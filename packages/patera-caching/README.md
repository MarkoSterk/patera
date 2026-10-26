# patera-caching

Response caching for Patera with in-memory, Redis and SQLite backends. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-caching
# or, with uv
uv add "patera[caching]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

Only GET and HEAD are cached by default. Opt into POST explicitly with
`@cache("PUBLIC_CACHE", methods=("POST",))` for read-only RPC operations; cache
hits skip the handler. Opted-in methods include a SHA-256 body digest in the key.
Default keys contain the handler's module and qualified name, method, path and
query. Existing entries with the former short-name keys expire naturally; update
manual invalidation patterns to include the qualified name.

`key` accepts a string or a sync/async callable taking `Request`. For example,
`key=lambda req: f"page:{req.path}:{req.headers.get('accept-language', '')}"`
separates language variants. A custom key replaces the default URL/handler key,
so include every relevant variation. Body digests and default user partitioning
still apply. User partitioning alone does not account for headers or other
request-dependent data.

`patera-caching` caches responses of endpoints:

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

See the [Caching section of the Patera documentation](https://github.com/MarkoSterk/Patera#caching) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
