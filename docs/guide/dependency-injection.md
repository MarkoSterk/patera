# Services and dependency injection

Application services are subclasses of `BaseExtension` (alias: `Service`). Each service is a
**singleton per application**. Declare dependencies with `Inject[...]` on the application class,
controllers, services, middleware, exception handlers or CLI controllers: they are created on
first use and shared.

```python
from typing import TYPE_CHECKING

from pydantic import BaseModel

from patera import Request, Response, Service
from patera.controller import Controller, get, path
from patera.injectable import ConfigVar, Inject

if TYPE_CHECKING:
    from app import App


class GreetingSettings(BaseModel):
    PREFIX: str = "Hello"


class Formatter(Service["App"]):
    def format(self, prefix: str, name: str) -> str:
        return f"{prefix}, {name}!"


class GreetingService(Service["App", GreetingSettings]):
    formatter: Inject[Formatter]

    def init(self) -> None:          # called after construction
        self.greeted = 0

    def greet(self, name: str) -> str:
        self.greeted += 1
        return self.formatter.format(self.configs.PREFIX, name)


@path("/greetings")
class GreetingApi(Controller["App"]):
    greetings: Inject[GreetingService]
    app_name: str = ConfigVar("APP_NAME")

    @get("/<name>")
    async def greet(self, req: Request, name: str) -> Response:
        return req.res.text(self.greetings.greet(name))
```

## How resolution works

- Dependencies are class annotations, resolved before `init()` on services and before
  `@after_init` hooks on controllers.
- There is one instance per application, with **no request or transient scope**. Do not store
  the current user, request or database session on a service.
- Registry keys derive from class names; distinct classes with the same name collide.
- Injectable classes must accept the application as their only constructor argument. Wrap
  libraries that need other constructor arguments in a service.
- Circular dependencies are reported with `CircularDependencyError` instead of providing
  partially initialized objects. Break them by separating responsibilities.
- Injection also works with `from __future__ import annotations`, as long as the injected class
  is importable at runtime (not only under `TYPE_CHECKING`).

### Interfaces and implementations

There is no automatic resolution by superclass. For an interface with a concrete
implementation, use `Autowire`:

```python
from typing import TYPE_CHECKING, Annotated

from patera.injectable import Autowire, Inject

if TYPE_CHECKING:
    from app import App


class NotesApi(Controller["App"]):
    storage: Annotated[Storage, Autowire(FileStorage)]
```

## Service configuration

`self.configs` of a service returns the configuration field named after the class in
UPPER_SNAKE_CASE (`GreetingService` → `GREETING_SERVICE`). The second type argument of
`Service[...]` / `BaseExtension[...]` declares the configuration model, which means:

- a configuration model instance in the config class is used as is,
- a plain dict (for example from `PATERA_GREETING_SERVICE__PREFIX=Hi`) is validated with the model,
- a missing configuration falls back to the model's defaults, or raises a clear error if the
  model has required fields.

```python
class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    GREETING_SERVICE: GreetingSettings = GreetingSettings(PREFIX="Welcome")
```

## Creating services at startup

Services that must exist from startup (for example to register hooks or middleware) are listed
in `App.app_extensions`; others are created when they are first injected. List order alone does
not establish all dependency ordering, since injection can construct a service earlier.

Retrieve any service with `app.get_extension(GreetingService)`.

To write reusable services with their own controllers, middleware and lifecycle hooks, see
[Custom extensions](custom-extensions.md).
