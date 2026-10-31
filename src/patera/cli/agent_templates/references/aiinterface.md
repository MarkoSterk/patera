# AI interfaces (experimental)

`patera-aiinterface` is experimental and separately installed. Check its installed
source before extending it; its API is not promised stable. Core chat/prompt usage
does not require the heavy retrieval dependencies. Install the `augmentation`
extra only for retrieval features.

Public types include `AiService`, `AiServiceConfig`, `ChatResponse`,
`SqlHistoryProvider`, and decorators `system_prompt`, `user_prompt`, `history`.
Providers include `OpenAIServiceProvider` in
`patera.aiinterface.service_provider.openai` and an Ollama provider. Select the
provider and a model available to the application; do not hardcode a model merely
because an older example used it.

```python
from typing import TYPE_CHECKING

from patera.aiinterface import AiService, ChatResponse, system_prompt, user_prompt
from patera.aiinterface.service_provider.openai import OpenAIServiceProvider

if TYPE_CHECKING:
    from app import App


class Translator(AiService["App"]):
    service_provider = OpenAIServiceProvider()

    @system_prompt("Translate the supplied text.")
    @user_prompt("Translate '<:text>' to <:language>.")
    async def translate(self, text: str, language: str) -> ChatResponse:
        ...
```

Declare `TRANSLATOR: AiServiceConfig` with provider URL/model and environment-backed
credentials, then inject the service. Prompt placeholders use `<:name>`.
History requires a compatible model/provider with session_id, role, content and
order_number fields; check the provider's actual schema. Enforce ownership of
conversation/session identifiers in the application. Streaming return types and
retrieval components need tests against the installed version.

Use fake providers for tests. Keep untrusted retrieved text separate from
application instructions, bound history/retrieval work, and handle provider errors
and stream cancellation. Do not let generated text authorize application actions.

Sources: experimental package exports, README and examples; excluded from the
tutorial book's stable extension scope.
