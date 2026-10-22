# Testing

Install `patera[testing]` in development dependencies. Use the project's test
configuration and an importable tests package where necessary.

```python
import pytest
from patera.testing import PateraTestClient
from app import App

@pytest.mark.asyncio
async def test_endpoint():
    async with PateraTestClient(App()) as client:
        response = await client.get("/hello/Ada")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello, Ada!"}
```

Adapt the URL/body to the real endpoint. The async context manager runs startup
and shutdown. Bare HTTPX ASGI transport does not provide lifespan automatically.
Set test configuration/environment **before** constructing the app. Use a fresh
app and isolated database/files/cache for independent tests. Explicitly test
production error behavior with DEBUG disabled when asserting generic 500 bodies.

`patera test` runs pytest and loads `.env.test` if present. An explicit
`--env-file` must exist. It forwards pytest options, e.g.
`patera test -q -k greeting`; arguments after `--` all go to pytest.

Cover changed observable behavior: input failures, authorization, transaction
commit/rollback, response typing, lifecycle cleanup, and concurrent state where
relevant. Mock external SMTP/HTTP/AI transports rather than sending real requests.
Use a socket harness for WebSockets and isolated argv/output/filesystem for CLI.

Sources: tutorial chapter 7; architecture chapter 14.
