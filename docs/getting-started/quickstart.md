# Quick start

A Patera project is a Python package, by default called `app`:

```text
my-app/
  app/
    __init__.py          # the application class
    configs.py           # configuration
    api/
      __init__.py
      greeting_api.py    # controllers are discovered automatically
    templates/
    static/
  .env
  pyproject.toml
```

## 1. Configuration

`app/configs.py`:

```python
import os

from patera import BaseConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)  # required
    APP_NAME: str = "My app"
    VERSION: str = "1.0.0"
```

`BASE_PATH` is the directory of the application package. Every option can also be set from the
environment; see [Configuration](../guide/configuration.md).

## 2. The application class

`app/__init__.py`:

```python
from patera import Patera, app

from .configs import Config


@app(__name__, configs=Config)
class App(Patera[Config]):
    pass
```

`@app` supplies the runtime metadata (the import name and the configuration class); the generic
argument `Patera[Config]` gives your editor and type checker the configuration type.

## 3. A controller

`app/api/greeting_api.py`:

```python
from pydantic import BaseModel

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import Controller, consumes, get, path, post, produces

from app import App


class Greeting(BaseModel):
    name: str


@path("/api/v1/greetings")
class GreetingApi(Controller[App]):
    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def hello(self, req: Request) -> Response:
        return req.res.json({"message": "Hello, World!"})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    async def greet(self, req: Request, greeting: Greeting) -> Response:
        return req.res.json({"message": f"Hello, {greeting.name}!"})
```

The controller lives in an `api` folder and its file name contains `api`, so Patera
[discovers it](project-layout.md) automatically.

## 4. Run it

```sh
uv run patera dev
```

Open <http://localhost:3000/api/v1/greetings/>. Send a `POST` with a JSON body
`{"name": "Ana"}` to the same URL to call `greet`; an invalid body is answered with `422` and
the validation errors.

The generated API documentation is available at <http://localhost:3000/openapi/docs>.

## Where to go next

- [Project layout](project-layout.md): which folders and file names are discovered.
- [Controllers](../guide/controllers.md): routes, parameters, validation and hooks.
- [Services and dependency injection](../guide/dependency-injection.md): structure your
  business logic.
- [Testing](../guide/testing.md): test your endpoints with `PateraTestClient`.
