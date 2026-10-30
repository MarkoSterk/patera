<p align="center">
  <img src="https://raw.githubusercontent.com/MarkoSterk/Patera/refs/heads/main/src/patera/graphics/patera_logo.png" alt="Patera Logo" width="200">
</p>

# Patera - async-first Python web framework

See [public API conventions and extension names](PUBLIC_API.md) for the package,
import and configuration map, installation-extra scope and compatibility policy.

Patera is a modular, async-first ASGI web framework with a structure inspired by Java frameworks:
class-based controllers, decorators for routing and HTTP semantics, dependency injection of
application services, and typed configuration objects.

The core package handles routing, requests/responses, validation, templates, static files, CORS,
middleware, OpenAPI documentation, logging, a CLI and a test client. Optional packages add SQL
databases, migrations, authentication, caching, scheduled tasks, e-mail, declarative API clients,
an AI interface, an admin dashboard and desktop windows.

> Patera is in beta. Until version 1.0, a minor release may contain breaking changes; each one is
> listed in the [changelog](https://github.com/MarkoSterk/Patera/blob/main/CHANGELOG.md). The AI
> interface and desktop packages are experimental.

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
| `prod` | granian | production server (`patera prod`) |
| `dev` | uvicorn, watchfiles, websockets | development server with auto-reload (`patera dev`) |
| `testing` | pytest, pytest-asyncio, httpx, ... | testing tools (`patera test`) |
| `database` | `patera-database` | async SQLAlchemy integration |
| `migrate` | `patera-migrate` | SQL migrations (pyway) |
| `auth` | `patera-auth` | authentication/authorization middleware |
| `caching` | `patera-caching` | response caching (in-memory) |
| `caching-redis` / `caching-sqlite` | + redis / aiosqlite | Redis or SQLite cache backends |
| `taskmanager` | `patera-taskmanager` | scheduled and background tasks (APScheduler) |
| `email` | `patera-email` | SMTP e-mail client |
| `apiinterface` | `patera-apiinterface` | declarative clients for external HTTP APIs |
| `joltui` | [`patera-joltui`](packages/patera-joltui/README.md) | JoltUI server components with typed group registration |
| `aiinterface` | `patera-aiinterface` | LLM chat interface (experimental; `patera-aiinterface[augmentation]` adds the embedding libraries) |
| `admin` | `patera-admin` | admin dashboard |
| `desktop` | `patera-desktop` | show the app in a desktop window (pywebview) and package it as a program |
| `all` | the extension packages above except `aiinterface` and `desktop` | |

```sh
uv add "patera[database,auth,caching]"
```

The production server is an extra too, `prod`, because a deployment needs it but a desktop
program does not (it embeds Uvicorn). Without it, the core's dependencies are pure Python
apart from pydantic-core.

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
| `patera prod [--app app:App] [--env-file .env.prod]` | production server ([Granian](https://github.com/emmett-framework/granian), installed with the `prod` extra: `uv add "patera[prod]"`), `DEBUG` is forced off. Only an environment file given with `--env-file` is loaded. Host/port from `PATERA_HOST`/`PATERA_PORT` (default `0.0.0.0:80`), event loop from `PATERA_LOOP`. |
| `patera cli Controller:command [args...]` | runs a [CLI command](#command-line-interface). |
| `patera agents [codex\|claude\|all]` | generates project instructions and Patera skills without loading an application. Defaults to Codex; supports `--dry-run` and `--force`. |
| `patera test [--env-file FILE] [pytest args...]` | runs pytest after loading the test environment file (`.env.test` when the project has one). Pytest options may come in any order (`patera test -k login -q`); everything after `--` goes to pytest unchanged. |

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

The values can live in `.env` (or the environment) instead of the class. Declare a settings model
without a value, and it is built from the variables that are set, with the model's defaults for the
rest:

```python
class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    MAIN_DB: SqlDatabaseConfig    # PATERA_MAIN_DB__DATABASE_URI must be set
    DESKTOP: DesktopConfig        # every field has a default; PATERA_DESKTOP__WIDTH=1200 changes one
```

A required field that no variable sets stops the application at startup with its name
(`MAIN_DB.DATABASE_URI: Field required`). A model declared with a value in the class
(`MAIN_DB: SqlDatabaseConfig = SqlDatabaseConfig(...)`) keeps that value as its default, and
variables change single fields of it.

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
| `HOST` / `PORT` / `PROTOCOL` | `"localhost"` / `3000` / `"http"` | Where the server listens and what the startup line and OpenAPI server URL report. `patera dev`/`prod` take `PATERA_HOST`/`PATERA_PORT`, then defaults set on your config class, then `localhost:3000` (dev) or `0.0.0.0:80` (prod). |
| `STARTUP_BANNER` | `True` | Print the banner and address box on startup; the startup line is always logged. |
| `MAX_CONTENT_LENGTH` | `10485760` (10 MB) | Largest accepted request body; `None` for no limit. Override per route with `@max_content_length`. |
| `BACKGROUND_TASKS_SHUTDOWN_TIMEOUT` | `10.0` | Seconds to wait on shutdown for `run_in_background()` tasks before cancelling them (`None`: no limit). |
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
| `URL_PREFIX` | `""` | Prefix of every controller route, for example `"/api/v1"` (`PATERA_URL_PREFIX`). It must start with `/`; a trailing `/` is removed. Static files keep `STATIC_URL`. |
| `STRICT_SLASHES` | `False` | If `False`, `/users` and `/users/` match the same route. |
| `OPEN_API` / `OPEN_API_URL` / `OPEN_API_DESCRIPTION` | `True` / `"/openapi"` / `"Simple API"` | OpenAPI documentation. |
| `CORS_ENABLED` | `True` | Global CORS handling. |
| `CORS_ALLOW_ORIGINS` | `["*"]` | Allowed origins. |
| `CORS_ALLOW_METHODS` | `["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]` | Allowed methods. |
| `CORS_ALLOW_HEADERS` | `["Authorization", "Content-Type"]` | Allowed request headers. |
| `CORS_EXPOSE_HEADERS` | `[]` | Response headers exposed to the browser. |
| `CORS_ALLOW_CREDENTIALS` | `False` | Allow credentials: cookies and `Authorization` on cross-origin requests (the request origin is echoed instead of `*`). Turn it on only together with an explicit `CORS_ALLOW_ORIGINS` list. |
| `CORS_MAX_AGE` | `None` | Preflight cache time in seconds. |
| `DEFAULT_LOGGER` | `DefaultLoggerConfig()` | Default console sink, see [Logging](#logging). |
| `LOG_FILES` | `LogFilesConfig()` | Rotating JSON Lines log files read by the admin dashboard, see [Logging](#logging). |
| `CONTROLLER_FOLDERS`, `CLI_CONTROLLER_FOLDERS`, `EXCEPTION_HANDLER_FOLDERS`, `MIDDLEWARE_FOLDERS`, `LOGGER_FOLDERS` | `None` | Additional folders for [auto-discovery](#project-layout-and-auto-discovery). |

## The application class

```python
from patera import Patera, app, on_shutdown, on_startup
from patera.injectable import Inject

from .configs import Config
from .services.greetings import GreetingService
from .database import Databases


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
| `url_prefix` | the `URL_PREFIX` setting (`""` without a prefix) |
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
  form (including `UploadedFile` fields). For forms, a single value of a field the model declares
  as a list (checkboxes, multi-selects) arrives as a one-item list. Invalid data raises
  `RequestValidationError`: `422` with the validation errors, without the submitted values, unless
  you [handle](#exception-handling) it yourself. Validate other client data (query parameters,
  route values) with `req.validate(Model, data)`, which raises the same error.
- `@produces(MediaType, status_code=HttpStatus.OK)` – default media type and status code (an
  explicitly set content type or status wins, also `.status(HttpStatus.OK)`). Documented in OpenAPI.
- `-> Response[Model]` – the body is validated and serialized through `Model`, which filters
  out undeclared fields (e.g. `password_hash` above). Generic annotations such as `list[Model]` or
  `dict[str, Model]` filter every item. Dictionaries, model instances and objects with matching
  attributes (ORM rows) are accepted. Only 2xx bodies are shaped this way; error bodies keep their
  own fields. The annotation also documents the response in OpenAPI.
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
middleware is not applied to them. A socket handler (or its controller) marked with
`@login_required`, `@role_required` or `@transactional` is therefore refused at startup: check the
user inside the handler and keep sockets in a controller of their own. Database sessions a socket
handler opens through `Model.query()` or a repository are closed when it returns.

## Requests and responses

`Request`:

| Member | Description |
| --- | --- |
| `method`, `path`, `query_string`, `headers` (lower-case keys) | request line and headers |
| `query_parameters` | dict; repeated keys become lists |
| `route_parameters` | parsed route parameters |
| `await body()`, `await json()` | raw body / parsed JSON (`None` if empty; malformed JSON is `400`). A client that disconnects mid-body raises `ClientDisconnected`: the handler stops and no response is sent |
| `await form()`, `await files()`, `await form_and_files()` | url-encoded and multipart data; files are `UploadedFile` objects (`filename`, `content_type`, `size`, `read()`/`seek()` like a file, `save(path)`, `stream`); a broken multipart body is `400` |
| `validate(Model, data)` | validates client data the handler reads itself; invalid data raises `RequestValidationError` (`422`) |
| `await get_data(location)` | `"json"`, `"form"`, `"files"`, `"form_and_files"` or `"query"` |
| `user`, `roles`, `set_user()`, `set_roles()` | authenticated user (see [Authentication](#authentication)) |
| `context` | request-scoped storage (`req.context.set(key, value)`, `req.context.get(key)`) |
| `app`, `res` / `response` | the application and the response being built |

The current request is also available anywhere during request handling through
`patera.ctx.current_request`.

`Response` (`req.res`) methods return the response, so calls can be chained:

```python
from patera import HttpStatus

return req.res.json({"ok": True}).status(HttpStatus.CREATED).set_header("x-id", "7")
```

| Method | Description |
| --- | --- |
| `json(data)` | JSON body: dicts, lists, Pydantic models and values inside them such as dates, UUIDs and decimals, encoded as Pydantic encodes them. A `str` or `bytes` raises `TypeError` (use `text()`, or `bytes(data, MediaType.APPLICATION_JSON.value)` for encoded JSON) |
| `text()`, `html_body()`, `xml()`, `csv()`, `yaml()`, `ndjson(rows)`, `bytes(data, media_type)` | other bodies |
| `await html(template, context)`, `await html_from_string(source, context)` | rendered [templates](#templates) |
| `problem(title, detail, status, type_="about:blank", instance=None, extra=None)` | RFC 9457 problem details |
| `stream(iterable, media_type)`, `stream_text(iterable)` | streaming responses (sync or async iterables); an error after the first chunk is logged and the connection closed, since the status is already sent |
| `file_response(res, path, req.headers, download_name=...)` (from `patera.utilities`) | stream a file from disk, with ranges, `ETag` and 304; `download_name` makes it a download under any file name |
| `redirect(location, status=HttpStatus.SEE_OTHER)`, `no_content()` | redirects and `204` |
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
from patera import HttpStatus, Request, Response
from patera.exceptions import (
    BaseHttpException,
    ExceptionHandler,
    RequestValidationError,
    exception_handler,
    handles,
)


class EntityNotFound(BaseHttpException):
    def __init__(self, message: str):
        super().__init__(message, HttpStatus.NOT_FOUND)


@exception_handler
class ApiExceptionHandler(ExceptionHandler):

    @handles(RequestValidationError)
    async def validation_error(self, req: Request, exc: RequestValidationError) -> Response:
        return req.res.json({"message": "Invalid data", "details": exc.errors}).status(HttpStatus.UNPROCESSABLE_ENTITY)

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
| `RequestValidationError` (from `@consumes` or `req.validate()`, a `BaseHttpException`) | `422` with `{"status": "error", "message": "Validation failed", "data": [...]}` |
| anything else, including a `pydantic.ValidationError` from your own code or data | `DEBUG=True`: the exception propagates (traceback in the server log). `DEBUG=False`: `500` `{"status": "error", "message": "Internal server error"}` and the error is logged |

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
same-origin requests keep working; preflights from such origins get `403`. Every response of a route
with CORS enabled carries `Vary: Origin`, so shared caches keep the variants apart.

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
from docstrings. Exclude a controller or endpoint with `open_api_spec=False`. The document's server
is relative (`URL_PREFIX`, or `/`), so "Try it out" calls the origin that served the page, behind a
proxy too.

## Logging

Patera logs with [Loguru](https://loguru.readthedocs.io). Use `self.app.logger` (or `app.logger`).
The default sink is configured with `DEFAULT_LOGGER`, a `DefaultLoggerConfig` model. Fields you
leave out keep their defaults, and unknown fields are rejected:

```python
from patera.logging import DefaultLoggerConfig


class Config(BaseConfig):
    ...
    DEFAULT_LOGGER: DefaultLoggerConfig = DefaultLoggerConfig(
        SINK="STDERR",             # STDERR, STDOUT, NULL or a file path
        LEVEL="INFO",
        ENQUEUE=True,
        COLORIZE=True,
    )
```

Fields can also be set from the environment, for example `PATERA_DEFAULT_LOGGER__LEVEL=INFO`.

### Log files

Every record at `LOG_FILES.LEVEL` or above is also written to a JSON Lines file, one JSON object
per line with `time`, `level`, `message`, `logger_name`, `name`, `file`, `line`, `function`,
`process`, `thread`, and, when present, `exception` (the formatted traceback) and `extra` (values
bound with `logger.bind(...)`). The admin dashboard reads its log view from these files.

```python
from patera.logging import LogFilesConfig


class Config(BaseConfig):
    ...
    LOG_FILES: LogFilesConfig = LogFilesConfig(
        PATH="logs/patera.jsonl",  # relative to the application package; must end with .jsonl
        LEVEL="INFO",
        ROTATION="10 MB",          # size, time of day ("00:00") or interval ("1 day"); None = never
        FILE_COUNT=5,              # files kept, including the active one
    )
```

| Field | Default | Description |
|-------|---------|-------------|
| `ENABLED` | `True` | Write log files. |
| `PATH` | `logs/patera.jsonl` | Active file. Rotated files are renamed with their rotation time, e.g. `patera.2026-10-09_13-25-00_123456.jsonl`. |
| `LEVEL` | `DEBUG` | Minimum level written. |
| `ROTATION` | `10 MB` | When the active file is rotated. |
| `FILE_COUNT` | `5` | Number of files kept; older rotated files are deleted. |
| `ENQUEUE` | `True` | Write from a background queue. |
| `READ_LIMIT` | `10000` | Maximum number of newest records returned by `app.log_files.read()`. |

`app.log_files.read(limit)` (or `await app.log_files.read_async(limit)`) returns the newest
records, oldest first. Rotation is not coordinated between processes: with several server
workers appending to one file, set `ROTATION=None` and rotate with an external tool, or run a
single worker.

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


## Command line interface

### Generate coding-agent guidance

Run from the project directory, including before an application exists:

```sh
patera agents             # AGENTS.md and .agents/skills/patera/
patera agents claude      # CLAUDE.md and .claude/skills/patera/
patera agents all         # both layouts; CLAUDE.md imports AGENTS.md
patera agents all --dry-run
```

The bundled skill covers application construction, configuration, injection,
controllers, requests/responses, middleware, errors, CLI controllers, WebSockets,
templates, logging, testing, deployment, custom extensions, and all official
extension packages. Its `SKILL.md` routes to focused reference files derived from
the tutorial and architecture books; generation works offline from an installed
package and does not require the books or optional extensions.

Existing instruction files retain their content outside a marked Patera section.
Repeated runs skip identical files. A conflicting skill file stops generation
before any writes; use `--force` to replace those bundled files deliberately.
Unrelated files are preserved. `--dry-run` never writes, even with `--force`.
Malformed section markers and linked destinations require manual repair and are
not bypassed by `--force`. Run the command in the intended project root: it writes
to the current directory, without searching for an app or loading environment
files. Application-only `--app`, `--env-file`, and `--list` options do not apply.

### Application commands

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
requests through [HTTPX](https://www.python-httpx.org). It needs the `testing` extra, which also
installs pytest and pytest-asyncio: `uv add --dev "patera[testing]"`.

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

and run `uv run patera test` (loads `.env.test` if present) or `uv run pytest`.

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
`SHOW_SQL`, `NICE_NAME`, `EXPIRE_ON_COMMIT`, `AUTOFLUSH`, and `SQLITE_FOREIGN_KEYS` (SQLite only:
enforce `FOREIGN KEY` constraints, which SQLite leaves off by default; for example
`PATERA_MAIN_DB__SQLITE_FOREIGN_KEYS=true`). The engine connects on startup and is
disposed on shutdown. Register only the manager, not the individual databases. With several
databases, give each one a unique `__db_name__` **and** a unique `DATABASE_SESSION_NAME`.

**Sessions and transactions.** During a request, model queries and repositories share one session
per database. At the end of the request the manager middleware commits it if the controller or
endpoint is marked `@transactional` and no exception occurred; otherwise all changes are rolled
back.

```python
from patera import HttpStatus

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
        return req.res.json({"id": note.id}).status(HttpStatus.CREATED)
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
`MIGRATE_TABLE` (`"pyway_migrations"`), and the migration file names:
`MIGRATE_SQL_MIGRATION_PREFIX` (`"V"`), `MIGRATE_SQL_MIGRATION_SEPARATOR` (`"__"`) and
`MIGRATE_SQL_MIGRATION_SUFFIXES` (`".sql"`, several separated by commas). A migration is named
`<prefix><version><separator><description><suffix>`, for example `V1_0__create_notes.sql`; the
version has at least two numbers (`1_0`, `2.1`, `3_0_1`). Files with another ending, such as a
`README.md`, are ignored; a file with a migration ending but another name stops the command with an
error, so a misnamed migration is never skipped silently.
`migrate:init` writes `.pyway.conf` into the migration directory (`app/migrations/.pyway.conf` by
default). Each developer generates their own copy, so add it to `.gitignore`. The file holds only
migration settings: the connection (including the password) is read from `DATABASE_URI` each time a
command runs. A `database_*` value set in the file overrides the URI for that developer.

```sh
uv run patera cli migrate:init       # writes app/migrations/.pyway.conf (keep it in .gitignore)
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

    @get("/audit")
    @role_required("admin", "auditor", require_all=True)    # every listed role
    async def audit(self, req: Request) -> Response: ...
```

Routes without the decorators do not load the user. A missing user raises
`AuthenticationException` (`401`), missing roles raise `AuthorizationException` (`403`, the
required roles in `data`); both produce JSON error responses unless you handle them. Role
requirements on the controller and on the endpoint must both be satisfied. Configure messages with
`TOKEN_AUTH: AuthConfig = AuthConfig(AUTHENTICATION_ERROR_MSG=..., AUTHORIZATION_ERROR_MSG=...,
ALWAYS_LOAD_ROLES=False)`. Override `refresh_credentials(res)` to renew cookies/tokens.

`AuthUtils` contains helpers: `create_password_hash`/`check_password_hash` (bcrypt over a SHA-256
digest, so passwords of any length count in full; a malformed stored hash simply does not match;
plain bcrypt hashes from earlier versions still verify, and `password_hash_needs_update(hash)` says
when to re-hash after a successful login),
`create_signed_cookie_value`/`decode_signed_cookie(value, key, max_age=None)` (HMAC with a signing
timestamp; `max_age` rejects older values) and
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
Only successful (`< 400`), non-streaming responses without cookies are cached. The body is stored
as it is sent, already serialized (through `Response[Model]`), and replayed with the status, headers
and media type on a hit. Cache only public data or include the user in the key.

Manual use: `await cache.get(key, req)`, `await cache.set(key, response, duration)`,
`await cache.delete(key)`, `await cache.delete("users:*", wildcard=True)`,
`await cache.delete(r"^users:\d+$", regex=True)`, `await cache.clear()`.

Other backends are chosen with `backend_class`; the extension creates them from its settings
with `backend_class.from_configs(app, configs, namespace)`:

```python
from patera.caching.backends.redis_cache_backend import RedisCacheBackend


class SharedCache(Caching):
    backend_class = RedisCacheBackend   # SHARED_CACHE = {"REDIS_URL": ..., "DURATION": 60}
```

Keys in Redis and SQLite live under `KEY_PREFIX`, by default `patera:<app name>:<cache name>:`
(for example `patera:blog:shared_cache:`), so several caches or applications can share one store and
`clear()` only removes its own keys. To build a backend yourself, assign `self.backend` in `init()`
before calling `super().init()`.

The Redis and SQLite backends store JSON (the serialized body as base64 text), so reading an entry
never runs code; an entry that cannot be read counts as a miss. Custom backends implement
`patera.caching.BaseCacheBackend` (`encode_payload()`/`decode_payload()` convert a payload).

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

Register `Jobs` in `app_extensions`; the scheduler starts and stops with the application. A job
without an `id` gets `<class>.<method>` (`Jobs.cleanup`), and a job is replaced at every start, so it
is never stored twice. Optional
configuration: `JOBS: TaskManagerConfig = TaskManagerConfig(NICE_NAME="Jobs", DAEMON=True)`.
At runtime: `add_job(func, trigger, **kwargs)`, `remove_job(job)`, `pause_job(job)`,
`resume_job(job)`, `run_job_now(job)`, `get_job(id)`, `jobs`, `is_job_running(job)` and
`run_background_task(func, *args)` for fire-and-forget work. Customize the scheduler with the class
attributes `scheduler_cls`, `job_stores`, `executors` and `job_defaults`. With a job store that
keeps jobs outside the process, such as `SQLAlchemyJobStore`, declared jobs and task manager methods
passed to `add_job()` are stored by name and find the running task manager when they run (one
application per process).

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
    @resource("/repos/<repo_id>")              # filled from the argument of the same name
    async def get_repo(self, repo_id: int) -> Repo: ...   # Pydantic return types are validated

    @method(HttpMethod.POST)
    @resource("/repos")
    async def create_repo(self, name: str, private: bool) -> dict: ...   # arguments become the JSON body
```

Also available: `@consumes`/`@produces` (body and response formats, incl. form data and file
uploads), `AuthType.BASIC_AUTH` and `AuthType.API_KEY`, and `@no_auth` to disable inherited
authentication for one method. Arguments fill `<name>` placeholders; the rest become query
parameters (GET, HEAD) or the body. `@forward_request` (on a method or the class) additionally
forwards the current request's query string and fills placeholders from its route parameters.

A 4xx or 5xx answer raises `ApiInterfaceResponseError` with `status_code`, the decoded `body` and the
`response`. Annotate a method with `-> httpx.Response` to receive every response unchecked.

### AI interface (experimental)

`patera-aiinterface` connects to chat completion APIs (OpenAI-compatible and Ollama). Retrieval
augmentation needs the embedding libraries (sentence-transformers, which brings PyTorch, and
pgvector): `pip install "patera-aiinterface[augmentation]"`. Without them everything else works.

```python
from typing import AsyncIterator, Optional

from patera.aiinterface import (
    AiService, AiServiceConfig, ChatResponse, SqlHistoryProvider, history, system_prompt, user_prompt,
)
from patera.aiinterface.service_provider.openai import OpenAIServiceProvider


class ChatHistory(SqlHistoryProvider[ChatMessageRow]):   # a model with session_id, role,
    model = ChatMessageRow                               # content and order_number columns


class Assistant(AiService):
    service_provider = OpenAIServiceProvider()           # or OllamaServiceProvider()
    history_provider = ChatHistory()

    @system_prompt("You are a helpful translator.")
    @user_prompt("Translate '<:text>' to <:language>.")
    async def translate(self, text: str, language: str = "German") -> ChatResponse: ...

    @history
    @system_prompt("You are a friendly assistant.")
    @user_prompt("<:message>")
    async def chat(self, session_id: Optional[str], message: str) -> AsyncIterator[ChatResponse]: ...


class Config(BaseConfig):
    ...
    ASSISTANT: AiServiceConfig = AiServiceConfig(
        BASE_URL="https://api.openai.com/v1", API_KEY="...", MODEL="gpt-4o-mini", HISTORY_LIMIT=10,
    )
```

```python
answer = await self.assistant.translate("Good morning", "French")
async for chunk in self.assistant.chat(None, "Hi!"):      # None starts a new session
    session_id = chunk.session_id                         # send it back to continue the chat
```

Every call builds the messages the same way: the current system prompt first, then (with `@history`)
the session's last `HISTORY_LIMIT` messages, then the user prompt with its `<:name>` placeholders
filled from the method's arguments. A method annotated `-> AsyncIterator[ChatResponse]` streams and
is iterated directly, without `await`; the others return one `ChatResponse`.

- `@history` needs a `history_provider` and a `session_id` parameter on the method. `None` starts a
  new session (a random UUID by default; override `new_session_id()`), and every response carries
  the session id. The question and the answer are saved after the call (a streamed answer once the
  stream ends); nothing is saved when the call fails. The system prompt is never stored, so a changed
  prompt applies to existing sessions too. In a `@transactional` handler, `SqlHistoryProvider` uses
  the request's session, so the messages commit or roll back with the request; anywhere else it uses
  a short transaction of its own, so it works in plain requests, CLI commands and scheduled jobs
  without a commit by the caller (a streamed answer, saved after the request's transaction has
  ended, also gets its own). Writes to one chat session never overlap, also across worker processes
  and inside `@transactional` requests that commit later: each write first locks the chat session
  until it commits (an advisory lock on PostgreSQL, the database's write lock on SQLite). Other
  databases take turns within a process. Implement `load()` and `append()` of
  `BaseHistoryProvider` for other storage.
- `HISTORY_SUMMARY = HistorySummaryConfig(EVERY=10, MAX_WORDS=250)` keeps a rolling summary of
  long conversations. Each call sends the summary, then the messages it does not cover; once
  `EVERY` messages beyond the latest `HISTORY_LIMIT` are uncovered, they are merged into the summary
  by one extra model call in the background, after the answer is returned. The summary is a row of
  the messages table (`role="summary"`), every message stays stored in full, and concurrent updates
  never overwrite each other. `await service.update_summary(session_id)` runs an update by hand.
  Custom history providers support it by implementing `load_since`, `load_summary` and
  `save_summary`.
- `@augmentation` adds the most similar documents as a context message just before the user message
  (`CONTEXT_TEMPLATE`, with `<:documents>`); the history never stores them. With history and
  `REWRITE_QUERY=True`, a follow-up such as "who wrote it?" is first rewritten by the model into a
  standalone question for the search (one extra call per message; off by default).
- The documents are rows with a text and a `VectorColumn` (pgvector's type):

  ```python
  from patera.aiinterface.augmentation_provider import BaseAugmentationProvider
  from patera.aiinterface.augmentation_provider.embeddings import VectorColumn


  class Document(Base):
      __tablename__ = "documents"
      id: Mapped[int] = mapped_column(primary_key=True)
      text: Mapped[str] = mapped_column(Text)
      vector = mapped_column(VectorColumn(384))     # the embedding model's dimension


  class Documents(BaseAugmentationProvider[Document]):
      model = Document

      def base_query(self, req):                    # optional: limit the candidates
          return select(Document).where(Document.owner_id == req.user.id)


  class Assistant(AiService):
      ...
      augmentation_provider = Documents()
  ```

  The embedding model is loaded the first time a text is embedded (in a worker thread), not when the
  application starts, so CLI commands never load it; override `load_embedding_model()` to use
  another model. `await assistant.augmentation_provider.add_documents(texts, **columns)` embeds and stores
  documents with the same model that embeds the questions. On PostgreSQL with the pgvector extension
  the search is one query that orders by cosine distance; on other databases the candidates are
  compared in Python (`RETRIEVAL` forces either). Settings:
  `AiServiceConfig.AUGMENTATION = AugmentationConfig(MATCH_LIMIT=5, MINIMAL_SIMILARITY=0.9, ...)`.
- A missing provider for `@history` or `@augmentation` fails when the service starts.
- Other settings: `RESPONSE_FORMAT` (for example `{"type": "json_object"}`), `TEMPERATURE` (`None`
  for the provider's default), `MAX_RETRIES` (failed connections), `ORGANIZATION_ID` and
  `PROJECT_ID` (OpenAI headers).

### Admin dashboard

`patera-admin` provides a web dashboard for logs, database models, files in the static folder, task
managers and e-mail clients. It requires an [authentication](#authentication) middleware: users need
the roles from `patera.admin.Permissions`: `ADMIN_CAN_ENTER` opens the dashboard, and each action
needs it together with `ADMIN_CAN_VIEW`, `ADMIN_CAN_CREATE`, `ADMIN_CAN_EDIT` or
`ADMIN_CAN_DELETE`. A user with `ENTER` and `VIEW` can look around but not change anything.

```python
from patera.admin import AdminConfig, AdminInterface


class Admin(AdminInterface):
    managed_models = [Note]


class Config(BaseConfig):
    ...
    ADMIN: AdminConfig = AdminConfig(
        URL_FOR_FOR_LOGIN="AuthApi.login", URL_FOR_FOR_LOGOUT="AuthApi.logout",
    )
```

Admin looks up the extensions it manages (databases, task managers, e-mail clients) on every page
load, so their order in `app_extensions` does not matter. Record forms are validated with the
model's `Meta.create_validation_schema` / `update_validation_schema` when it has them. Otherwise the
values are converted to the column types (an unticked checkbox is `False`, an empty optional field
`None`), and only fields the form shows are written: fields in `exclude_from_create_form` /
`exclude_from_update_form` cannot be set through a request. The dashboard is served at
`/admin/<lang>/` (`en`, `de`, `sl`, `es`).

### Desktop applications

`patera-desktop` shows the application in a native window ([pywebview](https://pywebview.flowrl.com)).
Register the extension; it adds the CLI command `desktop:run`:

```python
from patera.desktop import Desktop, DesktopConfig


class Config(BaseConfig):
    ...
    DESKTOP: DesktopConfig = DesktopConfig(INDEX_PAGE="/")  # optional


@app(__name__, configs=Config)
class App(Patera):
    app_extensions = [Desktop]
```

`uv run patera cli desktop:run` (or `desktop:run prod`) starts the application in a separate
process, as `patera dev` (or `patera prod`) would, listening on `127.0.0.1` and the `PORT` setting.
Once it answers, a window titled with `APP_NAME` (or `DESKTOP.TITLE`) opens `INDEX_PAGE`: a path relative to `URL_PREFIX`
(default `/`) or an absolute URL. Closing the window stops the application.

`DESKTOP` also sets up the window: its size (remembered between starts), title, icon, background
color, text selection, zoom, the web inspector, and whether cookies and local storage persist
(they do by default, in the user's data folder).

`uv run patera cli desktop:package [folder]` packages the application as a program with PyInstaller
(install `patera-desktop[pyinstaller]`), by default into `dist/desktop/<APP_NAME>/`. The program runs
the server in a background thread on a free port, in production mode, through `run_in_window(App)`, and
keeps its log files in `user_data_dir(APP_NAME)` (for example `%APPDATA%\<name>`), the place for its
other data too. A program does not read `.env`: its settings come from `desktop.env`, which
`uv run patera cli desktop:env` writes from the configuration class (with `${PATERA_DATA_DIR}` for
paths in the data folder) and `desktop:package` bundles, and from the installation's `settings.env`
in the data folder (`settings_file(APP_NAME)`). The application must live in a package, which is copied next to the executable.
For hidden imports, data files, an icon or a single-file program, `uv run patera cli desktop:spec`
writes a PyInstaller spec file, `desktop.spec`, to edit; `desktop:package` builds with it. See the [patera-desktop README](packages/patera-desktop/README.md) for details, and
[`examples/desktop_notes`](examples/desktop_notes) for a complete notes program.

## Developing Patera

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): the
core package lives in `src/patera`, the extensions in `packages/`. All of them share the `patera`
namespace.

```sh
uv sync --all-packages --all-extras    # note: the AI interface pulls in PyTorch
uv run pytest                          # tests/ (unit, integration and extension tests)
PATERA_TEST_PG_URI=postgresql+asyncpg://... uv run pytest   # also run the pgvector tests
uv run pytest --cov
uv run ruff check . && uv run ruff format --check .
uv run mypy src/patera
```

Scripts in [`scripts/`](scripts/README.md) bump versions, build and publish all packages.

## License

Patera and its extension packages are released under the [MIT License](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
