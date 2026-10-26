# External APIs

`patera-apiinterface` turns annotated methods into HTTP calls with
[HTTPX](https://www.python-httpx.org): declarative async clients for external APIs.

```sh
uv add "patera[apiinterface]"
```

```python
from patera import HttpMethod
from patera.apiinterface import ApiInterface, AuthType, auth, headers, method, resource, service, timeout


@service("GITHUB_URL")                         # config key or literal URL
@auth(AuthType.BEARER, token="GITHUB_TOKEN")   # config key or literal value
@headers({"X-Client": "my-app"})
@timeout(10)
class GithubApi(ApiInterface):

    @method(HttpMethod.GET)
    @resource("/repos/<repo_id>")              # filled from the argument of the same name
    async def get_repo(self, repo_id: int) -> Repo: ...   # Pydantic return types are validated

    @method(HttpMethod.POST)
    @resource("/repos")
    async def create_repo(self, name: str, private: bool) -> dict: ...   # arguments become the JSON body
```

Declare `GITHUB_URL` and `GITHUB_TOKEN` on your config and inject the interface. Decorated method
bodies are replaced by wrappers, so put business logic in a separate service.

## Arguments

- Arguments fill `<name>` placeholders in the resource (encoded).
- The remaining arguments become query parameters for `GET` and `HEAD`, and the body otherwise.
- `@consumes` / `@produces` select the body and response formats, including form data and file
  uploads. These are the API interface's decorators, not the controller decorators of the same
  name.

## Authentication

`@auth` supports `AuthType.BEARER`, `AuthType.BASIC_AUTH` and `AuthType.API_KEY`. Class-level
defaults can be overridden on methods; `@no_auth` disables inherited authentication for one
method.

`@forward_request` (on a method or the class) additionally forwards the current request's query
string and fills placeholders from its route parameters. Forwarding is explicit, so incoming
credentials and query values are not passed on by accident.

## Responses and errors

- A Pydantic return annotation validates the remote data.
- A 4xx or 5xx answer raises `ApiInterfaceResponseError` with `status_code`, the decoded `body`
  and the `response`.
- Annotate a method with `-> httpx.Response` to receive every response unchecked; the caller
  must then inspect it.

## Client lifecycle

- Within an application lifespan, an interface reuses one HTTP client and closes it at shutdown.
- Standalone and CLI calls use temporary clients, closed before the call returns, including on
  failures.
- If you acquire `interface.client` explicitly, call `await interface.aclose()` in that same
  event loop before it closes. Access from another loop raises instead of discarding an unclosed
  client.
- Override `create_client()` for transport mocks or limits. Test with an HTTPX mock transport,
  including error and timeout behaviour.
