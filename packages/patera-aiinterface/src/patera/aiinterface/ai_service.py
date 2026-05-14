"""
AI interface for Patera app
Makes connecting to LLM's easy
"""

from functools import wraps
from typing import (
    Any,
    Awaitable,
    Optional,
    Callable,
    ParamSpec,
    Type,
    TypeVar,
    Generic,
)
from collections.abc import AsyncIterator
from pydantic import BaseModel, Field
from patera import Patera, Request
from patera.ctx import current_request
from patera.base_extension import BaseExtension

from .service_provider import BaseServiceProvider, ChatResponse

from .augmentation_provider.base_augmentation_provider import (
    _AugmentationConfig,
)


class AiServiceConfig(BaseModel):
    """
    AI service configuration model
    """

    API_KEY: Optional[str] = Field(None, description="API key for the AI provider")
    BASE_URL: str = Field(description="Base URL for the AI provider API")
    ORGANIZATION_ID: Optional[str] = Field(
        None, description="Organization ID for the AI provider"
    )
    PROJECT_ID: Optional[str] = Field(
        None, description="Project ID for the AI provider"
    )
    TIMEOUT: int = Field(
        60, description="Timeout for AI provider requests in seconds. Default 60 s"
    )
    MODEL: str = Field(description="Model name to use for AI requests")
    TEMPERATURE: float = Field(0.0, description="Temperature for AI model responses")
    RESPONSE_FORMAT: dict[str, str] = Field(
        {"type": "json_object"}, description="Desired response format from the AI model"
    )
    TOOL_CHOICE: bool = Field(
        False, description="Whether to enable tool choice for the AI model"
    )
    MAX_RETRIES: int = Field(
        0, description="Maximum number of retries for AI provider requests"
    )
    STREAM: bool = Field(False, description="If the answer should be streamed.")
    AUGMENTATION: Optional[_AugmentationConfig] = Field(
        None, description="Configuration for prompt augmentation provider."
    )


AppT = TypeVar("AppT", bound="Patera[Any]")
ServiceT = TypeVar("ServiceT", bound=BaseServiceProvider)
HistoryT = TypeVar("HistoryT", default=None)
AugmentationT = TypeVar("AugmentationT", default=None)


class AiService(
    BaseExtension[AppT, AiServiceConfig],
    Generic[AppT, ServiceT, HistoryT, AugmentationT],
):
    """
    Main AI service class for handling chat requests and connecting to the AI provider
    """

    service_provider: ServiceT
    history_provider: Optional[HistoryT]
    augmentation_provider: Optional[AugmentationT]

    def init(self):
        """
        Initilizer method for extension
        """
        self._app.add_extension(self)
        if (
            hasattr(self, "augmentation_provider")
            and self.augmentation_provider is not None
        ):
            from .augmentation_provider import BaseAugmentationProvider

            assert isinstance(self.augmentation_provider, BaseAugmentationProvider)
            assert self.configs.AUGMENTATION is not None
            self.augmentation_provider._init_embedding_model(
                self.configs.AUGMENTATION,
                self,  # type: ignore
            )  # type: ignore
    
    async def _wrapper(self, func, **kwargs) -> ChatResponse:
        """
        Wrapper method for handling chat requests, calling the service provider and returning the response
        """
        system_prompt: str = getattr(func, "__system_prompt__", "")
        user_prompt: str = getattr(func, "__user_prompt__", "")
        use_history: bool = getattr(func, "__use_history__", False)
        use_augmentation: bool = getattr(func, "__use_augmentation__", False)
        req = current_request.request

        return await self.service_provider.chat(req, system_prompt, user_prompt,
                                                use_history, use_augmentation, self, **kwargs)
    
    def _stream_wrapper(self, func, *args, **kwargs) -> AsyncIterator[ChatResponse]:
        """
        Wrapper method for handling streaming chat requests, calling the service provider and yielding the response
        """
        system_prompt: str = getattr(func, "__system_prompt__", "")
        user_prompt: str = getattr(func, "__user_prompt__", "")
        use_history: bool = getattr(func, "__use_history__", False)
        use_augmentation: bool = getattr(func, "__use_augmentation__", False)
        req = current_request.request

        for response in self.service_provider.stream(req, system_prompt, user_prompt,
                                                           use_history, use_augmentation):
            yield response

    
    @classmethod
    def _wrap_method(cls, func):
        @wraps(func)
        async def inner(self, *args, **kwargs):
            stream: bool = getattr(func, "__stream__", False)
            if stream:
                return self._stream_wrapper(func, *args, **kwargs)
            return await self._wrapper(func, **kwargs)

        return inner

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        for name, value in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue

            if callable(value) and hasattr(value, "__system_prompt__"):
                setattr(cls, name, AiService._wrap_method(value))


AiServiceT = TypeVar("AiServiceT", bound=AiService[Any, Any, Any, Any])

P = ParamSpec("P")
R = TypeVar("R")


def session_id(
    name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        """
        Decorator for setting memory id
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            req: Request = args[0]  # type: ignore
            if req is None or not isinstance(req, Request):
                raise ValueError(
                    "First argument of the method must be a Request object"
                )
            session_id_value = req._route_parameters.get(name, None)
            if session_id_value is None:
                raise ValueError(
                    f"Session ID not found in route parameters with name '{name}'"
                )
            req._route_parameters["session_id"] = session_id_value  # type: ignore
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def system_prompt(prompt: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for setting system prompt
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Sets system prompt for the AI service
        """
        setattr(func, "__system_prompt__", prompt)
        return func

    return decorator

def history(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for adding history to chat requests
    """

    setattr(func, "__use_history__", True)
    return func

def augmentation(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for adding augmentation to chat requests
    """

    setattr(func, "__use_augmentation__", True)
    return func

def user_prompt(prompt: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for setting user prompt
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Sets user prompt for the tool method
        """
        setattr(func, "__user_prompt__", prompt)
        return func

    return decorator

F = TypeVar("F", bound=Callable[..., Any])

def stream(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for marking a method as a streaming method
    """

    setattr(func, "__stream__", True)
    return func

def tool(
    name: Optional[str] = None, description: Optional[str] = None
) -> Callable[[F], F]:
    """
    Decorator for adding a method as a tool to the Ai interface
    """

    def decorator(func: F) -> F:
        """
        Marks method to as ai interface tool
        """
        setattr(
            func,
            "__ai_tool__",
            {"name": name or func.__name__, "description": description or func.__doc__},
        )
        return func

    return decorator
