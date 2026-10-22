# Response caching

Install `patera-caching`. Subclass `Caching`, e.g. `PublicCache`, register it,
and declare `PUBLIC_CACHE: CachingConfig`. The default backend is per-instance
memory with bounded size and expiry; it is neither shared across workers nor
persistent across restarts. Redis/SQLite backends need their corresponding extras.

```python
from patera.caching import cache

@get("/statistics")
@cache("PUBLIC_CACHE", duration=15, per_user=False)
async def statistics(self, req: Request) -> Response:
    return req.res.json({"count": await self.notes.count()})
```

This is a controller method fragment. Use `per_user=False` only for genuinely
shared results. The default key includes handler, method, path and ordered query
values plus a user identity suffix. Per-user separation requires an actually
loaded user and a stable unique identity; public routes normally skip user loading.
Tenant/language/permission variants may need custom keys. A literal key replaces
the normal base calculation.

The decorator snapshots the serialized response before later hooks/middleware.
It skips errors, streaming, file sends and responses setting cookies at that
point; explicit `set` calls require their own sharing decision. Do not use it for
account responses merely because a guard runs first.

Invalidate on writes through delete/clear or revisioned keys. `delete` supports
keys/patterns; inspect matching behavior before removing broad sets. Test misses,
hits, expiry, invalidation and cross-user separation. Cached data uses bytes/JSON,
not executable pickle payloads. Backend lifecycle follows app lifespan.

Sources: tutorial chapters 14 and 19; architecture chapter 18.
