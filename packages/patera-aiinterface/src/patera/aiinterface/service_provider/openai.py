"""
OpenAI chat service
"""

from typing import TYPE_CHECKING
from patera import Request

from .base_service_provider import BaseServiceProvider, ChatResponse

if TYPE_CHECKING:
    from ..ai_service import AiService


class OpenAiServiceProvider(BaseServiceProvider):
    async def chat(self, req: Request, msg: str, ext: AiService) -> ChatResponse:
        return ChatResponse()  # type: ignore
