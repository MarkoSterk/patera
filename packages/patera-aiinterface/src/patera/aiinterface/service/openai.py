"""
OpenAI chat service
"""

from patera import Request

from .base_service_provider import BaseServiceProvider, ChatResponse


class OpenAiServiceProvider(BaseServiceProvider):
    async def chat(self, req: Request, msg: str) -> ChatResponse:
        return ChatResponse()
