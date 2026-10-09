"""
AI interface tests. The heavy ML dependencies (torch, sentence-transformers,
pgvector) are only needed for prompt augmentation, so they are replaced by
stubs when not installed.
"""

from __future__ import annotations

import sys
import types
from typing import AsyncIterator

import pytest

from patera import Request, Response
from patera.controller import Controller, get, path


def _stub_module(name: str, **attrs) -> None:
    if name in sys.modules:
        return
    try:
        __import__(name)
    except Exception:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


_stub_module("torch", Tensor=object)
_stub_module("sentence_transformers", SentenceTransformer=object)
_stub_module("pgvector")
_stub_module("pgvector.sqlalchemy", Vector=object)

# Skip (instead of failing collection) when patera-aiinterface is not installed.
pytest.importorskip("patera.aiinterface")

from patera.aiinterface import (  # noqa: E402
    AiService,
    AiServiceConfig,
    ChatResponse,
    system_prompt,
    user_prompt,
)
from patera.aiinterface.service_provider import BaseServiceProvider  # noqa: E402
from patera.injectable import Inject  # noqa: E402

pytestmark = pytest.mark.integration


class FakeProvider(BaseServiceProvider):
    def __init__(self):
        self.calls: list[dict] = []

    async def chat(
        self,
        req,
        system_prompt,
        user_prompt,
        use_history,
        use_augmentation,
        ext,
        **kwargs,
    ):
        self.calls.append(
            {"system": system_prompt, "user": user_prompt, "kwargs": kwargs}
        )
        message = user_prompt
        for key, value in kwargs.items():
            message = message.replace(f"<:{key}>", str(value))
        return message

    async def stream(
        self,
        req,
        system_prompt,
        user_prompt,
        use_history,
        use_augmentation,
        ext,
        **kwargs,
    ):
        self.calls.append({"stream": True, "kwargs": kwargs})
        for word in ("a", "b"):
            yield f"{word}-{kwargs.get('topic')}"


class Assistant(AiService):
    service_provider = FakeProvider()

    @system_prompt("You are helpful")
    @user_prompt("Translate <:text> to <:language>")
    async def translate(self, text: str, language: str = "German") -> ChatResponse: ...

    @system_prompt("Stream")
    @user_prompt("About <:topic>")
    async def stream_about(self, topic: str) -> AsyncIterator[ChatResponse]: ...


@path("/ai")
class AiController(Controller):
    assistant: Inject[Assistant]

    @get("/translate/<text>")
    async def translate(self, req: Request, text: str) -> Response:
        positional = await self.assistant.translate(text, "French")
        keyword = await self.assistant.translate(text=text)
        chunks = [c async for c in await self.assistant.stream_about("cats")]
        return req.res.json(
            {"positional": positional, "keyword": keyword, "chunks": chunks}
        )


async def test_prompt_arguments_are_bound(make_app, client_for):
    Assistant.service_provider.calls.clear()
    app = make_app(
        controllers=[AiController],
        ASSISTANT=AiServiceConfig(BASE_URL="http://llm.local", MODEL="test-model"),
    )
    async with client_for(app) as client:
        res = await client.get("/ai/translate/hello")
    assert res.json() == {
        # positional arguments used to be dropped silently
        "positional": "Translate hello to French",
        "keyword": "Translate hello to German",
        # streaming calls used to ignore all arguments
        "chunks": ["a-cats", "b-cats"],
    }
    calls = Assistant.service_provider.calls
    assert calls[0]["system"] == "You are helpful"
    assert calls[2] == {"stream": True, "kwargs": {"topic": "cats"}}


# --- Service providers (HTTP mocked) ---------------------------------------

import json  # noqa: E402

import httpx  # noqa: E402

from patera.aiinterface.service_provider import ollama as ollama_module  # noqa: E402
from patera.aiinterface.service_provider import openai as openai_module  # noqa: E402


class FakeHistory:
    def __init__(self, session_id="s1", history=None):
        self.session_id = session_id
        self.history = history or []
        self.saved: list[tuple] = []

    async def get_history_messages(self, req):
        return self.session_id, list(self.history)

    def save_message(self, session_id, message, order_number):
        self.saved.append(
            (session_id, message["role"], message["content"], order_number)
        )


class FakeExt:
    def __init__(self, history=None, **configs):
        self.history_provider = history
        self.augmentation_provider = None
        self.configs = AiServiceConfig(
            BASE_URL="http://llm.local", MODEL="m", API_KEY="key", **configs
        )


def _mock_httpx(monkeypatch, module, handler):
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


async def test_openai_chat_with_history(monkeypatch):
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer key"
        return httpx.Response(
            200,
            json={
                "model": "m",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hi!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            },
        )

    _mock_httpx(monkeypatch, openai_module, handler)
    history = FakeHistory()
    provider = openai_module.OpenAIServiceProvider()
    res = await provider.chat(
        None, "sys", "Hello <:name>", True, False, FakeExt(history), name="Ana"
    )
    assert res.message.content == "Hi!"
    assert res.session_id == "s1"
    assert payloads[0]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Hello Ana"},
    ]
    assert history.saved == [
        ("s1", "system", "sys", 0),
        ("s1", "user", "Hello Ana", 1),
        ("s1", "assistant", "Hi!", 2),
    ]


async def test_openai_stream_with_history(monkeypatch):
    chunks = [
        {"model": "m", "choices": [{"delta": {"role": "assistant", "content": "He"}}]},
        {
            "model": "m",
            "choices": [{"delta": {"content": "llo"}, "finish_reason": "stop"}],
        },
    ]

    def handler(request):
        body = (
            "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    _mock_httpx(monkeypatch, openai_module, handler)
    history = FakeHistory(history=[{"role": "system", "content": "old"}])
    provider = openai_module.OpenAIServiceProvider()
    parts = [
        c
        async for c in provider.stream(None, "sys", "Q", True, False, FakeExt(history))
    ]
    assert "".join(p.message.content for p in parts) == "Hello"
    assert history.saved == [("s1", "user", "Q", 1), ("s1", "assistant", "Hello", 2)]


async def test_ollama_chat_and_stream(monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        if payload["stream"]:
            lines = [
                {"model": "m", "message": {"role": "assistant", "content": "A"}},
                {
                    "model": "m",
                    "message": {"role": "assistant", "content": "B"},
                    "done": True,
                },
            ]
            return httpx.Response(
                200, text="\n".join(json.dumps(line) for line in lines)
            )
        return httpx.Response(
            200,
            json={
                "model": "m",
                "message": {"role": "assistant", "content": "ok"},
                "done": True,
            },
        )

    _mock_httpx(monkeypatch, ollama_module, handler)
    provider = ollama_module.OllamaServiceProvider()

    res = await provider.chat(None, "sys", "Q", False, False, FakeExt())
    assert res.message.content == "ok"
    assert res.finish_reason == "stop"

    history = FakeHistory()
    parts = [
        c
        async for c in provider.stream(None, "sys", "Q", True, False, FakeExt(history))
    ]
    assert "".join(p.message.content for p in parts) == "AB"
    assert history.saved == [
        ("s1", "system", "sys", 0),
        ("s1", "user", "Q", 1),
        ("s1", "assistant", "AB", 2),
    ]


async def test_history_requires_provider():
    provider = openai_module.OpenAIServiceProvider()
    ext = FakeExt()
    with pytest.raises(ValueError, match="History Provider"):
        await provider.chat(None, "s", "u", True, False, ext)
