# patera-apiinterface

Declarative async HTTP clients for external APIs in Patera applications. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-apiinterface
# or, with uv
uv add "patera[apiinterface]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

`patera-apiinterface` turns annotated methods into HTTP calls (with [HTTPX](https://www.python-httpx.org)):

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

See the [External APIs section of the Patera documentation](https://github.com/MarkoSterk/Patera#external-apis) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
