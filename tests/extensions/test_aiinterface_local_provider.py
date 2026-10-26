"""Opt-in local Ollama checks; never sends requests to a paid provider.

Set PATERA_TEST_OLLAMA_URL and PATERA_TEST_OLLAMA_MODEL after pulling the model.
"""

import json
import os
from urllib.parse import urlsplit

import pytest

pytest.importorskip("patera.aiinterface")

from patera.aiinterface import AiServiceConfig, ChatMessage  # noqa: E402
from patera.aiinterface.service_provider.openai import OpenAIServiceProvider  # noqa: E402
from patera.aiinterface.service_provider.ollama import OllamaServiceProvider  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("PATERA_TEST_OLLAMA_URL"), reason="local Ollama is opt-in"
    ),
]


@pytest.fixture(params=["ollama", "openai-compatible"])
def local_provider(request):
    url = os.environ["PATERA_TEST_OLLAMA_URL"].rstrip("/")
    assert urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"}
    native = request.param == "ollama"
    provider = OllamaServiceProvider() if native else OpenAIServiceProvider()
    configs = AiServiceConfig(
        BASE_URL=url if native else url + "/v1",
        MODEL=os.environ["PATERA_TEST_OLLAMA_MODEL"],
        API_KEY="local-test-only",
        TIMEOUT=180,
        TEMPERATURE=0,
    )
    return provider, configs


async def test_local_completion_and_stream(local_provider):
    provider, configs = local_provider
    messages = [ChatMessage(role="user", content="Reply with one short greeting.")]
    response = await provider.complete(messages, configs)
    assert response.message.content.strip()
    assert response.finish_reason
    assert response.usage.output_tokens > 0
    chunks = [chunk async for chunk in provider.stream(messages, configs)]
    assert any(chunk.message.content for chunk in chunks)
    assert any(chunk.finish_reason for chunk in chunks)
    assert any(chunk.usage.output_tokens for chunk in chunks)


async def test_local_json_format(local_provider):
    provider, configs = local_provider
    configs = configs.model_copy(update={"RESPONSE_FORMAT": {"type": "json_object"}})
    messages = [
        ChatMessage(role="user", content='Return only JSON: {"greeting":"hello"}')
    ]
    response = await provider.complete(messages, configs)
    assert isinstance(json.loads(response.message.content), dict)
