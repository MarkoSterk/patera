from __future__ import annotations

import pytest

from patera import MediaType, Request, Response
from patera.caching import Caching, CachingConfig, MemoryCacheBackend, cache
from patera.caching.backends.sqlite_cache_backend import SQLiteCacheBackend
from patera.controller import Controller, get, path, produces

pytestmark = pytest.mark.integration

CALLS: dict[str, int] = {}


class PublicCache(Caching):
    """No backend configured: falls back to an in-memory backend."""


@path("/cached")
class CachedController(Controller):
    @get("/json")
    @cache("PUBLIC_CACHE", duration=60)
    async def json_view(self, req: Request) -> Response:
        CALLS["json"] = CALLS.get("json", 0) + 1
        return req.res.json({"calls": CALLS["json"]})

    @get("/html")
    @produces(MediaType.TEXT_HTML)
    @cache("PUBLIC_CACHE")
    async def html_view(self, req: Request) -> Response:
        CALLS["html"] = CALLS.get("html", 0) + 1
        return req.res.html_body(f"<b>{CALLS['html']}</b>")

    @get("/error")
    @cache("PUBLIC_CACHE")
    async def error_view(self, req: Request) -> Response:
        CALLS["error"] = CALLS.get("error", 0) + 1
        return req.res.json({"calls": CALLS["error"]}).status(503)

    @get("/cookie")
    @cache("PUBLIC_CACHE")
    async def cookie_view(self, req: Request) -> Response:
        CALLS["cookie"] = CALLS.get("cookie", 0) + 1
        return req.res.json({"calls": CALLS["cookie"]}).set_cookie("s", "1")

    @get("/fixed")
    @cache("PUBLIC_CACHE", key="fixed-key")
    async def fixed(self, req: Request) -> Response:
        CALLS["fixed"] = CALLS.get("fixed", 0) + 1
        return req.res.json({"calls": CALLS["fixed"]})


@pytest.fixture
def app(make_app):
    CALLS.clear()
    return make_app(controllers=[CachedController], extensions=[PublicCache])


async def test_cache_hit_and_query_variants(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/cached/json")).json() == {"calls": 1}
        assert (await client.get("/cached/json")).json() == {"calls": 1}
        # Repeated query keys used to crash (lists are unhashable)
        assert (await client.get("/cached/json?tag=a&tag=b")).json() == {"calls": 2}
        assert (await client.get("/cached/json?tag=a&tag=b")).json() == {"calls": 2}
        assert (await client.get("/cached/json?tag=b")).json() == {"calls": 3}


async def test_cached_response_keeps_media_type(app, client_for):
    async with client_for(app) as client:
        first = await client.get("/cached/html")
        second = await client.get("/cached/html")
        assert first.text == second.text == "<b>1</b>"
        assert second.headers["content-type"] == "text/html; charset=utf-8"


async def test_errors_and_cookies_are_not_cached(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/cached/error")).json() == {"calls": 1}
        assert (await client.get("/cached/error")).json() == {"calls": 2}
        assert (await client.get("/cached/cookie")).json() == {"calls": 1}
        assert (await client.get("/cached/cookie")).json() == {"calls": 2}


async def test_manual_api_and_invalidation(app, client_for):
    caching = app.get_extension(PublicCache)
    async with client_for(app) as client:
        await client.get("/cached/fixed")
        assert (await client.get("/cached/fixed")).json() == {"calls": 1}
        assert await caching.delete("fixed-key") == 1
        assert (await client.get("/cached/fixed")).json() == {"calls": 2}

        await client.get("/cached/json")
        await client.get("/cached/json?x=1")
        assert await caching.delete("json_view:*", wildcard=True) == 2
        await client.get("/cached/json")
        assert await caching.delete(r"^json_view:GET", regex=True) == 1
        await caching.clear()


def test_default_backend_uses_configs(make_app):
    app = make_app(
        extensions=[PublicCache], PUBLIC_CACHE=CachingConfig(DURATION=5, MAX_SIZE=3)
    )
    backend = app.get_extension(PublicCache).backend
    assert isinstance(backend, MemoryCacheBackend)
    assert backend.default_ttl == 5
    assert backend.maxsize == 3


async def test_memory_backend_expiry(monkeypatch):
    backend = MemoryCacheBackend(default_ttl=10)
    now = [1000.0]
    monkeypatch.setattr(MemoryCacheBackend, "_now", staticmethod(lambda: now[0]))
    await backend.set("k", {"v": 1}, duration=5)
    assert await backend.get("k") == {"v": 1}
    now[0] += 6
    assert await backend.get("k") is None
    with pytest.raises(ValueError):
        await backend.delete("k", regex=True, wildcard=True)


async def test_sqlite_backend(tmp_path):
    backend = SQLiteCacheBackend.configure_from_app(
        None,  # type: ignore[arg-type]
        CachingConfig(
            DURATION=60, SQLITE_PATH=str(tmp_path / "c" / "cache.db"), KEY_PREFIX="t"
        ),
    )
    await backend.connect()
    try:
        await backend.set("users:1", {"body": 1})
        await backend.set("users:2", {"body": 2})
        await backend.set("posts:1", {"body": 3})
        assert await backend.get("users:1") == {"body": 1}
        assert await backend.delete("users:*", wildcard=True) == 2
        assert await backend.get("users:2") is None
        assert await backend.delete(r"^posts", regex=True) == 1
        await backend.set("short", {"b": 1}, duration=-1)
        assert await backend.get("short") is None
        await backend.set("x", {"b": 1})
        await backend.clear()
        assert await backend.get("x") is None
    finally:
        await backend.disconnect()

    with pytest.raises(ValueError):
        SQLiteCacheBackend(db_path=":memory:", table="bad; DROP TABLE x")


async def test_redis_backend():
    fakeredis = pytest.importorskip("fakeredis")
    from patera.caching.backends.redis_cache_backend import RedisCacheBackend

    backend = RedisCacheBackend.configure_from_app(
        None,  # type: ignore[arg-type]
        {"REDIS_URL": "redis://localhost:6379/0", "KEY_PREFIX": "app"},
    )
    assert backend.default_ttl == 300
    backend._client = fakeredis.FakeAsyncRedis()
    await backend.set("users:1", {"a": 1})
    await backend.set("users:2", {"a": 2})
    await backend.set("posts:1", {"a": 3})
    assert await backend.get("users:1") == {"a": 1}
    assert await backend.delete("users:*", wildcard=True) == 2
    assert await backend.delete(r"^posts:\d$", regex=True) == 1
    assert await backend.delete("missing") == 0
    await backend.clear()
    await backend.disconnect()
