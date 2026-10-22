# Declarative HTTP clients

Install `patera-apiinterface`. Use its decorators, not the similarly named
incoming-controller decorators:

```python
from patera import HttpMethod
from patera.apiinterface import ApiInterface, service, resource, method

@service("CATALOGUE_URL")
class Catalogue(ApiInterface):
    @resource("/items/<item_id>")
    @method(HttpMethod.GET)
    async def item(self, item_id: int) -> dict:
        ...
```

Declare `CATALOGUE_URL` on Config and inject the interface. Decorated method bodies
are replaced by wrappers: put business logic in a separate service. Named path
arguments fill and encode placeholders. Remaining GET/HEAD arguments become query
parameters; other methods use body serialization selected by `@consumes`.
Class-level defaults can be overridden on methods; `@no_auth` removes inherited
authentication. Do not forward incoming credentials/query values accidentally;
request forwarding is explicitly enabled with `@forward_request`.

Pydantic return models validate remote data. Remote 4xx/5xx raise
`ApiInterfaceResponseError`; a declared `httpx.Response` return bypasses that
automatic checking so the caller must inspect it. Keep remote failures distinct
from successful application data.

The HTTPX client is shared and loop-aware. ASGI shutdown closes it. CLI and other
non-lifespan callers must `await interface.aclose()` in `finally`. Override
`create_client()` for transport mocks/limits. Bound destination URLs and keep
credentials in settings. Test with an HTTPX mock transport, including error and
timeout behavior, without contacting a production provider.

Sources: tutorial chapter 15; architecture chapter 18.
