# Custom extensions

Extensions are [services](dependency-injection.md) that plug into the application: they can
register controllers, middleware, exception handlers, CLI commands, template folders and
lifecycle hooks. The official [extension packages](../extensions/index.md) are built this way.

```python
from typing import TYPE_CHECKING

from pydantic import BaseModel

from patera import BaseExtension

if TYPE_CHECKING:
    from app import App


class AuditConfig(BaseModel):
    ENABLED: bool = True


class AuditService(BaseExtension["App", AuditConfig]):
    def init(self) -> None:
        if self.configs.ENABLED:
            self.app.add_on_startup_method(self.start)
            self.app.add_on_shutdown_method(self.stop)

    async def start(self) -> None:
        self.app.logger.info("Audit started")

    async def stop(self) -> None:
        self.app.logger.info("Audit stopped")
```

Declare `AUDIT_SERVICE: AuditConfig = AuditConfig()` on the application's config for nested
environment settings, and register the class in `app_extensions` or inject it. The two generic
parameters are the application type, then the configuration type.

## Construction and `init()`

Construction resolves injections, registers the instance, then calls the synchronous `init()`.
Prefer that hook over overriding `__init__`. In `init()`, use the application's public methods:

| Register | Method |
| --- | --- |
| controller classes | `app.register_controller(...)` |
| middleware classes (before the chain is built) | `app.register_middleware(cls, order)` |
| exception handler classes | `app.register_exception_handler(...)` |
| CLI controller instances | `app.register_cli_controller(instance)` |
| template folders | `app.add_template_path(path)`, `app.add_template_prefix(prefix, path)` |
| lifecycle callbacks | `app.add_on_startup_method(fn)`, `app.add_on_shutdown_method(fn)` |
| request observers | `app.add_request_observer(fn)` |

Registration is provisional until `init()` succeeds. A failed construction rolls back framework
registries, routes, template paths and lifecycle hooks, including nested dependency
registrations, and injection rejects instances still initializing. This cannot undo arbitrary
external side effects: acquire resources in startup, or clean them up yourself if initialization
fails.

## Guidelines

- Acquire resources in startup and release them in shutdown. CLI users must manage resources
  explicitly, because commands do not run the lifespan.
- Keep request state in the [request context](requests.md#request-context), never on the instance.
- Keep instances independent, so several test applications can coexist.
- Validate settings rather than silently ignoring invalid values.
- Extension class names must not collide within one application.
- Do not import the concrete application into a reusable extension; type against `Patera`.

## Publishing an extension

Publish reusable extensions as separate distributions. Official packages install under the
`patera` namespace, whose path is extended by the core; a third-party package can use its own
import namespace. Include templates and static resources in the distribution and test an
installed artifact, not only editable sources. Follow the naming conventions in the
[public API reference](../reference/public-api.md).
