# Custom extensions

```python
from patera import BaseExtension, Patera
from pydantic import BaseModel

class AuditConfig(BaseModel):
    ENABLED: bool = True

class AuditService(BaseExtension[Patera, AuditConfig]):
    def init(self) -> None:
        if self.configs.ENABLED:
            self.app.add_on_startup_method(self.start)
            self.app.add_on_shutdown_method(self.stop)

    async def start(self) -> None:
        self.app.logger.info("Audit started")

    async def stop(self) -> None:
        self.app.logger.info("Audit stopped")
```

Declare `AUDIT_SERVICE: AuditConfig = AuditConfig()` on app Config for nested
environment settings. Register the class in `app_extensions` or inject it.
The two generic parameters are application type then configuration type.

Construction resolves injections, registers the instance, then calls synchronous
`init`. Prefer that hook over overriding `__init__`. In `init`, register controller
classes, middleware classes, exception handler classes, CLI controller instances,
URL aliases, template paths and lifecycle callbacks through the application's
public methods. Register middleware before the chain is built. Do not import the
concrete application into a reusable extension.

Registration is provisional until `init` succeeds. Failed construction rolls
back framework registries, routes, template paths and lifecycle hooks, including
nested dependency registrations. Injection rejects instances still initializing.
This cannot undo arbitrary external side effects: acquire resources in startup,
or clean them up in the extension if its initialization fails.

Acquire resources in startup and close them in shutdown; CLI users must explicitly
manage resources. Preserve instance independence across test applications. Keep
request state in context. Validate settings rather than silently ignoring invalid
values. Extension class names must not collide within one app.

Publish reusable extensions as separate distributions. Official packages install
under the `patera` namespace, whose path is extended by the core; a third-party
package can use its own import namespace. Include templates/static resources in
the distribution and test an installed artifact, not only editable sources.

Sources: tutorial chapter 16; architecture chapter 15.
