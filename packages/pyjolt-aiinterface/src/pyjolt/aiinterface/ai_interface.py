"""
AI interface for PyJolt app
Makes connecting to LLM's easy
"""

from abc import ABC, abstractmethod
import inspect
from functools import wraps
from typing import (
    List,
    Dict,
    Any,
    Optional,
    get_type_hints,
    Callable,
    cast,
    TypedDict,
    NotRequired,
)
import docstring_parser
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall
from pydantic import BaseModel, Field

from pyjolt import PyJolt, Request, HttpStatus, Response
from pyjolt.utilities import run_sync_or_async
from pyjolt.exceptions import BaseHttpException
from pyjolt.base_extension import BaseExtension


class ChatContextNotFound(BaseHttpException):
    def __init__(self, msg: str, status_code: int | HttpStatus = HttpStatus.NOT_FOUND):
        super().__init__(msg, status_code=status_code)
        if isinstance(status_code, HttpStatus):
            status_code = status_code.value
        self.status_code = status_code


class FailedToRunAiToolMethod(BaseHttpException):
    def __init__(
        self,
        msg: str,
        method_name: str,
        *args,
        status_code: int | HttpStatus = HttpStatus.UNPROCESSABLE_ENTITY,
        **kwargs,
    ):
        super().__init__(msg, status_code=status_code)
        if isinstance(status_code, HttpStatus):
            status_code = status_code.value
        self.status_code = status_code
        self.method_name = method_name
        self.args = args
        self.kwargs = kwargs


class _AiInterfaceConfigs(BaseModel):
    """
    AI interface configuration model
    """

    API_KEY: str = Field(description="API key for the AI provider")
    API_BASE_URL: Optional[str] = Field(
        "https://api.openai.com/v1", description="Base URL for the AI provider API"
    )
    ORGANIZATION_ID: Optional[str] = Field(
        None, description="Organization ID for the AI provider"
    )
    PROJECT_ID: Optional[str] = Field(
        None, description="Project ID for the AI provider"
    )
    TIMEOUT: Optional[int] = Field(
        30, description="Timeout for AI provider requests in seconds"
    )
    MODEL: str = Field(description="Model name to use for AI requests")
    TEMPERATURE: Optional[float] = Field(
        1.0, description="Temperature for AI model responses"
    )
    RESPONSE_FORMAT: Optional[dict[str, str]] = Field(
        {"type": "json_object"}, description="Desired response format from the AI model"
    )
    TOOL_CHOICE: Optional[bool] = Field(
        False, description="Whether to enable tool choice for the AI model"
    )
    MAX_RETRIES: Optional[int] = Field(
        0, description="Maximum number of retries for AI provider requests"
    )
    CHAT_CONTEXT_NAME: Optional[str] = Field(
        "chat_context", description="Name of the chat context model for injection"
    )


class AiConfig(TypedDict):
    """Admin configurations typed dictionary"""

    API_KEY: str
    API_BASE_URL: NotRequired[str]
    ORGANIZATION_ID: NotRequired[str]
    PROJECT_ID: NotRequired[str]
    TIMEOUT: NotRequired[int]
    MODEL: str
    TEMPERATURE: NotRequired[float]
    RESPONSE_FORMAT: NotRequired[dict[str, str]]
    TOOL_CHOICE: NotRequired[bool]
    MAX_RETRIES: NotRequired[int]
    CHAT_CONTEXT_NAME: NotRequired[str]


