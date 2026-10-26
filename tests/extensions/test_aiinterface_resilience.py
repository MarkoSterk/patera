"""Provider failures must release connections and never persist partial answers."""

import asyncio
import json

import httpx
import pytest

pytest.importorskip("patera.aiinterface")

from patera.aiinterface.service_provider.openai import OpenAIServiceProvider  # noqa: E402
from patera.aiinterface.service_provider.ollama import OllamaServiceProvider  # noqa: E402
from tests.extensions.test_aiinterface import CONFIG, _chat_service  # noqa: E402

pytestmark = pytest.mark.integration


class WireStream(httpx.AsyncByteStream):
    def __init__(self, payload, *, wait=False):
        self.payload = payload
        self.wait = wait
        self.closed = False
        self.waiting = asyncio.Event()

    async def __aiter__(self):
        # Fragment JSON and UTF-8 across transport reads.
        for byte in self.payload:
            yield bytes([byte])
        if self.wait:
            self.waiting.set()
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


@pytest.fixture(params=[OpenAIServiceProvider, OllamaServiceProvider])
def provider(request):
    return request.param()


def wire(provider, *, terminal=True):
    if isinstance(provider, OpenAIServiceProvider):
        content = 'data: {"choices":[{"delta":{"content":"čaj"}}]}\n\n'
        return (content + ("data: [DONE]\n\n" if terminal else "")).encode()
    content = '{"message":{"content":"čaj"},"done":false}\n'
    return (content + ('{"done":true}\n' if terminal else "")).encode()


def attach(monkeypatch, provider, stream, status=200):
    def client(configs):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(status, stream=stream)
            )
        )

    monkeypatch.setattr(provider, "create_client", client)


async def test_fragmented_stream(provider, monkeypatch):
    stream = WireStream(wire(provider))
    attach(monkeypatch, provider, stream)
    chunks = [chunk async for chunk in provider.stream([], CONFIG)]
    assert "".join(chunk.message.content for chunk in chunks) == "čaj"
    assert stream.closed


@pytest.mark.parametrize("ending", ["truncated", "malformed", "close", "cancel"])
async def test_incomplete_answer_is_not_saved(provider, monkeypatch, make_app, ending):
    payload = wire(provider, terminal=False)
    if ending == "malformed":
        payload += (
            b"data: invalid\n\n"
            if isinstance(provider, OpenAIServiceProvider)
            else b"invalid\n"
        )
    stream = WireStream(payload, wait=ending == "cancel")
    attach(monkeypatch, provider, stream)
    service = _chat_service(make_app)
    service.service_provider = provider
    answer = service.chat_stream(None, "hello")
    assert (await anext(answer)).message.content == "čaj"
    if ending == "close":
        await answer.aclose()
    elif ending == "cancel":
        task = asyncio.create_task(anext(answer))
        await asyncio.wait_for(stream.waiting.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        error = (
            json.JSONDecodeError if ending == "malformed" else httpx.RemoteProtocolError
        )
        with pytest.raises(error):
            await anext(answer)
    assert stream.closed
    assert service.history_provider.sessions == {}


@pytest.mark.parametrize("status", [401, 429, 500, 503])
@pytest.mark.parametrize("streaming", [False, True])
async def test_http_errors(provider, monkeypatch, status, streaming):
    stream = WireStream(b'{"error":"unavailable"}')
    attach(monkeypatch, provider, stream, status)
    with pytest.raises(httpx.HTTPStatusError) as caught:
        if streaming:
            await anext(provider.stream([], CONFIG))
        else:
            await provider.complete([], CONFIG)
    assert caught.value.response.status_code == status
    assert stream.closed


@pytest.mark.parametrize(
    "error", [httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout]
)
async def test_transport_failure(provider, monkeypatch, make_app, error):
    def fail(req):
        raise error("simulated failure", request=req)

    monkeypatch.setattr(
        provider,
        "create_client",
        lambda configs: httpx.AsyncClient(transport=httpx.MockTransport(fail)),
    )
    service = _chat_service(make_app)
    service.service_provider = provider
    with pytest.raises(error):
        await service.chat(None, "hello")
    assert service.history_provider.sessions == {}


async def test_malformed_completion(provider, monkeypatch):
    stream = WireStream(b"not json")
    attach(monkeypatch, provider, stream)
    with pytest.raises(json.JSONDecodeError):
        await provider.complete([], CONFIG)
    assert stream.closed


async def test_ollama_stream_error(monkeypatch):
    provider = OllamaServiceProvider()
    stream = WireStream(b'{"error":"model failed"}\n')
    attach(monkeypatch, provider, stream)
    with pytest.raises(httpx.RemoteProtocolError, match="model failed"):
        await anext(provider.stream([], CONFIG))
    assert stream.closed
