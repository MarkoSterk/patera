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
