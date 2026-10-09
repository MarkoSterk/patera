<p align="center">
  <img src="https://raw.githubusercontent.com/MarkoSterk/Patera/refs/heads/main/src/patera/graphics/patera_logo.png" alt="Patera Logo" width="200">
</p>

# Patera - async-first Python web framework

Patera is a modular, async-first ASGI web framework with a structure inspired by Java frameworks:
class-based controllers, decorators for routing and HTTP semantics, dependency injection of
application services, and typed configuration objects.

The core package handles routing, requests/responses, validation, templates, static files, CORS,
middleware, OpenAPI documentation, logging, a CLI and a test client. Optional packages add SQL
databases, migrations, authentication, caching, scheduled tasks, e-mail, declarative API clients,
an AI interface, an admin dashboard and a desktop launcher.

> Patera is in an early (alpha) stage. The API may still change between versions.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Running the application](#running-the-application)
- [Configuration](#configuration)
- [The application class](#the-application-class)
- [Project layout and auto-discovery](#project-layout-and-auto-discovery)
- [Controllers](#controllers)
- [Requests and responses](#requests-and-responses)
- [Routing behaviour](#routing-behaviour)
- [Services and dependency injection](#services-and-dependency-injection)
- [Exception handling](#exception-handling)
- [Templates](#templates)
- [Static files and static pages](#static-files-and-static-pages)
- [CORS](#cors)
- [Middleware](#middleware)
- [OpenAPI](#openapi)
- [Logging](#logging)
- [Command line interface](#command-line-interface)
- [Testing](#testing)
- [Extensions](#extensions)
- [Developing Patera](#developing-patera)

## Installation

Patera requires Python 3.13 or newer. We recommend [uv](https://docs.astral.sh/uv/):

```sh
uv init --python 3.13 my-app
cd my-app
uv add "patera[dev]"     # core + uvicorn/watchfiles for the development server
```

or with pip:

```sh
pip install "patera[dev]"
```

Optional features are installed with extras:

| Extra | Installs | Purpose |
| --- | --- | --- |
| `dev` | uvicorn, watchfiles | development server with auto-reload (`patera dev`) |
| `testing` | pytest, pytest-asyncio, httpx, ... | testing tools (`patera test`) |
| `database` | `patera-database` | async SQLAlchemy integration |
| `migrate` | `patera-migrate` | SQL migrations (pyway) |
| `auth` | `patera-auth` | authentication/authorization middleware |
| `caching` | `patera-caching` | response caching (in-memory) |
| `caching-redis` / `caching-sqlite` | + redis / aiosqlite | Redis or SQLite cache backends |
| `taskmanager` | `patera-taskmanager` | scheduled and background tasks (APScheduler) |
| `email` | `patera-email` | SMTP e-mail client |
| `apiinterface` | `patera-apiinterface` | declarative clients for external HTTP APIs |
| `aiinterface` | `patera-aiinterface` | LLM chat interface (experimental, installs PyTorch) |
| `admin` | `patera-admin` | admin dashboard |
| `desktop` | `patera-desktop` | run the app as a desktop application (pywebview) |
| `all` | all of the above except `desktop` | |

```sh
uv add "patera[database,auth,caching]"
```

## Quick start

A Patera project is a Python package (by default called `app`):

```
my-app/
  app/
    __init__.py          # the application class
    configs.py           # configuration
    api/
      greeting_api.py    # controllers are discovered automatically
    templates/
    static/
  .env
  pyproject.toml
```

`app/configs.py`:

```python
import os

from patera import BaseConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)  # required
    APP_NAME: str = "My app"
    VERSION: str = "1.0.0"
```

`app/__init__.py`:

```python
from patera import Patera, app

from .configs import Config


@app(__name__, configs=Config)
class App(Patera[Config]):
    pass
```

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

Start the development server and open <http://localhost:3000/api/v1/greetings/>:

```sh
uv run patera dev
```

The generated API documentation is available at <http://localhost:3000/openapi/docs>.
A complete small example lives in [`examples/basic_app`](examples/basic_app).

## Running the application

The `patera` command finds your application class automatically (it looks for the class decorated
with `@app` in `app/__init__.py`, `app/app.py`, `app/main.py`, ...). Use `--app module:Class` or the
`PATERA_IMPORT` environment variable to point at it explicitly, and `PATERA_APP_PACKAGE` if your
package is not called `app`.

| Command | Description |
| --- | --- |
| `patera dev [--app app:App] [--env-file .env]` | development server (uvicorn) with auto-reload. Loads `.env`, `.env.dev` or `.env.local` if no file is given. Host/port from `PATERA_HOST`/`PATERA_PORT` (default `localhost:3000`). |
| `patera prod [--app app:App] [--env-file .env.prod]` | production server ([Granian](https://github.com/emmett-framework/granian)), `DEBUG` is forced off. Host/port from `PATERA_HOST`/`PATERA_PORT` (default `0.0.0.0:80`), event loop from `PATERA_LOOP`. |
| `patera cli Controller:command [args...]` | runs a [CLI command](#command-line-interface). |
| `patera test [--env-file .env.test] [pytest args...]` | runs pytest after loading the test environment file. |
| `patera desktop [--mode dev\|prod]` | runs the app as a desktop application (needs `patera-desktop`). |

The application class is an ASGI application factory, so any ASGI server works, e.g.
`uvicorn app:App --factory --lifespan on`. Keep lifespan enabled: startup/shutdown hooks
(database connections, schedulers, ...) depend on it.

## Configuration

Configuration classes inherit from `patera.BaseConfig`, a
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) model.
Every option can be overridden with an environment variable prefixed with `PATERA_`.
Nested values use `__` as separator:

```sh
PATERA_DEBUG=false
PATERA_PORT=8080
PATERA_CORS_ALLOW_ORIGINS='["https://app.example.com"]'
PATERA_MAIN_DB__DATABASE_URI=postgresql+asyncpg://user:pass@db/app
```

Extension and middleware settings are regular fields of your config class, named after the class in
UPPER_SNAKE_CASE (`MainDb` → `MAIN_DB`, `PublicCache` → `PUBLIC_CACHE`). See
[Services and dependency injection](#services-and-dependency-injection).

Read configuration values with `app.configs.NAME`, `app.get_conf("NAME", default)` (supports dotted
paths into nested models and dictionaries: `app.get_conf("MAIN_DB.DATABASE_URI")`) or the
`ConfigVar` descriptor in controllers and services.

Built-in options:

| Option | Default | Description |
| --- | --- | --- |
| `BASE_PATH` | *required* | Directory of the application package (`os.path.dirname(__file__)`). |
| `APP_PACKAGE` | `"app"` | Name of the application package. |
| `APP_NAME` | `"Patera app"` | Human readable name (logs, OpenAPI title). |
| `VERSION` | `"1.0"` | Application version (OpenAPI). |
| `DEBUG` | `True` | Debug mode. Unhandled exceptions propagate in debug mode and become a generic 500 response otherwise. `@development` routes only exist in debug mode. |
| `HOST` / `PORT` / `PROTOCOL` | `"localhost"` / `3000` / `"http"` | Used for the OpenAPI server URL and startup message. |
| `LIFESPAN` | `"on"` | For custom run scripts; `patera dev`/`prod` always enable lifespan. |
| `REQUEST_CLASS` / `RESPONSE_CLASS` | `Request` / `Response` | Custom subclasses of the request/response classes. |
| `TEMPLATES_DIR` | `"templates"` | Template folder, relative to `BASE_PATH`. |
| `TEMPLATES_STRICT` | `True` | Undefined template variables raise errors. |
| `AUTO_RELOAD` | `True` | Reload changed templates. |
| `STATIC_DIR` / `STATIC_URL` | `"static"` / `"/static"` | Static files folder and URL prefix. |
| `STATIC_CONTROLLER_NAME` | `"static"` | `url_for` alias for static files: `url_for("static", filename="app.css")`. |
| `USE_STATIC_PAGES` | `False` | Serve HTML pages from `STATIC_PAGES_DIR`. |
| `STATIC_PAGES_DIR` / `STATIC_PAGES_URL` | `"static_pages"` / `"/"` | Static pages folder and URL prefix. |
| `STATIC_PAGES_CONTROLLER_NAME` | `"static_pages"` | `url_for` alias for pages: `url_for("static_pages", page="about")`. |
| `STRICT_SLASHES` | `False` | If `False`, `/users` and `/users/` match the same route. |
| `OPEN_API` / `OPEN_API_URL` / `OPEN_API_DESCRIPTION` | `True` / `"/openapi"` / `"Simple API"` | OpenAPI documentation. |
| `CORS_ENABLED` | `True` | Global CORS handling. |
| `CORS_ALLOW_ORIGINS` | `["*"]` | Allowed origins. |
| `CORS_ALLOW_METHODS` | `["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]` | Allowed methods. |
| `CORS_ALLOW_HEADERS` | `["Authorization", "Content-Type"]` | Allowed request headers. |
| `CORS_EXPOSE_HEADERS` | `[]` | Response headers exposed to the browser. |
| `CORS_ALLOW_CREDENTIALS` | `True` | Allow credentials (the request origin is echoed instead of `*`). |
| `CORS_MAX_AGE` | `None` | Preflight cache time in seconds. |
| `DEFAULT_LOGGER` | see [Logging](#logging) | Configuration of the default log sink. |
| `IN_MEMORY_LOG_BUFFER_SIZE` | `1000` | Number of log records kept in memory (admin dashboard). |
| `CONTROLLER_FOLDERS`, `CLI_CONTROLLER_FOLDERS`, `EXCEPTION_HANDLER_FOLDERS`, `MIDDLEWARE_FOLDERS`, `LOGGER_FOLDERS` | `None` | Additional folders for [auto-discovery](#project-layout-and-auto-discovery). |

## The application class

```python
from patera import Patera, app, app_path, on_shutdown, on_startup
from patera.injectable import Inject

from .configs import Config
from .services.greetings import GreetingService
from .database import Databases


@app_path("/demo")                 # optional prefix for every controller route
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

Startup and shutdown hooks run in alphabetical order of their method names; use a single hook per
event that calls other methods in the order you need. If a startup hook raises, the server is
notified that startup failed. Extensions add their own hooks with
`app.add_on_startup_method(...)`/`app.add_on_shutdown_method(...)`.

Useful members of the application object:

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
| `json_spec` | the OpenAPI specification (dict) |
| `logger` | the [Loguru](https://loguru.readthedocs.io) logger |
| `root_path`, `static_files_path`, `app_name`, `version` | |
| `default_exception_response(req, exc)` | override to customize the [default error responses](#exception-handling) |

## Project layout and auto-discovery

When the application is created, Patera imports modules from well-known folders inside the
application package and registers the classes it finds. A module is imported if its folder and
file name match:

| Kind | Folders | File name contains | Registered when |
| --- | --- | --- | --- |
| Controllers | `api`, `public`, `controllers`, `routers`, `routes` | `api`, `controller`, `public`, `router`, `routes` | decorated with `@path` |
| Exception handlers | `exceptions`, `exc_controllers` | `handler`, `exception_controller`, `controller` | decorated with `@exception_handler` |
| Middleware | `middleware`, `middlewares` | `middleware`, `mw` | decorated with `@middleware` |
| CLI controllers | `cli`, `cli_controllers`, `clis` | `cli`, `cli_controller` | decorated with `@cli_controller` (CLI mode only) |
| Loggers | `logging`, `loggers` | `logger`, `log_sink`, `logging` | decorated with `@logger` |

Folders are searched recursively. Add folders with the `*_FOLDERS` options. Classes marked with
`@ignore` are skipped; classes (and endpoint methods) marked with `@development` are only registered
when `DEBUG` is on. Anything can also be registered explicitly with the `register_*` methods.

## Controllers

A controller is a class that groups endpoints under a base path:

```python
from pydantic import BaseModel

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import (
    Controller, after_request, before_request, consumes, delete, get, patch, path, post, produces, put,
)

from app import App


class UserIn(BaseModel):
    name: str
    email: str


class UserOut(BaseModel):
    id: int
    name: str


@path("/api/v1/users", tags=["Users"], alias="users")
class UserApi(Controller[App]):

    @get("/")
    async def list_users(self, req: Request) -> Response[list[UserOut]]:
        return req.res.json([{"id": 1, "name": "Ana"}])

    @get("/<int:user_id>")
    async def get_user(self, req: Request, user_id: int) -> Response[UserOut]:
        return req.res.json({"id": user_id, "name": "Ana", "password_hash": "..."})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    async def create_user(self, req: Request, user: UserIn) -> Response[UserOut]:
        return req.res.json({"id": 2, "name": user.name})

    @delete("/<int:user_id>")
    async def delete_user(self, req: Request, user_id: int) -> Response:
        return req.res.no_content()

    @before_request
    async def before(self, req: Request) -> None:
        ...  # runs before every endpoint of this controller

    @after_request
    async def after(self, res: Response) -> None:
        res.set_header("x-controller", "users")
```

- `@path(url, open_api_spec=True, tags=None, alias=None)` – base path of the controller. `alias` is
  an alternative name for `url_for` (`url_for("users.get_user", user_id=1)`); the class name always
  works too (`url_for("UserApi.get_user", user_id=1)`). Several controllers may share a base path.
- `@get`, `@post`, `@put`, `@patch`, `@delete(url, open_api_spec=True, tags=None)` – endpoints.
  The first argument after `self` is always the `Request`; route parameters are passed as keyword
  arguments. Handlers may be `async` or plain functions (these run in a thread pool).
- Route parameters use [Werkzeug converters](https://werkzeug.palletsprojects.com/en/stable/routing/#built-in-converters):
  `<name>`, `<int:id>`, `<float:x>`, `<uuid:key>`, `<path:rest>` (matches slashes), ...
- `@consumes(MediaType)` – the request must have this content type (otherwise `415`). Parameters
  annotated with a Pydantic model are validated from the JSON body, url-encoded form or multipart
  form (including `UploadedFile` fields). Invalid data returns `422` with the validation errors
  unless you [handle](#exception-handling) `pydantic.ValidationError` yourself.
- `@produces(MediaType, status_code=HttpStatus.OK)` – default media type and status code (an
  explicitly set content type/status wins). Documented in OpenAPI.
- `-> Response[Model]` – a dict body is validated and serialized through `Model`, which filters
  out undeclared fields (e.g. `password_hash` above). The annotation (also generic ones like
  `list[Model]`) documents the response in OpenAPI.
- `@before_request` / `@after_request` – controller level hooks. `@after_init` methods run once after
  the controller is created.
- `@open_api_docs(Descriptor(status, description, media_type, body))` – document error responses.
- `@cors(...)` / `@no_cors` – per-endpoint [CORS](#cors) settings.
- `@development` – endpoint (or controller) only exists in debug mode; `@ignore` – never registered.

### Websockets

```python
from patera.controller import Controller, path, socket


@path("/ws")
class ChatSocket(Controller[App]):
    @socket("/chat/<room>")
    async def chat(self, req: Request, room: str) -> None:
        await req.receive()   # {"type": "websocket.connect"}
        await req.accept()
        while True:
            message = await req.receive()
            if message["type"] == "websocket.disconnect":
                break
            await req.send({"type": "websocket.send", "text": f"[{room}] {message.get('text')}"})
```

Websocket handlers receive the raw ASGI messages through `req.receive()`/`req.send()`; HTTP
middleware is not applied to them.

## Requests and responses

`Request`:

| Member | Description |
| --- | --- |
| `method`, `path`, `query_string`, `headers` (lower-case keys) | request line and headers |
| `query_parameters` | dict; repeated keys become lists |
| `route_parameters` | parsed route parameters |
| `await body()`, `await json()` | raw body / parsed JSON (`None` if empty or invalid) |
| `await form()`, `await files()`, `await form_and_files()` | url-encoded and multipart data; files are `UploadedFile` objects (`filename`, `content_type`, `size`, `read()`, `save(path)`, `stream`) |
| `await get_data(location)` | `"json"`, `"form"`, `"files"`, `"form_and_files"` or `"query"` |
| `user`, `roles`, `set_user()`, `set_roles()` | authenticated user (see [Authentication](#authentication)) |
| `context` | request-scoped storage (`req.context.set(key, value)`, `req.context.get(key)`) |
| `app`, `res` / `response` | the application and the response being built |

The current request is also available anywhere during request handling through
`patera.ctx.current_request`.

`Response` (`req.res`) methods return the response, so calls can be chained:

```python
return req.res.json({"ok": True}).status(HttpStatus.CREATED).set_header("x-id", "7")
```

| Method | Description |
| --- | --- |
| `json(data)` | JSON body (dicts, lists, Pydantic models, ...) |
| `text()`, `html_body()`, `xml()`, `csv()`, `yaml()`, `ndjson(rows)`, `bytes(data, media_type)` | other bodies |
| `await html(template, context)`, `await html_from_string(source, context)` | rendered [templates](#templates) |
| `problem(title, detail, status, type_="about:blank", instance=None, extra=None)` | RFC 9457 problem details |
| `stream(iterable, media_type)`, `stream_text(iterable)` | streaming responses (sync or async iterables) |
| `send_file(bytes, headers)` | file download |
| `redirect(location, status=303)`, `no_content()` | redirects and `204` |
| `status(code)` | status code (`int` or `HttpStatus`) |
| `set_header()`, `set_headers()` | headers |
| `set_cookie(name, value, max_age, path, domain, secure, http_only, same_site)`, `delete_cookie()`, `add_raw_cookie()` | cookies |

## Routing behaviour

- With `STRICT_SLASHES=False` (default) `/users` and `/users/` reach the same endpoint.
- Unknown paths return `404` (JSON). A known path with the wrong method returns `405` with an
  `Allow` header.
- `HEAD` requests are answered by the matching `GET` endpoint, without a body.
- `OPTIONS` requests to routes without an explicit handler return `204` with an `Allow` header
  (CORS preflight requests are answered by the CORS middleware).
- `url_for("Controller.method", **params)` builds URLs, also in templates.

## Services and dependency injection

Application services are subclasses of `BaseExtension` (alias: `Service`). Each service is a
singleton per application. Declare dependencies with `Inject[...]` on the application class,
controllers, services, middleware, exception handlers or CLI controllers – they are created on first
use and shared:

```python
from pydantic import BaseModel

from patera import Service
from patera.injectable import ConfigVar, Inject


class GreetingSettings(BaseModel):
    PREFIX: str = "Hello"


class Formatter(Service):
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
    label: str = ConfigVar("GREETING_LABEL", "Greetings")   # with default

    @get("/<name>")
    async def greet(self, req: Request, name: str) -> Response:
        return req.res.text(self.greetings.greet(name))
```

`self.configs` of a service returns the configuration field named after the class in
UPPER_SNAKE_CASE (`GreetingService` → `GREETING_SERVICE`). The second type argument of
`Service[...]`/`BaseExtension[...]` declares the configuration model, which means:

- a configuration model instance in the config class is used as is,
- a plain dict (e.g. from `PATERA_GREETING_SERVICE__PREFIX=Hi`) is validated with the model,
- a missing configuration falls back to the model's defaults (or raises a clear error if the model
  has required fields).

```python
class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    GREETING_SERVICE: GreetingSettings = GreetingSettings(PREFIX="Welcome")
```

Services that should exist from startup (e.g. to register hooks) are listed in
`App.app_extensions`; others are created when they are first injected. Retrieve any service with
`app.get_extension(GreetingService)`. Injection also works with
`from __future__ import annotations`, as long as the injected class is importable at runtime (not
only under `TYPE_CHECKING`).

## Exception handling

Exception handlers are classes with methods mapped to exception types:

```python
from pydantic import ValidationError

from patera import HttpStatus, Request, Response
from patera.exceptions import BaseHttpException, ExceptionHandler, exception_handler, handles


class EntityNotFound(BaseHttpException):
    def __init__(self, message: str):
        super().__init__(message, HttpStatus.NOT_FOUND)


@exception_handler
class ApiExceptionHandler(ExceptionHandler):

    @handles(ValidationError)
    async def validation_error(self, req: Request, exc: ValidationError) -> Response:
        details = exc.errors(include_url=False, include_context=False)
        return req.res.json({"message": "Invalid data", "details": details}).status(422)

    @handles(BaseHttpException)          # also handles subclasses, e.g. EntityNotFound
    async def http_error(self, req: Request, exc: BaseHttpException) -> Response:
        return req.res.json({"message": exc.message, "data": exc.data}).status(exc.status_code)
```

Put the class in an `exceptions` folder (file name containing `handler`) or register it with
`app.register_exception_handler(...)`. A handler registered for a base class also handles its
subclasses; the most specific handler wins.

Without a matching handler:

| Exception | Response |
| --- | --- |
| `BaseHttpException` and subclasses (`abort()`, authentication errors, ...) | JSON `{"status", "message", "data"}` with the exception's status code |
| `pydantic.ValidationError` | `422` with `{"status": "error", "message": "Validation failed", "errors": [...]}` |
| anything else | `DEBUG=True`: the exception propagates (traceback in the server log). `DEBUG=False`: `500` `{"status": "error", "message": "Internal server error"}` and the error is logged |

Override `default_exception_response(req, exc)` on the application class to change this fallback.

Quick aborts:

```python
from patera import HttpStatus, abort, html_abort

abort("User not found", HttpStatus.NOT_FOUND, data={"id": user_id})   # JSON error response
html_abort("errors/404.html", HttpStatus.NOT_FOUND, {"id": user_id})  # renders the template
```

## Templates

Templates are rendered with [Jinja2](https://jinja.palletsprojects.com) (async, auto-escaping for
HTML/XML) from `TEMPLATES_DIR`:

```python
@get("/")
async def index(self, req: Request) -> Response:
    return await req.res.html("index.html", {"title": "Home"})
```

```html
<h1>{{ title }}</h1>
<a href="{{ url_for('UserApi.list_users') }}">Users</a>
<link rel="stylesheet" href="{{ url_for('static', filename='site.css') }}">
```

Besides your context, templates receive `app`, `request`, `url_for`, `attribute` (`getattr`) and
`len`. With `TEMPLATES_STRICT=True` (default) undefined variables raise errors. The application's
own template folder always takes precedence over template folders added by extensions or static
pages.

## Static files and static pages

Files in `STATIC_DIR` are served at `STATIC_URL` (`/static/<path:filename>`) with `Content-Type`
detection, HTTP range requests (`206 Partial Content`, useful for media) and path traversal
protection. In production, consider serving static files with a reverse proxy instead.

With `USE_STATIC_PAGES=True`, HTML files in `STATIC_PAGES_DIR` are rendered as Jinja templates and
served under `STATIC_PAGES_URL` without writing a controller (`pages/about.html` →
`/about` or `/about.html`, `pages/docs/intro.html` → `/docs/intro`). Pages can extend/include each
other by name. Build links with `url_for("static_pages", page="about")`.

## CORS

CORS is enabled by default and configured with the `CORS_*` options. The middleware answers
preflight requests (`OPTIONS` with `Access-Control-Request-Method`) and adds CORS headers to all
responses of allowed origins, including error responses. Requests from origins that are not allowed
are processed normally but without CORS headers, so the browser blocks cross-origin reads while
same-origin requests keep working; preflights from such origins get `403`.

Per endpoint:

```python
from patera.controller import cors, no_cors

@get("/partner-data")
@cors(allow_origins=["https://partner.example.com"], allow_credentials=False, max_age=600)
async def partner_data(self, req: Request) -> Response: ...

@get("/internal")
@no_cors
async def internal(self, req: Request) -> Response: ...
```

## Middleware

Middleware wraps the request handling chain:

```python
# app/middleware/timing_mw.py
import time

from patera import Request, Response
from patera.middleware import MiddlewareBase, middleware


@middleware(order=10)
class TimingMiddleware(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        start = time.perf_counter()
        res = await self.next(req)          # or return a response directly (short-circuit)
        res.set_header("x-process-time-ms", str(int((time.perf_counter() - start) * 1000)))
        return res
```

Middleware is discovered in `middleware` folders (file names containing `middleware` or `mw`) or
registered with `app.register_middleware(TimingMiddleware, order=10)` before the first request.
Lower order numbers run first (outermost). Built-in middleware uses negative orders: CORS `-101`,
the SQL session manager `-100`, authentication `-99`. If an order is taken, the next free number is
used and a warning is logged. Middleware can declare a configuration model just like services
(`MiddlewareBase[App, MyConfig]`, available as `self.configs`).

Exceptions raised in middleware are handled by the exception handlers. Static files bypass
middleware.

## OpenAPI

With `OPEN_API=True` the specification is served at `/openapi/specs.json` and a Swagger UI at
`/openapi/docs`. It is generated from your controllers: paths and path parameters, request bodies
from `@consumes` + Pydantic parameters, responses from `@produces` and `Response[Model]`
annotations, error responses from `@open_api_docs`, tags from `@path(tags=...)` and descriptions
from docstrings. Exclude a controller or endpoint with `open_api_spec=False`.

## Logging

Patera logs with [Loguru](https://loguru.readthedocs.io). Use `self.app.logger` (or `app.logger`).
The default sink is configured with `DEFAULT_LOGGER`:

```python
class Config(BaseConfig):
    ...
    DEFAULT_LOGGER: dict[str, Any] = {
        "SINK": "STDERR",          # STDERR, STDOUT, NULL or a file path
        "LEVEL": "INFO",
        "FORMAT": "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {extra[logger_name]} | <level>{message}</level>",
        "ENQUEUE": True,
        "COLORIZE": True,
    }
```

Additional sinks are classes in a `logging`/`loggers` folder:

```python
# app/loggers/file_logger.py
from patera.logging import LoggerBase, logger


@logger("File logger")
class FileLogger(LoggerBase):
    def get_filter(self):
        return lambda record: record["level"].no >= 30   # WARNING and above
```

```python
class Config(BaseConfig):
    ...
    FILE_LOGGER: dict[str, Any] = {
        "SINK": "logs/app.log",     # relative to the application package
        "LEVEL": "WARNING",
        "ROTATION": "5 MB",
        "RETENTION": "10 days",
        "COMPRESSION": "zip",
    }
```

The most recent log records are also kept in memory (`app.log_buffer`) for the admin dashboard.

## Command line interface

Maintenance commands are methods of CLI controllers:

```python
# app/cli/maintenance_cli.py
from patera.cli import CLIController, cli_controller, command


@cli_controller(name="maintenance")
class MaintenanceCLI(CLIController):

    @command("greet", help="Greets a user")
    async def greet(self, name: str, times: int = 1) -> None:
        for _ in range(times):
            print(f"Hello, {name}!")
```

```sh
uv run patera cli maintenance:greet Ana 3
```

Positional arguments are converted according to the parameter annotations (`str`, `int`,
`float`, `bool` and other callables); parameters with defaults are optional. The application is
created in CLI mode (no HTTP server, no middleware). A failing command prints the error and exits
with status code `1`. CLI controllers support dependency injection like any other component.

## Testing

`patera.testing.PateraTestClient` runs the application (including startup/shutdown hooks) and sends
requests through [HTTPX](https://www.python-httpx.org):

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

The client offers `get`, `post`, `put`, `patch`, `delete`, `head`, `options` and `request`
(all accept the usual HTTPX keyword arguments such as `json=`, `headers=`, `files=`).
Configure pytest in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

and run `uv run patera test` (loads `.env.test`) or `uv run pytest`.

## Extensions

Extensions are services (see [Services and dependency injection](#services-and-dependency-injection)):
you subclass them, configure them through a config field named after your subclass and register
them in `App.app_extensions` (or inject them).

### SQL databases

`patera-database` integrates async SQLAlchemy. Install a driver for your database too
(`aiosqlite` is included; e.g. `asyncpg` for PostgreSQL).

```python
# app/database.py
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from patera.database.sql import DeclarativeBaseModel, SqlDatabase, SqlDatabaseManager


class MainDb(SqlDatabase):
    __db_name__ = "main"


class Databases(SqlDatabaseManager):
    databases = [MainDb]


class Base(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "main"          # models are bound to a database by name


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
```

```python
# app/configs.py
from patera.database.sql import SqlDatabaseConfig

class Config(BaseConfig):
    ...
    MAIN_DB: SqlDatabaseConfig = SqlDatabaseConfig(DATABASE_URI="sqlite+aiosqlite:///./app.db")
```

```python
# app/__init__.py
@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Databases]
```

`SqlDatabaseConfig` options: `DATABASE_URI`, `DATABASE_SESSION_NAME` (default `"session"`),
`SHOW_SQL`, `NICE_NAME`, `EXPIRE_ON_COMMIT`, `AUTOFLUSH`. The engine connects on startup and is
disposed on shutdown. Register only the manager, not the individual databases. With several
databases, give each one a unique `__db_name__` **and** a unique `DATABASE_SESSION_NAME`.

**Sessions and transactions.** During a request, model queries and repositories share one session
per database. At the end of the request the manager middleware commits it if the controller or
endpoint is marked `@transactional` and no exception occurred; otherwise all changes are rolled
back.

```python
from patera.database.sql import Repository, query, transactional
from patera.injectable import Inject


class NoteRepository(Repository[Note]):
    model = Note

    @query("SELECT * FROM notes WHERE title LIKE :pattern ORDER BY id")
    async def search(self, pattern: str) -> list[Note]: ...   # SQL with bound parameters


@path("/notes")
class NoteApi(Controller[App]):
    notes: Inject[NoteRepository]

    @get("/")
    async def index(self, req: Request) -> Response:
        page = await Note.query().order_by(Note.id).paginate(page=1, per_page=20)
        return req.res.json({"total": page.total, "titles": [n.title for n in page.items]})

    @post("/")
    @transactional
    async def create(self, req: Request) -> Response:
        note = await self.notes.create_and_flush(title=(await req.json())["title"])
        return req.res.json({"id": note.id}).status(201)
```

- `Model.query()` returns a chainable `AsyncQuery` (`where`/`filter`, `filter_by`, `join`,
  `order_by`, `order_by_strings("title DESC")`, `limit`, `offset`, and the terminal methods `all`,
  `first`, `one`, `one_or_none`, `count`, `exists`, `paginate`).
- `Repository[Model]` offers `get`, `get_one_by`, `first_by`, `list_all`, `list_by`, `count`,
  `exists`, `create`, `create_and_flush`, `add`, `add_all`, `save`, `delete`, `flush`, `refresh`,
  `paginate`, `execute`. `@query` methods map rows to models, Pydantic/dataclass types, dicts or
  scalars based on the return annotation (`Optional[...]` allows no result).
- Outside requests pass a session explicitly:
  `async with db.create_session() as session: await Note.query(session).all()`, or decorate a CLI
  command with `@cli_session("main")` (opens a session and a transaction for the command).
- `SqlDatabaseManager` gives access to the databases: `manager.get_database("main")`,
  `manager["main"]`, `manager.get_default_database()`.

### Migrations

`patera-migrate` adds SQL migrations based on [pyway](https://github.com/jasondcamp/pyway). Add the
`Migrate` mixin to the database class:

```python
from patera.migrate import Migrate

class MainDb(SqlDatabase, Migrate):
    __db_name__ = "main"
```

Migration settings are part of the database configuration: `MIGRATE_CLI_NAME` (`"migrate"`),
`MIGRATE_DATABASE_MIGRATION_DIR` (`"migrations"`, relative to the application package),
`MIGRATE_TABLE` (`"pyway_migrations"`), `MIGRATE_SQL_MIGRATION_PREFIX` (`"V"`),
`MIGRATE_SQL_MIGRATION_SEPARATOR` (`"__"`), `MIGRATE_SQL_MIGRATION_SUFFIXES` (`".sql"`).

```sh
uv run patera cli migrate:init       # writes migrations/.pyway.conf from DATABASE_URI
# add migrations/V01_01__create_notes.sql
uv run patera cli migrate:info
uv run patera cli migrate:migrate
uv run patera cli migrate:validate
```

### Authentication

`patera-auth` provides an authentication middleware. Implement how users and roles are loaded:

```python
# app/middleware/auth_mw.py
import jwt

from patera import Request
from patera.auth import Authentication, AuthUtils
from patera.middleware import middleware


@middleware
class TokenAuth(Authentication):
    async def user_loader(self, req: Request):
        token = req.headers.get("authorization", "").removeprefix("Bearer ")
        try:
            claims = AuthUtils.validate_jwt_token(token, self.app.configs.SECRET_KEY)
        except jwt.InvalidTokenError:
            return None                    # -> not authenticated
        return await load_user(claims["sub"])

    async def roles_loader(self, user) -> list:
        return user.roles
```

```python
from patera.auth import login_required, role_required


@path("/account")
@login_required()                       # every endpoint requires a user
class AccountApi(Controller[App]):

    @get("/")
    async def me(self, req: Request) -> Response:
        return req.res.json({"user": req.user.name})

    @get("/admin")
    @role_required("admin", "owner")    # any of the listed roles
    async def admin(self, req: Request) -> Response: ...
```

Routes without the decorators do not load the user. A missing user raises
`AuthenticationException` (`401`), missing roles raise `AuthorizationException` (`403`, the
required roles in `data`); both produce JSON error responses unless you handle them. Role
requirements on the controller and on the endpoint must both be satisfied. Configure messages with
`TOKEN_AUTH: AuthConfig = AuthConfig(AUTHENTICATION_ERROR_MSG=..., AUTHORIZATION_ERROR_MSG=...,
ALWAYS_LOAD_ROLES=False)`. Override `refresh_credentials(res)` to renew cookies/tokens.

`AuthUtils` contains helpers: `create_password_hash`/`check_password_hash` (bcrypt),
`create_signed_cookie_value`/`decode_signed_cookie` (HMAC) and
`create_jwt_token`/`validate_jwt_token` (HS256; validation raises `jwt.InvalidTokenError`).

### Caching

`patera-caching` caches responses of endpoints:

```python
from patera.caching import Caching, CachingConfig, cache


class PublicCache(Caching):
    pass                                 # in-memory backend by default


class Config(BaseConfig):
    ...
    PUBLIC_CACHE: CachingConfig = CachingConfig(DURATION=60, MAX_SIZE=1000)


@path("/stats")
class StatsApi(Controller[App]):
    @get("/")
    @cache("PUBLIC_CACHE", duration=15)  # registered name of the extension
    async def stats(self, req: Request) -> Response:
        return req.res.json(await compute_stats())
```

Register `PublicCache` in `app_extensions`. Put `@cache` directly above the handler (below
`@get`). The key combines the handler name, method, path and query string (or pass `key=...`).
Only successful (`< 400`), non-streaming responses without cookies are cached; the status, headers
and media type are restored on a hit. Cache only public data or include the user in the key.

Manual use: `await cache.get(key, req)`, `await cache.set(key, response, duration)`,
`await cache.delete(key)`, `await cache.delete("users:*", wildcard=True)`,
`await cache.delete(r"^users:\d+$", regex=True)`, `await cache.clear()`.

Other backends are assigned in `init()`:

```python
from patera.caching.backends.redis_cache_backend import RedisCacheBackend
from patera.caching.backends.sqlite_cache_backend import SQLiteCacheBackend


class SharedCache(Caching):
    def init(self) -> None:
        self.backend = RedisCacheBackend(url="redis://localhost:6379/0", default_ttl=60, key_prefix="myapp")
        # or: RedisCacheBackend.configure_from_app(self.app, self.configs)  (REDIS_URL, KEY_PREFIX, ...)
        # or: SQLiteCacheBackend(db_path="cache.db", default_ttl=60)
        super().init()
```

The Redis and SQLite backends store pickled data – only use storage that you control. Custom
backends implement `patera.caching.BaseCacheBackend`.

### Task manager

`patera-taskmanager` schedules jobs with [APScheduler](https://apscheduler.readthedocs.io/en/3.x/):

```python
from patera.taskmanager import TaskManager, schedule_job


class Jobs(TaskManager):

    @schedule_job("interval", minutes=5, id="cleanup")
    async def cleanup(self) -> None:
        self.app.logger.info("Cleaning up")

    @schedule_job("cron", hour=3, id="nightly")
    async def nightly(self) -> None: ...
```

Register `Jobs` in `app_extensions`; the scheduler starts and stops with the application. Optional
configuration: `JOBS: TaskManagerConfig = TaskManagerConfig(NICE_NAME="Jobs", DAEMON=True)`.
At runtime: `add_job(func, trigger, **kwargs)`, `remove_job(job)`, `pause_job(job)`,
`resume_job(job)`, `run_job_now(job)`, `get_job(id)`, `jobs`, `is_job_running(job)` and
`run_background_task(func, *args)` for fire-and-forget work. Customize the scheduler with the class
attributes `scheduler_cls`, `job_stores`, `executors` and `job_defaults`.

### E-mail

```python
from patera.email import EmailClient, EmailConfig


class Mailer(EmailClient):
    pass


class Config(BaseConfig):
    ...
    MAILER: EmailConfig = EmailConfig(
        SENDER_NAME_OR_ADDRESS="My app <noreply@example.com>",
        SMTP_SERVER="smtp.example.com", SMTP_PORT=587,
        USERNAME="user", PASSWORD="secret", USE_TLS=True,
    )
```

```python
mailer: Inject[Mailer]
...
await self.mailer.send_email("ana@example.com", "Report", "See attachment", attachments={"report.csv": data})
await self.mailer.send_email_with_template(["a@example.com"], "Welcome", "mail/welcome.txt", context={"name": "Ana"})
```

### External APIs

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
    @resource("/repos/<repo_id>")              # filled from the current request's route parameters
    async def get_repo(self) -> Repo: ...      # Pydantic return types are validated

    @method(HttpMethod.POST)
    @resource("/repos")
    async def create_repo(self, name: str, private: bool) -> dict: ...   # arguments become the JSON body
```

Also available: `@consumes`/`@produces` (body and response formats, incl. form data and file
uploads), `AuthType.BASIC_AUTH` and `AuthType.API_KEY`, and `@no_auth` to disable inherited
authentication for one method. During a request the current query string is forwarded and `<name>`
placeholders are filled from route parameters; the methods can also be called outside requests.

### AI interface (experimental)

`patera-aiinterface` connects to chat completion APIs (OpenAI-compatible and Ollama). It depends on
PyTorch/sentence-transformers for optional prompt augmentation.

```python
from typing import AsyncIterator

from patera.aiinterface import AiService, AiServiceConfig, ChatResponse, system_prompt, user_prompt
from patera.aiinterface.service_provider.openai import OpenAIServiceProvider


class Assistant(AiService):
    service_provider = OpenAIServiceProvider()      # or OllamaServiceProvider()

    @system_prompt("You are a helpful translator.")
    @user_prompt("Translate '<:text>' to <:language>.")
    async def translate(self, text: str, language: str = "German") -> ChatResponse: ...

    @system_prompt("You are a storyteller.")
    @user_prompt("Tell a short story about <:topic>.")
    async def story(self, topic: str) -> AsyncIterator[ChatResponse]: ...   # streaming


class Config(BaseConfig):
    ...
    ASSISTANT: AiServiceConfig = AiServiceConfig(
        BASE_URL="https://api.openai.com/v1", API_KEY="...", MODEL="gpt-4o-mini",
    )
```

```python
answer = await self.assistant.translate("Good morning", "French")
async for chunk in await self.assistant.story("cats"):
    ...
```

`<:name>` placeholders are filled from the method's arguments (including defaults). Conversation
history (`@history`, with a `history_provider` based on `BaseHistoryProvider`) and retrieval
augmentation (`@augmentation`, with an `augmentation_provider`) are optional. The `@tool` decorator
marks methods as tools, but the bundled providers do not send tool definitions yet.

### Admin dashboard

`patera-admin` provides a web dashboard for logs, database models, files in the static folder, task
managers and e-mail clients. It requires an [authentication](#authentication) middleware: users need
the roles from `patera.admin.Permissions` (`ADMIN_CAN_ENTER` plus
`ADMIN_CAN_VIEW`/`CREATE`/`EDIT`/`DELETE`).

```python
from patera.admin import AdminConfig, AdminInterface


class Admin(AdminInterface):
    MANAGED_MODELS = [Note]


class Config(BaseConfig):
    ...
    ADMIN: AdminConfig = AdminConfig(
        URL_FOR_FOR_LOGIN="AuthApi.login", URL_FOR_FOR_LOGOUT="AuthApi.logout",
    )
```

List `Admin` in `app_extensions` **after** the extensions it should manage (databases, task
managers, e-mail clients). The dashboard is served at `/admin/<lang>/` (`en`, `de`, `si`, `es`).

### Desktop applications

`patera-desktop` runs the application in a native window ([pywebview](https://pywebview.flowrl.com)):
`uv run patera desktop --mode dev`. Window options are read from `PATERA_DESKTOP_*` environment
variables (`TITLE`, `WIDTH`, `HEIGHT`, `RESIZABLE`, `FULLSCREEN`, `ICON`, ...).

## Developing Patera

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): the
core package lives in `src/patera`, the extensions in `packages/`. All of them share the `patera`
namespace.

```sh
uv sync --all-packages --all-extras    # note: the AI interface pulls in PyTorch
uv run pytest                          # tests/ (unit, integration and extension tests)
uv run pytest --cov
uv run ruff check . && uv run ruff format --check .
uv run mypy src/patera
```

Scripts in [`scripts/`](scripts/README.md) bump versions, build and publish all packages.
