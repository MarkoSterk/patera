# Services and dependency injection

```python
from typing import TYPE_CHECKING

from patera import Service, Request, Response
from patera.injectable import Inject
from patera.controller import Controller, path, get

if TYPE_CHECKING:
    from app import App


class GreetingService(Service["App"]):
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"

@path("/hello")
class HelloController(Controller["App"]):
    greetings: Inject[GreetingService]

    @get("/<name>")
    async def hello(self, req: Request, name: str) -> Response:
        return req.res.json({"message": self.greetings.greet(name)})
```

`Service` is an alias for `BaseExtension`. Dependencies are class annotations,
resolved before `init()` on extensions and `@after_init` hooks on controllers.
Use concrete, runtime-importable types. Avoid hiding injected types behind
`TYPE_CHECKING`; unresolved string annotations can prevent discovery of injection
metadata. Check existing annotations before introducing postponed evaluation.

There is one instance per application, with no transient/request injection scope.
Do not store current users, requests, or sessions on those instances. Registry
keys derive from class names; distinct classes with the same name collide.
There is no automatic resolution by superclass. For an interface with a concrete
implementation use `Annotated[Interface, Autowire(Implementation)]`, importing
`Annotated` from `typing` and `Autowire` from `patera.injectable`.

Injectable classes must accept the application as their constructor argument.
Wrap libraries requiring additional constructor arguments in a service. Break
circular dependencies by separating responsibilities; the resolver reports
`CircularDependencyError` rather than providing partially initialized objects.

Sources: tutorial chapter 2; architecture chapter 6.