class AiInterface(BaseExtension, ABC):
    """
    Main AI interface
    """

    def __init__(self, configs_name: Optional[str] = "AI_INTERFACE"):
        """
        Extension init method
        """
        self._app: PyJolt
        self._configs_name: str = cast(str, configs_name)
        self._configs: dict[str, Any] = {}
        self._api_key: str
        self._api_base_url: str
        self._organization_id: str
        self._project_id: str
        self._timeout: int
        self._model: str
        self._temperature: float
        self._response_format: dict[str, str]
        self._tool_choice: bool
        self._max_retries: int
        self._tools: list = []
        self._tools_mapping: dict[str, Callable] = {}
        self._chat_context_name: str = "chat_context"

    def init_app(self, app: PyJolt):
        """
        Initilizer method for extension
        """
        self._app = app  # type: ignore
        self._configs = cast(dict[str, Any], app.get_conf(self._configs_name, None))
        if self._configs is None:
            raise ValueError(
                f"Configurations for {self._configs_name} not found in app configurations."
            )
        self._configs = self.validate_configs(self._configs, _AiInterfaceConfigs)
        self._get_tools()

        self._api_key = self._configs["API_KEY"]
        self._api_base_url = self._configs["API_BASE_URL"]
        self._organization_id = self._configs["ORGANIZATION_ID"]
        self._project_id = self._configs["PROJECT_ID"]
        self._timeout = self._configs["TIMEOUT"]
        self._model = self._configs["MODEL"]
        self._temperature = self._configs["TEMPERATURE"]
        self._response_format = self._configs["RESPONSE_FORMAT"]
        self._tool_choice = self._configs["TOOL_CHOICE"]
        self._max_retries = self._configs["MAX_RETRIES"]
        self._chat_context_name = self._configs["CHAT_CONTEXT_NAME"]
        self._app.add_extension(self)

    @property
    def configs(self) -> dict[str, Any]:
        """
        Returns default configs object with env. var. or extension defaults
        """
        return self._configs

    async def provider(
        self, messages: List[Dict[str, str]], **kwargs
    ) -> tuple[
        str | None,
        Any | list[ChatCompletionMessageToolCall] | None,
        ChatCompletion | None,
    ]:
        """
        Default provider method. Uses AsyncOpenAI from the openai package
        """

        # Build request
        api_key = kwargs.get("api_key", self._api_key)
        organization = kwargs.get("organization", self._organization_id)
        project = kwargs.get("project", self._project_id)
        timeout = kwargs.get("timeout", self._timeout)
        base_url = kwargs.get("api_base_url", self._api_base_url)
        max_retries = kwargs.get("max_retries", self._max_retries)

        client: AsyncOpenAI = AsyncOpenAI(
            api_key=api_key,
            organization=organization,
            project=project,
            timeout=timeout,
            base_url=base_url,
            max_retries=max_retries,
        )

        model = kwargs.get("model", self._model)
        temperature = kwargs.get("temperature", self._temperature)
        response_format = kwargs.get("response_format", self._response_format)

        configs: dict = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "response_format": response_format,
        }
        if kwargs.get("use_tools", False):
            configs["tools"] = self._tools

        chat: ChatCompletion = await client.chat.completions.create(**configs)
        tool_calls = chat.choices[0].message.tool_calls or None
        assistant_message_content = chat.choices[0].message.content or None
        return assistant_message_content, tool_calls, chat

    async def create_chat_completion(
        self, messages: List[Dict[str, str]], **kwargs
    ) -> tuple[
        str | None, list[ChatCompletionMessageToolCall] | None, ChatCompletion | None
    ]:
        """
        Makes prompt with chosen provider method.
        Default is the default_provider method which is OpenAI compatible.

        :param stream: bool = False
        :returns chat_completion:
        """
        ##if default method is selected
        return await self.provider(messages, **kwargs)

    async def envoke_ai_tool(self, tool_name, *args, **kwargs) -> Any:
        """
        Runs a registered AI tool method
        """
        tool_method: Optional[Callable] = self._tools_mapping.get(tool_name, None)
        if tool_method is None:
            raise ValueError(
                f"Tool method named {tool_name} is not registered with the AI interface"
            )
        try:
            return await run_sync_or_async(tool_method, *args, **kwargs)
        except Exception as exc:
            raise FailedToRunAiToolMethod(
                f"Failed to run AI tool {tool_name}", *args, **kwargs
            ) from exc

    def build_function_schema(
        self,
        func: Callable,
        func_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Automatically builds an OpenAI function schema from a Python function.
        Assumes docstring and type hints follow some basic conventions.
        """
        # Parse the docstring
        doc = docstring_parser.parse(func.__doc__ or "")
        func_description = description or doc.short_description or ""

        # Build the skeleton
        schema: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": func_name or func.__name__,
                "description": func_description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

        # Collect parameter info
        sig = inspect.signature(func)
        hints = get_type_hints(func)

        for param_name, param in sig.parameters.items():
            # Derive param type from hints
            param_type = hints.get(param_name, str)
            if param_type is str:
                schema_type = "string"
            elif param_type in [int, float]:
                schema_type = "number"
            elif param_type is bool:
                schema_type = "boolean"
            else:
                schema_type = "string"

            param_desc: str | None = ""
            for doc_param in doc.params:
                if doc_param.arg_name == param_name:
                    param_desc = doc_param.description
                    break

            schema["function"]["parameters"]["properties"][param_name] = {
                "type": schema_type,
                "description": param_desc,
            }
            # If no default value is detected, the parameter is required
            if param.default is inspect.Parameter.empty:
                schema["function"]["parameters"]["required"].append(param_name)
        return schema

    @abstractmethod
    async def chat_context_loader(
        self, req: Request, *args: Any, **kwargs: Any
    ) -> Optional[Any]:
        """Should load and return a chat session object (ie db model) or none"""

    @property
    def chat_context_name(self) -> str:
        return self._chat_context_name

    @property
    def with_chat_context(self) -> Callable:
        """
        Decorator for injecting chat session to route handler.
        Uses the chat session loader method added with the
        @chat_context_loader decorator.

        Injects the chat context object as a keyword argument
        """
        interface: AiInterface = self

        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(self, *args, **kwargs) -> "Response":
                req: Request = args[0]
                if not isinstance(req, Request):
                    raise ValueError(
                        "Missing Request object at @with_chat_context decorator. The request object"
                        " must be the first argument of the route handler. Please check if you have "
                        "changed the argument sequence."
                    )
                chat_context = await run_sync_or_async(
                    interface.chat_context_loader, req
                )
                if chat_context is None:
                    raise ChatContextNotFound("Chat session not found")
                kwargs[interface.chat_context_name] = chat_context
                return await run_sync_or_async(func, self, *args, **kwargs)

            return wrapper

        return decorator

    def _get_tools(self):
        for name in dir(self):
            method = getattr(self, name)
            if not callable(method):
                continue

            is_tool = getattr(method, "__ai_tool", None) or None
            if not is_tool:
                continue
            self._tools.append(
                self.build_function_schema(
                    method, is_tool["name"], is_tool["description"]
                )
            )
            self._tools_mapping[is_tool["name"]] = method


def tool(name: Optional[str] = None, description: Optional[str] = None):
    """
    Decorator for adding a method as a tool to the Ai interface
    """

    def decorator(func: Callable):
        """
        Marks method to as ai interface tool
        """
        setattr(
            func,
            "__ai_tool",
            {"name": name or func.__name__, "description": description or func.__doc__},
        )
        return func

    return decorator
