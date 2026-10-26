# Configuration options

Built-in options of `patera.BaseConfig`. Every option can be set from the environment with the
`PATERA_` prefix; nested values use `__` (see [Configuration](../guide/configuration.md)).

## Application

| Option | Default | Description |
| --- | --- | --- |
| `BASE_PATH` | *required* | Directory of the application package (`os.path.dirname(__file__)`). |
| `APP_PACKAGE` | `"app"` | Name of the application package. |
| `APP_NAME` | `"Patera app"` | Human readable name (logs, OpenAPI title). |
| `VERSION` | `"1.0"` | Application version (OpenAPI). |
| `DEBUG` | `True` | Debug mode. Unhandled exceptions propagate in debug mode and become a generic 500 response otherwise. `@development` routes only exist in debug mode. |
| `LIFESPAN` | `"on"` | For custom run scripts; `patera dev`/`prod` always enable lifespan. |
| `REQUEST_CLASS` / `RESPONSE_CLASS` | `Request` / `Response` | Custom subclasses of the request/response classes. |
| `BACKGROUND_TASKS_SHUTDOWN_TIMEOUT` | `10.0` | Seconds to wait on shutdown for `run_in_background()` tasks before cancelling them (`None`: no limit). |

## Server

| Option | Default | Description |
| --- | --- | --- |
| `HOST` / `PORT` / `PROTOCOL` | `"localhost"` / `3000` / `"http"` | Where the server listens and what the startup line and OpenAPI server URL report. `patera dev`/`prod` take `PATERA_HOST`/`PATERA_PORT`, then defaults set on your config class, then `localhost:3000` (dev) or `0.0.0.0:80` (prod). |
| `STARTUP_BANNER` | `True` | Print the banner and address box on startup; the startup line is always logged. |
| `MAX_CONTENT_LENGTH` | `10485760` (10 MB) | Largest accepted request body; `None` for no limit. Override per route with `@max_content_length`. |

## Routing

| Option | Default | Description |
| --- | --- | --- |
| `URL_PREFIX` | `""` | Prefix of every controller route, for example `"/api/v1"`. It must start with `/`; a trailing `/` is removed. Static files keep `STATIC_URL`. |
| `STRICT_SLASHES` | `False` | If `False`, `/users` and `/users/` match the same route. |

## Templates, static files and pages

| Option | Default | Description |
| --- | --- | --- |
| `TEMPLATES_DIR` | `"templates"` | Template folder, relative to `BASE_PATH`. |
| `TEMPLATES_STRICT` | `True` | Undefined template variables raise errors. |
| `AUTO_RELOAD` | `True` | Reload changed templates. |
| `STATIC_DIR` / `STATIC_URL` | `"static"` / `"/static"` | Static files folder and URL prefix. |
| `STATIC_CONTROLLER_NAME` | `"static"` | `url_for` alias for static files: `url_for("static", filename="app.css")`. |
| `USE_STATIC_PAGES` | `False` | Serve HTML pages from `STATIC_PAGES_DIR`. |
| `STATIC_PAGES_DIR` / `STATIC_PAGES_URL` | `"static_pages"` / `"/"` | Static pages folder and URL prefix. |
| `STATIC_PAGES_CONTROLLER_NAME` | `"static_pages"` | `url_for` alias for pages: `url_for("static_pages", page="about")`. |

## OpenAPI

| Option | Default | Description |
| --- | --- | --- |
| `OPEN_API` | `True` | Serve the specification and Swagger UI. |
| `OPEN_API_URL` | `"/openapi"` | Base URL of the documentation. |
| `OPEN_API_DESCRIPTION` | `"Simple API"` | Description in the specification. |

## CORS

| Option | Default | Description |
| --- | --- | --- |
| `CORS_ENABLED` | `True` | Global CORS handling. |
| `CORS_ALLOW_ORIGINS` | `["*"]` | Allowed origins. |
| `CORS_ALLOW_METHODS` | `["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]` | Allowed methods. |
| `CORS_ALLOW_HEADERS` | `["Authorization", "Content-Type"]` | Allowed request headers. |
| `CORS_EXPOSE_HEADERS` | `[]` | Response headers exposed to the browser. |
| `CORS_ALLOW_CREDENTIALS` | `False` | Allow credentials: cookies and `Authorization` on cross-origin requests (the request origin is echoed instead of `*`). Turn it on only together with an explicit `CORS_ALLOW_ORIGINS` list. |
| `CORS_MAX_AGE` | `None` | Preflight cache time in seconds. |

## Logging

| Option | Default | Description |
| --- | --- | --- |
| `DEFAULT_LOGGER` | `DefaultLoggerConfig()` | Default console sink, see [Logging](../guide/logging.md#the-default-sink). |
| `LOG_FILES` | `LogFilesConfig()` | Rotating JSON Lines log files read by the admin dashboard, see [Logging](../guide/logging.md#log-files). |

## Discovery

| Option | Default | Description |
| --- | --- | --- |
| `CONTROLLER_FOLDERS`, `CLI_CONTROLLER_FOLDERS`, `EXCEPTION_HANDLER_FOLDERS`, `MIDDLEWARE_FOLDERS`, `LOGGER_FOLDERS` | `None` | Additional folders for [auto-discovery](../getting-started/project-layout.md). |

## Environment variables of the `patera` command

| Variable | Description |
| --- | --- |
| `PATERA_IMPORT` | `module:Class` of the application. |
| `PATERA_APP_PACKAGE` | Name of the application package, if not `app`. |
| `PATERA_HOST` / `PATERA_PORT` | Server address. |
| `PATERA_LOOP` | Event loop of `patera prod`. |

## Extension settings

Extension settings are fields named after your extension subclass. See each
[extension page](../extensions/index.md) for its configuration model.
