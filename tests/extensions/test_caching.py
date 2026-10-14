from __future__ import annotations

import datetime

import pytest
from pydantic import BaseModel

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
    backend = SQLiteCacheBackend.from_configs(
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

    backend = RedisCacheBackend.from_configs(
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


# ---- Per-user cache entries -----------------------------------------------------

from patera.middleware import MiddlewareBase, middleware  # noqa: E402


class User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


@middleware(order=5)
class FakeLogin(MiddlewareBase):
    """Signs in the user named by the X-User header."""

    async def middleware(self, req: Request) -> Response:
        user_id = req.headers.get("x-user")
        if user_id:
            req.set_user(User(int(user_id)))
        return await self.next(req)


@path("/who")
class WhoController(Controller):
    @get("/me")
    @cache("PUBLIC_CACHE")
    async def me(self, req: Request) -> Response:
        CALLS["me"] = CALLS.get("me", 0) + 1
        user = req.user
        return req.res.json({"user": user.id if user else None, "calls": CALLS["me"]})

    @get("/shared")
    @cache("PUBLIC_CACHE", per_user=False)
    async def shared(self, req: Request) -> Response:
        CALLS["shared"] = CALLS.get("shared", 0) + 1
        return req.res.json({"calls": CALLS["shared"]})


@pytest.fixture
def user_app(make_app):
    CALLS.clear()
    return make_app(
        controllers=[WhoController], extensions=[PublicCache], middleware=[FakeLogin]
    )


async def test_signed_in_users_get_their_own_entries(user_app, client_for):
    async with client_for(user_app) as client:
        alice = await client.get("/who/me", headers={"x-user": "1"})
        bob = await client.get("/who/me", headers={"x-user": "2"})
        alice_again = await client.get("/who/me", headers={"x-user": "1"})
        anonymous = await client.get("/who/me")
        anonymous_again = await client.get("/who/me")
    assert alice.json() == {"user": 1, "calls": 1}
    assert bob.json() == {"user": 2, "calls": 2}  # not Alice's cached page
    assert alice_again.json() == {"user": 1, "calls": 1}
    assert anonymous.json() == {"user": None, "calls": 3}
    assert anonymous_again.json() == {"user": None, "calls": 3}


async def test_per_user_false_shares_one_entry(user_app, client_for):
    async with client_for(user_app) as client:
        first = await client.get("/who/shared", headers={"x-user": "1"})
        second = await client.get("/who/shared", headers={"x-user": "2"})
    assert first.json() == second.json() == {"calls": 1}


def test_user_cache_key(make_app):
    from types import SimpleNamespace

    caching = make_app(extensions=[PublicCache]).get_extension(PublicCache)

    def request_with(user):
        return SimpleNamespace(user=user)

    assert caching.user_cache_key(request_with(None)) is None
    assert caching.user_cache_key(request_with(User(7))) == "7"
    assert caching.user_cache_key(request_with({"id": 8})) == "8"
    assert caching.user_cache_key(request_with(SimpleNamespace(pk="u-9"))) == "u-9"
    assert caching.user_cache_key(request_with("ana")) == "ana"


# ---- Backend construction ---------------------------------------------------------


class SqliteCache(Caching):
    backend_class = SQLiteCacheBackend


def test_backend_class_is_created_from_configs(make_app, tmp_path):
    app = make_app(
        extensions=[SqliteCache],
        SQLITE_CACHE=CachingConfig(
            DURATION=42, SQLITE_PATH=str(tmp_path / "c.db"), KEY_PREFIX="blog"
        ),
    )
    backend = app.get_extension(SqliteCache).backend
    assert isinstance(backend, SQLiteCacheBackend)
    assert backend.default_ttl == 42
    assert backend._prefix == "blog:"


def test_an_explicit_backend_instance_is_used_as_is(make_app):
    explicit = MemoryCacheBackend(default_ttl=7, maxsize=2)

    class ExplicitCache(Caching):
        def init(self) -> None:
            self.backend = explicit
            super().init()

    app = make_app(
        extensions=[ExplicitCache],
        EXPLICIT_CACHE=CachingConfig(DURATION=99, MAX_SIZE=99),
    )
    backend = app.get_extension(ExplicitCache).backend
    assert backend is explicit
    assert backend.default_ttl == 7 and backend.maxsize == 2


def test_every_backend_has_from_configs():
    memory = MemoryCacheBackend.from_configs(
        None,  # type: ignore[arg-type]
        CachingConfig(DURATION=11, MAX_SIZE=4),
    )
    assert (memory.default_ttl, memory.maxsize) == (11, 4)


def test_configure_from_app_was_removed():
    from patera.caching.backends.redis_cache_backend import RedisCacheBackend

    for backend in (MemoryCacheBackend, RedisCacheBackend, SQLiteCacheBackend):
        assert not hasattr(backend, "configure_from_app")


# ---- Redis namespaces -----------------------------------------------------------


async def test_redis_default_prefix_and_clear_keep_other_data():
    fakeredis = pytest.importorskip("fakeredis")
    from patera.caching.backends.redis_cache_backend import RedisCacheBackend

    backend = RedisCacheBackend.from_configs(
        None,  # type: ignore[arg-type]
        {"REDIS_URL": "redis://localhost:6379/0"},
    )
    assert backend._prefix == "patera:cache:"
    client = fakeredis.FakeAsyncRedis()
    backend._client = client
    await client.set("sessions:abc", b"belongs to another app")
    await backend.set("page", {"a": 1})
    assert await client.exists("patera:cache:page")
    await backend.clear()
    assert await backend.get("page") is None
    assert await client.get("sessions:abc") == b"belongs to another app"


async def test_redis_clear_without_prefix_refuses_to_flush():
    fakeredis = pytest.importorskip("fakeredis")
    from patera.caching.backends.redis_cache_backend import RedisCacheBackend

    backend = RedisCacheBackend.from_configs(
        None,  # type: ignore[arg-type]
        {"REDIS_URL": "redis://localhost:6379/0", "KEY_PREFIX": ""},
    )
    client = fakeredis.FakeAsyncRedis()
    backend._client = client
    await client.set("sessions:abc", b"keep me")
    await backend.set("page", {"a": 1})
    with pytest.raises(RuntimeError, match="KEY_PREFIX"):
        await backend.clear()
    assert await client.get("sessions:abc") == b"keep me"


async def test_memory_backend_honours_long_per_entry_durations(monkeypatch):
    backend = MemoryCacheBackend(default_ttl=10)
    now = [1000.0]
    monkeypatch.setattr(MemoryCacheBackend, "_now", staticmethod(lambda: now[0]))
    await backend.set("long", {"v": 1}, duration=3600)
    await backend.set("default", {"v": 2})
    now[0] += 60  # past the default TTL, within the long duration
    assert await backend.get("long") == {"v": 1}
    assert await backend.get("default") is None
    now[0] += 3600
    assert await backend.get("long") is None
    await backend.set("never", {"v": 3}, duration=0)
    assert await backend.get("never") is None


class OtherSqliteCache(Caching):
    backend_class = SQLiteCacheBackend


def test_shared_backends_get_a_prefix_per_application_and_cache(make_app, tmp_path):
    from patera.caching.backends.redis_cache_backend import RedisCacheBackend

    path = str(tmp_path / "shared.db")
    app = make_app(
        extensions=[SqliteCache, OtherSqliteCache],
        SQLITE_CACHE=CachingConfig(SQLITE_PATH=path),
        OTHER_SQLITE_CACHE=CachingConfig(SQLITE_PATH=path),
    )
    first = app.get_extension(SqliteCache)
    second = app.get_extension(OtherSqliteCache)
    assert first.cache_name == "sqlite_cache"
    assert first.backend._prefix == "patera:test_app:sqlite_cache:"
    assert second.backend._prefix == "patera:test_app:other_sqlite_cache:"

    redis = RedisCacheBackend.from_configs(
        app, {"REDIS_URL": "redis://localhost:6379/0"}, namespace="public_cache"
    )
    assert redis._prefix == "patera:test_app:public_cache:"


async def test_clearing_one_sqlite_cache_keeps_the_other(make_app, tmp_path):
    path = str(tmp_path / "shared.db")
    app = make_app(
        extensions=[SqliteCache, OtherSqliteCache],
        SQLITE_CACHE=CachingConfig(SQLITE_PATH=path),
        OTHER_SQLITE_CACHE=CachingConfig(SQLITE_PATH=path),
    )
    first = app.get_extension(SqliteCache).backend
    second = app.get_extension(OtherSqliteCache).backend
    await first.connect()
    await second.connect()
    try:
        await first.set("page", {"from": "first"})
        await second.set("page", {"from": "second"})
        assert await first.get("page") == {"from": "first"}
        await first.clear()
        assert await first.get("page") is None
        assert await second.get("page") == {"from": "second"}
    finally:
        await first.disconnect()
        await second.disconnect()


async def test_sqlite_clear_treats_like_wildcards_literally(tmp_path):
    path = str(tmp_path / "w.db")
    narrow = SQLiteCacheBackend(db_path=path, key_prefix="a_b")
    other = SQLiteCacheBackend(db_path=path, key_prefix="axb")
    await narrow.connect()
    await other.connect()
    try:
        await other.set("k", {"v": 1})
        await narrow.clear()
        assert await other.get("k") == {"v": 1}
    finally:
        await narrow.disconnect()
        await other.disconnect()


class Item(BaseModel):
    name: str
    added: datetime.date


@path("/stored")
class StoredController(Controller):
    @get("/")
    @cache("SQLITE_CACHE", key="items")
    async def items(self, req: Request) -> Response[list[Item]]:
        CALLS["stored"] = CALLS.get("stored", 0) + 1
        return req.res.json(
            [{"name": "a", "added": datetime.date(2026, 1, 2), "secret": "x"}]
        )


async def test_cache_stores_the_sent_bytes_as_json(make_app, client_for, tmp_path):
    import base64
    import json
    import sqlite3

    CALLS.clear()
    app = make_app(
        controllers=[StoredController],
        extensions=[SqliteCache],
        SQLITE_CACHE=CachingConfig(
            SQLITE_PATH=str(tmp_path / "cache.db"), KEY_PREFIX="t"
        ),
    )
    expected = [{"name": "a", "added": "2026-01-02"}]
    async with client_for(app) as client:
        first = await client.get("/stored/")
        second = await client.get("/stored/")
    assert first.json() == second.json() == expected
    assert second.headers["content-type"] == "application/json; charset=utf-8"
    assert CALLS["stored"] == 1

    with sqlite3.connect(tmp_path / "cache.db") as conn:
        (raw,) = conn.execute("SELECT v FROM cache_entries").fetchone()
    payload = json.loads(raw)  # plain JSON, not pickle
    # The stored body is what was sent: filtered through Response[list[Item]].
    assert json.loads(base64.b64decode(payload["body"])) == expected


async def test_unreadable_entries_are_misses(tmp_path):
    backend = SQLiteCacheBackend(db_path=str(tmp_path / "c.db"))
    await backend.connect()
    try:
        await backend.set("k", {"a": 1})
        assert backend._conn is not None
        await backend._conn.execute(
            "UPDATE cache_entries SET v = ?", (b"\x80\x04 not json",)
        )
        await backend._conn.commit()
        assert await backend.get("k") is None
    finally:
        await backend.disconnect()
