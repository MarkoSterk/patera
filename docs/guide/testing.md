# Testing

`patera.testing.PateraTestClient` runs the application (including startup and shutdown hooks)
and sends requests through [HTTPX](https://www.python-httpx.org). It needs the `testing` extra,
which also installs pytest and pytest-asyncio:

```sh
uv add --dev "patera[testing]"
```

## A first test

```python
# tests/conftest.py
import pytest

from patera.testing import PateraTestClient
from app import App


@pytest.fixture
async def client():
    async with PateraTestClient(App()) as c:
        yield c
```

```python
# tests/test_users.py
async def test_list_users(client):
    res = await client.get("/api/v1/users/")
    assert res.status_code == 200
```

The client offers `get`, `post`, `put`, `patch`, `delete`, `head`, `options` and `request`, which
all accept the usual HTTPX keyword arguments such as `json=`, `headers=` and `files=`.

The async context manager runs the lifespan. A bare HTTPX ASGI transport does not run startup
and shutdown hooks.

## Configure pytest

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

## Run the tests

```sh
uv run patera test              # loads .env.test if present
uv run patera test -k login -q  # pytest options in any order
uv run patera test -- -x        # everything after -- goes to pytest unchanged
uv run pytest                   # plain pytest
```

`patera test --env-file FILE` loads another environment file, which must exist.

## Good practice

- Set test configuration and environment variables **before** constructing the app.
- Use a fresh app and isolated databases, files and caches for independent tests.
- Test production error behaviour with `DEBUG` disabled when asserting generic `500` bodies.
- Cover input failures, authorization, transaction commit/rollback, response models and lifecycle
  cleanup.
- Mock external SMTP, HTTP and AI transports instead of sending real requests.
- Use a socket harness for [WebSockets](websockets.md) and isolated argv/output/filesystem for
  [CLI commands](cli.md).
