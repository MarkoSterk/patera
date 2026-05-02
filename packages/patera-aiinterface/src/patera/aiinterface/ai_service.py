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
    cast,
)
from collections.abc import AsyncIterator
from pydantic import BaseModel, Field
from patera import Patera, Request
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
    TIMEOUT: Optional[int] = Field(
        60, description="Timeout for AI provider requests in seconds. Default 60 s"
    )
    MODEL: str = Field(description="Model name to use for AI requests")
    TEMPERATURE: Optional[float] = Field(
        0.0, description="Temperature for AI model responses"
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
    STREAM: Optional[bool] = Field(
        False, description="If the answer should be streamed."
    )
    AUGMENTATION: Optional[_AugmentationConfig] = Field(
        None, description="Configuration for prompt augmentation provider."
    )


AppT = TypeVar("AppT", bound="Patera")
ServiceT = TypeVar("ServiceT", bound=BaseServiceProvider)
HistoryT = TypeVar("HistoryT", default=None)
AugmentationT = TypeVar("AugmentationT", default=None)


class AiService(BaseExtension[AppT], Generic[AppT, ServiceT, HistoryT, AugmentationT]):
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
        self._configs = self._app.get_conf(self.configs_name, None)
        if self._configs is None:
            raise ValueError(
                f"Configurations for {self.configs_name} not found in app configurations."
            )
        self._configs = self.validate_configs(self._configs, AiServiceConfig)
        self._app.add_extension(self)
        if (
            hasattr(self, "augmentation_provider")
            and self.augmentation_provider is not None
        ):
            from .augmentation_provider import BaseAugmentationProvider

            assert isinstance(self.augmentation_provider, BaseAugmentationProvider)
            self.augmentation_provider._init_embedding_model(
                cast(dict[Any, Any], self._configs["AUGMENTATION"]),
                self,  # type: ignore
            )  # type: ignore

    async def chat(self, req: Request, msg: str) -> ChatResponse:
        return await self.service_provider.chat(req, msg, self)  # type: ignore

    def stream(self, req: Request, msg: str) -> AsyncIterator[ChatResponse]:
        return self.service_provider.stream(req, msg, self)  # type: ignore

    @property
    def configs(self) -> dict[str, Any]:
        return self._configs


AiServiceT = TypeVar("AiServiceT", bound=AiService[Any, Any, Any, Any])

P = ParamSpec("P")
R = TypeVar("R")


def session_id(
    name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        """
        Decorator for setting memory id of a tool method
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


def system_prompt(prompt: str) -> Callable[[Type[AiServiceT]], Type[AiServiceT]]:
    """
    Decorator for setting system prompt of AI service
    """

    def decorator(cls: Type[AiServiceT]) -> Type[AiServiceT]:
        """
        Sets system prompt for the AI service
        """
        setattr(cls, "__system_prompt__", prompt)
        return cls

    return decorator


F = TypeVar("F", bound=Callable[..., Any])


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
