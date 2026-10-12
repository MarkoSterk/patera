# patera-aiinterface

Experimental LLM interface for Patera: prompts, chat history and retrieval augmentation. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

> **Experimental.** This package is not yet ready for production use; its API may change in any release.

## Installation

```sh
pip install patera-aiinterface
# with retrieval augmentation (sentence-transformers, PyTorch, pgvector)
pip install "patera-aiinterface[augmentation]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

`patera-aiinterface` connects to chat completion APIs (OpenAI-compatible and Ollama). Retrieval
augmentation needs the `augmentation` extra; everything else works without it.

```python
from typing import AsyncIterator, Optional

from patera.aiinterface import (
    AiService, AiServiceConfig, ChatResponse, SqlHistoryProvider, history, system_prompt, user_prompt,
)
from patera.aiinterface.service_provider.openai import OpenAIServiceProvider


class ChatHistory(SqlHistoryProvider[ChatMessageRow]):   # a model with session_id, role,
    model = ChatMessageRow                               # content and order_number columns


class Assistant(AiService):
    service_provider = OpenAIServiceProvider()           # or OllamaServiceProvider()
    history_provider = ChatHistory()

    @system_prompt("You are a helpful translator.")
    @user_prompt("Translate '<:text>' to <:language>.")
    async def translate(self, text: str, language: str = "German") -> ChatResponse: ...

    @history
    @system_prompt("You are a friendly assistant.")
    @user_prompt("<:message>")
    async def chat(self, session_id: Optional[str], message: str) -> AsyncIterator[ChatResponse]: ...


class Config(BaseConfig):
    ...
    ASSISTANT: AiServiceConfig = AiServiceConfig(
        BASE_URL="https://api.openai.com/v1", API_KEY="...", MODEL="gpt-4o-mini", HISTORY_LIMIT=10,
    )
```

See the [AI interface (experimental) section of the Patera documentation](https://github.com/MarkoSterk/Patera#ai-interface-experimental) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
