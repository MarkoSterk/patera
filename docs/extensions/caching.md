# Caching

`patera-caching` caches endpoint responses with in-memory, Redis and SQLite backends.

```sh
uv add "patera[caching]"            # in-memory backend
uv add "patera[caching-redis]"      # + Redis backend
uv add "patera[caching-sqlite]"     # + SQLite backend
```

## Setup

```python
from patera.caching import Caching, CachingConfig, cache


class PublicCache(Caching):
    pass                                 # in-memory backend by default


class Config(BaseConfig):
    ...
    PUBLIC_CACHE: CachingConfig = CachingConfig(DURATION=60, MAX_SIZE=1000)


@path("/stats")
class StatsApi(Controller[App]):
    @get("/")
    @cache("PUBLIC_CACHE", duration=15)  # registered name of the extension
    async def stats(self, req: Request) -> Response:
        return req.res.json(await compute_stats())
```

Register `PublicCache` in `app_extensions`. Put `@cache` directly above the handler (below
`@get`).

The default in-memory backend is per instance, bounded in size and with expiry. It is neither
shared across worker processes nor persistent across restarts.

## What is cached

- Only `GET` and `HEAD` are cached by default. Opt into `POST` explicitly for read-only RPC
  operations with `@cache("PUBLIC_CACHE", methods=("POST",))`; cache hits skip the handler, and
  opted-in methods include a SHA-256 body digest in the key.
- Only successful (`< 400`), non-streaming responses without cookies are cached; file sends are
  skipped too.
- The body is stored as it is sent, already serialized (through `Response[Model]`), and replayed
  with the status, headers and media type on a hit.

## Keys

The default key combines the handler's module and qualified name, the method, the path and the
ordered query string, plus a user identity suffix when a user is loaded.

`key` accepts a string or a sync/async callable taking the `Request`:

```python
@cache("PUBLIC_CACHE", key=lambda req: f"page:{req.path}:{req.headers.get('accept-language', '')}")
```

A custom key replaces the default URL/handler key, so include every relevant variation. Body
digests and user partitioning still apply.

!!! warning "Cache only public data"

    Use `per_user=False` only for genuinely shared results. Per-user separation needs a loaded
    user with a stable identity, and public routes normally skip user loading. Tenant, language
    or permission variants may need custom keys.

## Manual use

```python
await cache.get(key, req)
await cache.set(key, response, duration)
await cache.delete(key)
await cache.delete("users:*", wildcard=True)
await cache.delete(r"^users:\d+$", regex=True)
await cache.clear()
```

Invalidate on writes with `delete`/`clear` or by using revisioned keys.

## Backends

Other backends are chosen with `backend_class`; the extension creates them from its settings
with `backend_class.from_configs(app, configs, namespace)`:

```python
from patera.caching.backends.redis_cache_backend import RedisCacheBackend


class SharedCache(Caching):
    backend_class = RedisCacheBackend   # SHARED_CACHE = {"REDIS_URL": ..., "DURATION": 60}
```

- Keys in Redis and SQLite live under `KEY_PREFIX`, by default `patera:<app name>:<cache name>:`
  (for example `patera:blog:shared_cache:`), so several caches or applications can share one
  store, and `clear()` only removes its own keys.
- The Redis and SQLite backends store JSON (the serialized body as base64 text), so reading an
  entry never runs code; an entry that cannot be read counts as a miss.
- To build a backend yourself, assign `self.backend` in `init()` before calling `super().init()`.
- Custom backends implement `patera.caching.BaseCacheBackend` (`encode_payload()` /
  `decode_payload()` convert a payload).
