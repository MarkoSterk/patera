# Project layout and auto-discovery

When the application is created, Patera imports modules from well-known folders inside the
application package and registers the classes it finds. A module is imported if its **folder**
and **file name** match:

| Kind | Folders | File name contains | Registered when |
| --- | --- | --- | --- |
| Controllers | `api`, `public`, `controllers`, `routers`, `routes` | `api`, `controller`, `public`, `router`, `routes` | decorated with `@path` |
| Exception handlers | `exceptions`, `exc_controllers` | `handler`, `exception_controller`, `controller` | decorated with `@exception_handler` |
| Middleware | `middleware`, `middlewares` | `middleware`, `mw` | decorated with `@middleware` |
| CLI controllers | `cli`, `cli_controllers`, `clis` | `cli`, `cli_controller` | decorated with `@cli_controller` (CLI mode only) |
| Loggers | `logging`, `loggers` | `logger`, `log_sink`, `logging` | decorated with `@logger` |

Folders are searched recursively. Include `__init__.py` files so the folders are packages.

A typical project:

```text
app/
  __init__.py                              # @app class App(Patera[Config])
  configs.py
  api/
    __init__.py
    greeting_api.py                        # controllers
  controllers/
    page_controller.py
  middleware/
    request_id_middleware.py               # middleware
  exceptions/
    app_exception_handler.py               # exception handlers
  cli/
    tools_cli.py                           # CLI controllers
  logging/
    audit_logger.py                        # additional log sinks
  services/                                # not discovered: import what you use
  templates/
  static/
```

!!! note "Models and services are not discovered"

    Only the component kinds above are discovered. Services, database models and other modules
    are used through imports and [dependency injection](../guide/dependency-injection.md).

## Controlling discovery

- Add folders with the `CONTROLLER_FOLDERS`, `CLI_CONTROLLER_FOLDERS`,
  `EXCEPTION_HANDLER_FOLDERS`, `MIDDLEWARE_FOLDERS` and `LOGGER_FOLDERS` options.
- Classes marked with `@ignore` are skipped.
- Classes (and endpoint methods) marked with `@development` are only registered when `DEBUG` is on.
- Anything can also be registered explicitly with the `register_*` methods of the
  [application](../guide/application.md): `register_controller(...)`,
  `register_exception_handler(...)`, `register_middleware(...)`.

```python
from typing import TYPE_CHECKING

from patera import development, ignore
from patera.controller import Controller, get, path

if TYPE_CHECKING:
    from app import App


@path("/debug")
@development              # only exists with DEBUG=True
class DebugApi(Controller["App"]):
    ...


@ignore                   # never registered
@path("/legacy")
class LegacyApi(Controller["App"]):
    ...
```

## Application package name

The application package is called `app` by default. If yours has another name, set the
`APP_PACKAGE` option and the `PATERA_APP_PACKAGE` environment variable for the `patera`
command (see [Running the application](running.md)).
