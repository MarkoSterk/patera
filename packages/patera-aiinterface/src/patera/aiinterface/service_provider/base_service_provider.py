from abc import ABC, abstractmethod
from typing import AsyncIterator, TYPE_CHECKING
from patera import Request

from .chat_response import ChatResponse

if TYPE_CHECKING:
    from ..ai_service import AiService


class BaseServiceProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        req: Request,
        system_prompt: str,
        user_prompt: str,
        use_history: bool,
        use_augmentation: bool,
        ext: "AiService",
        **kwargs,
    ) -> ChatResponse: ...

    async def stream(
        self,
        req: Request,
        system_prompt: str,
        user_prompt: str,
        use_history: bool,
        use_augmentation: bool,
        ext: "AiService",
        **kwargs,
    ) -> AsyncIterator[ChatResponse]:
        raise NotImplementedError(
            "If you wish to use streaming mode please implement the stream() method."
        )
