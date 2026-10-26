# The application class

The application is a subclass of `Patera`, decorated with `@app`:

```python
from patera import Patera, app, on_shutdown, on_startup
from patera.injectable import Inject

from .configs import Config
from .database import Databases
from .services.greetings import GreetingService


@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Databases]   # extensions created at startup
    greetings: Inject[GreetingService]

    @on_startup
    async def start(self) -> None:
        self.logger.info("Starting")

    @on_shutdown
    async def stop(self) -> None:
        self.logger.info("Stopping")
```

- `@app(__name__, configs=Config)` supplies runtime metadata. The import name determines the
  application root used for discovery, templates and static files.
- `Patera[Config]` supplies typing for `self.configs`.
- `BASE_PATH` is a directory, not a URL prefix. Use `URL_PREFIX` for controller URLs.

## Lifecycle hooks

Methods decorated with `@on_startup` and `@on_shutdown` run during the ASGI lifespan.

- Startup and shutdown hooks run in **alphabetical order of their method names**. Use a single
  hook per event that calls other methods in the order you need.
- If a startup hook raises, the server is notified that startup failed.
- Extensions add their own hooks with `app.add_on_startup_method(...)` and
  `app.add_on_shutdown_method(...)`; these are appended after the application's startup hooks.
  Do not assume a database is connected in an application startup hook.
- Construction is distinct from the lifespan: calling `App()` does not run the hooks. Servers,
  `patera dev`/`prod` and `PateraTestClient` run them.

## Extensions

Infrastructure services listed in `app_extensions` are constructed even if nothing injects them.
Other services are created on first injection. See
[Services and dependency injection](dependency-injection.md).

## Background tasks

`run_in_background()` from `patera` starts short local work that should not delay the response.
Running tasks are tracked, and shutdown waits for them up to `BACKGROUND_TASKS_SHUTDOWN_TIMEOUT`
seconds (default `10.0`, `None` for no limit) before cancelling them.

!!! warning

    Background tasks are not a durable queue. Pass plain data and acquire fresh resources inside
    the task: a copied context does not extend the lifetime of a request's database session.
    For scheduled or persistent work, use the [task manager](../extensions/taskmanager.md).

## Useful members

| Member | Description |
| --- | --- |
| `configs`, `get_conf(name, default=None)` | configuration |
| `url_for(endpoint, **params)` | URL of an endpoint (`"Controller.method"`, `"alias.method"`, `"static"`) |
| `get_extension(cls)`, `extensions` | registered extensions/services |
| `get_controller(cls_or_name)`, `controllers` | registered controller instances |
| `register_controller(*classes)` | register controllers manually |
| `register_exception_handler(*classes)` | register exception handlers manually |
| `register_middleware(cls, order=None)` | register middleware manually (before the first request) |
| `add_template_path(path)` | additional template folder |
| `add_on_startup_method(fn)`, `add_on_shutdown_method(fn)` | lifespan hooks |
| `add_request_observer(fn)` | observe every completed HTTP request (see [Logging](logging.md#request-observers)) |
| `json_spec` | the OpenAPI specification (dict) |
| `logger` | the [Loguru](https://loguru.readthedocs.io) logger |
| `root_path`, `static_files_path`, `app_name`, `version` | paths and metadata |
| `url_prefix` | the `URL_PREFIX` setting (`""` without a prefix) |
| `default_exception_response(req, exc)` | override to customize the [default error responses](exception-handling.md#default-responses) |

## Custom request and response classes

Set `REQUEST_CLASS` / `RESPONSE_CLASS` in the configuration to use subclasses of `Request` and
`Response` throughout the application.
