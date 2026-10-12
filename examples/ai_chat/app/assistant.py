from typing import AsyncIterator, Optional

from patera.aiinterface import (
    AiService,
    ChatResponse,
    SqlHistoryProvider,
    augmentation,
    history,
    system_prompt,
    user_prompt,
)
from patera.aiinterface.augmentation_provider import BaseAugmentationProvider
from patera.aiinterface.service_provider.openai import OpenAIServiceProvider

from .database import ChatMessageRow, Document


class ChatHistory(SqlHistoryProvider[ChatMessageRow]):
    """Chat sessions in the chat_messages table (session ids: random UUIDs)."""

    model = ChatMessageRow


class Documents(BaseAugmentationProvider[Document]):
    """The texts in the documents table. Override base_query() to filter them."""

    model = Document


SYSTEM_PROMPT = (
    "You are the support assistant for <:product>. Answer briefly and only from "
    "the documents you are given; if they do not contain the answer, say so."
)


class Assistant(AiService):
    service_provider = OpenAIServiceProvider()  # or OllamaServiceProvider()
    history_provider = ChatHistory()
    augmentation_provider = Documents()

    @history
    @augmentation
    @system_prompt(SYSTEM_PROMPT)
    @user_prompt("<:message>")
    async def chat(
        self, session_id: Optional[str], message: str, product: str = "Patera"
    ) -> ChatResponse: ...

    @history
    @augmentation
    @system_prompt(SYSTEM_PROMPT)
    @user_prompt("<:message>")
    async def chat_stream(
        self, session_id: Optional[str], message: str, product: str = "Patera"
    ) -> AsyncIterator[ChatResponse]: ...
