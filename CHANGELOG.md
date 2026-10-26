# Changelog

All notable changes to Patera and its extension packages. Until version 1.0, a minor release may
contain breaking changes; they are listed first in each release.

## Unreleased

### Stabilization fixes

- **Core:** failed extension initialization rolls back framework registrations,
  routes, template paths and lifecycle callbacks. Injection cannot reuse an
  instance still initializing. Ordinary subclass overrides now remove inherited
  injection declarations, following the Python MRO.
- **Caching:** response caching defaults to GET/HEAD. Explicitly opt into other
  methods with `methods=("POST",)`; these keys include a request-body digest.
  Default handler keys now use module and qualified names. Update manual cache
  invalidation patterns using the former short names. `key` also accepts a
  synchronous or asynchronous function of the request.
- **Task manager:** persisted-job dispatch uses an optional stable
  `JOB_NAMESPACE`. Conflicting active managers are rejected instead of silently
  replacing another application's manager; registrations end at shutdown.
- **API interface:** standalone/CLI calls close temporary HTTP clients within
  their event loop. Lifespan calls continue to share a client. Explicit client
  access requires closing in the owning loop before switching loops.
- **Desktop:** shutdown waits for reloader children, with bounded forced cleanup
  using `psutil`. Settings tests no longer spoof the whole interpreter platform.
- **JoltUI:** structured error responses from decorators and lifecycle hooks
  preserve their status and media type. Successful component responses still
  require HTML. Brand spelling and package metadata are consistent.
- **Public API:** exported `MigrateConfig` (old private alias retained), added
  `patera[desktop-ui]`, and documented existing names and the `[all]` server bundle
  in `PUBLIC_API.md`. Desktop UI now includes author, project and maturity metadata.
- **Release verification:** explicit candidate/final versions are supported by
  the bump helper. Added isolated wheel installation checks, a browser-bootstrap
  syntax check, and a Python 3.13/3.14 CI matrix for Windows, Linux and macOS.

### Added

- **patera-database:** `SqlDatabaseConfig.SQLITE_FOREIGN_KEYS` (default `False`) runs
  `PRAGMA foreign_keys=ON` on every new SQLite connection, so `FOREIGN KEY` constraints such as
  `ON DELETE CASCADE` are enforced; SQLite leaves them off by default. Set it in the settings
  model or from the environment, for example `PATERA_MAIN_DB__SQLITE_FOREIGN_KEYS=true`. Other
  databases ignore it. Applications no longer need to override `SqlDatabase.connect()` for this.
- **patera-database:** `SqlDatabaseConfig.SQLITE_BUSY_TIMEOUT` (seconds, default `None`) runs
  `PRAGMA busy_timeout` on every new SQLite connection: how long a connection waits for another
  connection's lock before failing with "database is locked". `None` keeps the driver's default
  of 5 seconds, or a `?timeout=` in `DATABASE_URI`; a value takes precedence over both. Other
  databases ignore it, for example `PATERA_MAIN_DB__SQLITE_BUSY_TIMEOUT=10`.
- **patera-admin:** `FileInput` and `DateInput` form elements in `patera.admin.custom_elements`,
  for `Meta.custom_form_fields`. `FileInput` renders `<input type="file">` (with `accept` and a
  browser-side `max_size`); the model's admin hooks receive the chosen file as an `UploadedFile`,
  and when no file is chosen the field is not sent, so an update keeps the current value.
  `DateInput` renders a date or, with `include_time=True`, a date-and-time picker; its value is
  converted to the column's type like a generated input, and `utc=True` shows a stored UTC
  timestamp in the viewer's local time and submits it in UTC. Custom elements opt in to that
  conversion with `converts_value = True`.
- **patera-admin:** `LatexInput` form element: a textarea, or a text input with
  `multiline=False`, for text with LaTeX math, with a preview underneath that updates while the
  user types. Math goes between `$...$` or `$$...$$`, and `\$` is a literal dollar sign. The
  preview is rendered as MathML by [Temml](https://temml.org) 0.14.0 (MIT), which Admin serves
  from its own static assets (`js/vendors/temml/`) and loads only on pages with this input. The
  inner control is an ordinary form field, so it is submitted and validated with the form.

- **Core:** request observers. `app.add_request_observer(callback)` calls `callback(record)` after
  every HTTP request, including router answers (404, 405), static resources and failed requests,
  with a `patera.RequestRecord`: method, path, the matched URL rule (`/api/exams/<exam_id>`, or
  `None` when no route matched), the status sent (500 for a failure before the response started),
  the start time and the duration. An observer that raises is logged and skipped; applications
  without observers take the previous code path. `Router.path_of(endpoint)` returns an endpoint's
  URL rule.
- **patera-admin:** request statistics on the dashboard, above the logs: uptime and start time,
  requests and average requests/s, 2xx/4xx/5xx counts with their share, average and approximate
  95th-percentile response time, a stacked requests-per-second chart by status class, a response
  time chart, the busiest endpoints and the most frequent 4xx/5xx statuses with their routes, for
  the last 15 minutes, hour, 6 hours or 24 hours, refreshed every 10 seconds. Admin collects them
  in memory through a request observer (24 hours, 10-second buckets), so each worker shows its own
  requests since it started; the dashboard's own polling is not counted.
  `AdminConfig.REQUEST_STATISTICS=False` turns the collection and the section off. The data is
  served as JSON at `<ADMIN_BASE_URL>/<lang>/dashboard/stats?period=1h`.

### Fixed

- **patera-admin:** the log table's page links no longer run off the right edge when there are many
  pages. Like the records table, they show the first and last page and two pages on each side of
  the current one, with ellipses between; on small screens only the neighbouring pages and arrow
  buttons are shown, and the links wrap if space runs out. Both tables share one template macro
  (`_admin/layout/pagination.html`) and `patera.admin.pagination.page_items()`.
- **Core:** a `Response[Model]` body made of ORM objects is converted through its declared type
  as soon as the route handler returns, while the request's database sessions are still open.
  Before, it was converted when the response was sent, after `patera-database` had rolled back
  (requests without `@transactional`) or committed with `EXPIRE_ON_COMMIT=True` and closed the
  session, so reading the expired objects failed with `DetachedInstanceError` (`500`). A body that
  does not fit its type now fails inside the middleware chain, so a `@transactional` request is
  rolled back instead of committed; the answer is still `500`. Streamed bodies are not converted
  early, and relationships must be loaded eagerly. `patera.serializers.materialize()` and
  `ResponseRenderer.materialize_body()` perform the conversion.
- **patera-admin:** record dialogs no longer overflow the window: the form inside each dialog is
  now the flex column, so the header and footer stay visible and the body scrolls.
- **patera-admin:** a custom form element gets its own id in the create and update dialogs
  (`create-field-<name>`, `update-field-<name>`); both used `create-field-<name>`, and the update
  dialog's label pointed at the create form. Elements without content, such as `<input>`, are
  rendered without a closing tag.
- **patera-admin:** a model's `admin_delete()` hook can refuse a deletion by raising
  `AdminFormError`: Admin answers `422` with the first error's message, which the records table
  shows (it was a `500`).
- **patera-admin:** an unknown database or model in a records-table URL shows the Admin error page
  with `404` (rendering the page failed because the template context was missing).
- **patera-admin:** the sign-in and "unauthorized" pages load Bootstrap and its icons from the
  copies shipped with the package instead of jsDelivr, so Admin works without internet access.

## patera 0.121.0 and extensions 0.11.0 (2026-10-12)

Every package in this release requires `patera>=0.121`. Upgrade the core and the extensions
together.

### Breaking changes

- **patera-auth:** signed cookie values carry a signing timestamp (`value|timestamp|signature`).
  Values signed by earlier versions are rejected, which signs users out once.
- **patera-caching:** Redis and SQLite keys default to the prefix `patera:<app name>:<cache name>:`
  instead of `patera:cache:` (Redis) or no prefix (SQLite), so existing cache entries are not found.
  Set `KEY_PREFIX` to keep the old keys. `BaseCacheBackend.from_configs()` takes a `namespace`
  argument, and `configure_from_app()` is gone; use `backend_class` or `from_configs()`.
- **patera-migrate:** `.pyway.conf` no longer contains connection details. The connection, including
  the password, is read from `DATABASE_URI` each time a command runs. The file stays in the migration
  directory and in `.gitignore`; regenerate it with `migrate:init` (delete the old one first) or
  remove the connection lines, because a `database_*` value left in the file overrides the URI.
- **patera-admin:** Slovenian uses the ISO code `sl` instead of `si` (URLs, `DEFAULT_LANGUAGE`).
- **patera-apiinterface:** a 4xx or 5xx response raises `ApiInterfaceResponseError` instead of being
  returned as data. Request forwarding is opt-in with `@forward_request`; method arguments fill
  `<name>` placeholders and become query parameters or the body.
- **patera-database:** `@query` methods annotated `-> None` return `None`; `-> int` on a statement
  without result rows returns the number of affected rows.
- **Core:** a settings model declared in the config class without a value (`MAIN_DB:
  SqlDatabaseConfig`) is built from the environment (and `.env`), with the model's defaults for
  the fields no variable sets; with no variable at all, from the defaults alone. A required field
  that nothing sets is reported by name (`MAIN_DB.DATABASE_URI`), instead of the whole model
  being "required".
- **Core:** Granian is no longer installed with the core package. `patera prod` needs the new
  `prod` extra: `uv add "patera[prod]"` (or `pip install "patera[prod]"`); without it, the command
  says so. The core's own dependencies are now pure Python apart from pydantic-core.
- **Core:** blank query and form values (`?q=`) are kept as `""` instead of being dropped.
- **Core:** the OpenAPI document's server is relative (`URL_PREFIX`, or `/`) instead of
  `PROTOCOL://HOST:PORT`, so Swagger's "Try it out" calls the origin that served the page.
- **Core:** `patera test` loads `.env.test` only when it exists (an explicit `--env-file` must
  exist), runs pytest without arguments by default so pytest's own configuration (`testpaths`)
  applies, and no longer has the unused `--app` option.
- **Core:** `Response.set_cookie()` raises `ValueError` for names or values a browser would change
  (spaces, `;`, `,`, quotes, backslashes, control characters) and for `SameSite=None` without
  `secure=True`.
- **Core:** a request header sent several times is combined into one comma-separated value
  (`Cookie` with `; `); use `Request.header_list()` for the separate values.
- **Core:** loggers read their settings only under the UPPER_SNAKE_CASE name of their class.
- **Core:** removed `patera.utilities.get_range_file()`, `get_file()` and `Response.send_file()`;
  use `file_response()`, which streams the file and takes a `download_name`.
- **Core:** `CORS_ALLOW_CREDENTIALS` defaults to `False`: by default no website may make
  cross-origin requests with the user's cookies. Set it to `True` together with an explicit
  `CORS_ALLOW_ORIGINS` list for a frontend on another origin.
- **patera-admin:** a signed-in user without the needed Admin permission gets 403 instead of 401
  (with `"status": "error"`), and an unknown database name gets 404.
- **Core:** the `@app_path` decorator is replaced by the `URL_PREFIX` setting (`PATERA_URL_PREFIX`),
  so the prefix can differ per environment: `@app_path("/demo")` becomes `URL_PREFIX: str = "/demo"`
  in the configuration class. The value must start with `/`; a trailing `/` is removed.
  `Patera.url_prefix` returns it, and `register_controller(with_base_path=...)` is now
  `with_url_prefix=...`.
- **Core:** invalid `@consumes` data raises `RequestValidationError` (a `BaseHttpException`):
  `422` with `{"status", "message", "data": [errors]}`, without the submitted values. Handle
  `RequestValidationError` instead of `pydantic.ValidationError`; its `errors` attribute is the list.
  A `ValidationError` raised anywhere else (handler code, data from a database or another service)
  is a server error (`500`) instead of a `422` that echoed the values. Validate query parameters and
  other client data with the new `req.validate(Model, data)`.
- **Core:** `res.json()` raises `TypeError` for `str` and `bytes`; use `text()`, or
  `bytes(data, MediaType.APPLICATION_JSON.value)` for already encoded JSON.
- **Core:** `UploadedFile.read(size)` reads like a file, from the current position onwards
  (it always returned the first bytes, so chunked readers never finished).
- **Core:** two controller classes with the same name raise `ValueError` at startup (the second was
  silently skipped). A WebSocket handler, or its controller, marked with `@login_required`,
  `@role_required` or `@transactional` raises `ValueError` at startup: middleware does not run for
  sockets, so these had no effect.
- **Core:** removed the unused `patera.request.extract_boundary()`.
- **patera-admin:** every action needs `ADMIN_CAN_ENTER` and its own permission (`VIEW`, `CREATE`,
  `EDIT`, `DELETE`); `ADMIN_CAN_ENTER` alone allowed every action. Give administrators all five.
- **patera-admin:** record forms of models without a validation schema are converted to the column
  types, and only the fields the form shows are written: a field excluded from the form can no
  longer be set by adding it to the request. An unticked checkbox sets `False`.
- **patera-taskmanager:** `@schedule_job` jobs without an `id` get `<class>.<method>` instead of a
  random id, and every declared job replaces its stored copy at startup.
- **patera-caching:** responses are cached as the bytes that are sent, and the Redis and SQLite
  backends store JSON instead of pickle. Existing entries are treated as misses.
- **Core:** dropped the unused dependencies h11, httpcore, idna, mako and markupsafe; websockets
  moved to the `dev` extra (used by the uvicorn development server). httpx and asgi-lifespan, used
  only by the test client, moved to the `testing` extra: install `patera[testing]` to use
  `patera.testing.PateraTestClient`.

### Added

- **Core:** `MAX_CONTENT_LENGTH` (default 10 MB) and the `@max_content_length` decorator; larger
  bodies get 413.
- **Core:** `BACKGROUND_TASKS_SHUTDOWN_TIMEOUT` (default 10 s): on shutdown the application waits
  for `run_in_background()` tasks before closing resources, then cancels and logs the rest.
- **Core:** `STARTUP_BANNER` setting; the startup line is always logged.
- **Core:** `patera dev` and `patera prod` resolve the address from `PATERA_HOST`/`PATERA_PORT`,
  then the config class defaults, then `localhost:3000` (dev) or `0.0.0.0:80` (prod), and the
  application reports the address actually used.
- **Core:** `patera cli` without a command name lists every command.
- **Core:** `Request.cookies`, `Request.header_list()`, `Request.query_list()`,
  `Request.form_list()`.
- **Core:** static files (and Admin static files) send `ETag`, `Last-Modified` and `Cache-Control`,
  answer conditional requests with 304, honour `If-Range`, and are always sent zero-copy.
- **Core:** NDJSON streaming with `ndjson_line()`; `SerializerRegistry.register(first=)`,
  `replace()` and `unregister()`.
- **Core:** `DuplicateRouteError` and `CircularDependencyError` with clear messages.
- **Core:** `is_async_callable()` and `wait_for_background_tasks()` utilities; `py.typed` marker.
- **Core:** `Request.validate()`, `RequestValidationError`, `ClientDisconnected` and
  `Request.response_started`.
- **patera-auth:** `role_required(..., require_all=True)` requires every listed role.
- **patera-auth:** `decode_signed_cookie(..., max_age=...)` rejects old values.
- **patera-auth:** new password hashes are `bcrypt-sha256$` + bcrypt over a SHA-256 digest, so
  passwords of any length count in full. Plain bcrypt hashes from earlier versions still verify;
  `password_hash_needs_update()` tells you when to store a new hash after a successful login.
- **patera-admin:** severity filter for log records, notifications (`admin.notify()`, the header
  bell, failed e-mail sends recorded automatically), the application and Admin versions in the
  footer, and extension discovery on every request.
- **patera-apiinterface:** `ApiInterfaceResponseError`; `-> httpx.Response` returns the raw response
  unchecked; NDJSON responses are parsed line by line; one shared HTTPX client per event loop, closed
  at shutdown (`create_client()`, `aclose()`).
- **patera-caching:** per-user cache entries by default (`per_user`, `user_cache_key()`),
  `backend_class`, `Caching.cache_name`.
- **patera-database:** `background_session()` and `SqlDatabase.session_scope()` for work outside a
  request; `SqlDatabase.work_session()` for a service's own work (the request's session in a
  `@transactional` request, its own transaction elsewhere), `request_session()` and
  `in_transactional_request()`.
- **patera-email:** `USE_SSL` (implicit TLS), HTML messages with a generated plain-text
  alternative, and `Date` and `Message-ID` headers on every message.

### Fixed

- **Core:** uploaded files are no longer altered: the body is parsed as received (part headers
  were rewritten anywhere in the body, including inside file content). Field and file names are
  decoded as UTF-8.
- **Core:** JSON bodies may contain models, lists of models, dates, UUIDs, decimals and enums
  (they failed with 500), and `Response[list[Model]]` and other generic annotations filter every
  item like `Response[Model]` does; ORM objects are accepted too. NDJSON rows are encoded the
  same way. The declared type shapes only 2xx bodies, so error bodies such as the `415` from
  `@consumes` keep their own fields.
- **Core:** `file_response(download_name=...)` writes a correct `Content-Disposition` for names in
  any language (`content_disposition()`).
- **Core:** an explicit middleware order of `0` is kept.
- **Core:** an error after a streamed or file response has started is logged and the connection is
  closed, instead of a second response being attempted.
- **Core:** a client that disconnects before its body has arrived raises `ClientDisconnected`; the
  truncated body was handled as if it were complete. No response is sent.
- **Core:** a malformed multipart body (missing or wrong boundary) answers `400` instead of `500`.
- **Core:** a form field the `@consumes` model declares as a list accepts a single value.
- **Core:** a controller property that needs a request (`current_request.user`) no longer fails
  at registration.
- **Core:** raw non-UTF-8 bytes in a query string no longer fail the request before a response.
- **Core:** CLI arguments annotated `Optional[int]` or `int | None` are converted.
- **Core:** `@produces(..., status_code)` no longer overrides an explicit `.status(200)`
  (`Response.status_set`).
- **Core:** every response of a route with CORS enabled carries `Vary: Origin`, also without an
  `Origin` header, for a refused origin and for routing errors, so shared caches keep the
  variants apart.
- **Core:** logging works again when the application's lifespan runs a second time (the shutdown
  removed the sinks for good).
- **patera-admin:** record forms of models without a validation schema failed for boolean columns
  (always) and number and date columns (PostgreSQL); records with an integer key could not be
  viewed, edited or deleted on PostgreSQL. Values and keys are converted to the column types.
- **patera-admin:** an unknown database or model on a record page answers 404, and an unknown
  e-mail sender 400, instead of 500.
- **patera-taskmanager:** a persistent job store (`SQLAlchemyJobStore`, ...) made startup fail,
  because jobs were stored as bound methods. Methods of the task manager are now stored by name
  (`run_scheduled_job`); `job_callable(job)` returns the method a job runs.
- **Core:** the missing-configuration error names the `@app(...)` decorator.
- **Core:** database sessions opened in a WebSocket handler are closed when it returns.
- **patera-database:** `session_scope()` (and `work_session()` outside `@transactional`) inside a
  request keeps the request's user and request object, leaves the request's sessions alone, and
  closes other databases' sessions opened in the block (they leaked).
- **patera-auth:** `@login_required` and `@role_required` keep a custom exception class in either
  stacking order.
- **patera-taskmanager:** jobs declared with `@schedule_job` are added again when the application's
  lifespan runs again.
- **Core:** an environment variable for one field of a nested setting
  (`PATERA_ASSISTANT__API_KEY`) keeps the other fields of the class default instead of failing
  them as missing.
- **Core:** invalid UTF-8 in a form body answers 400 instead of failing; malformed cookies are
  skipped; a file that shrinks while being sent ends the response properly; CORS headers on routing
  errors; consistent `{"status", "message", "data"}` error bodies; `run_sync_or_async()` awaits
  async callable objects and `functools.partial` objects instead of running them in a thread.
- **patera-admin:** missing task manager translations; sorting by level follows severity and line
  numbers sort numerically; unknown sort columns fall back to newest first.
- **patera-auth:** passwords longer than 72 bytes no longer raise, and a malformed stored hash no
  longer crashes the check.
- **patera-caching:** the memory backend honours per-entry durations longer than its default; SQLite
  `clear()` treats `_` and `%` in the prefix literally; Redis `clear()` refuses to run without a
  prefix.
- **patera-database:** `@query` INSERT, UPDATE and DELETE statements no longer crash.
- **patera-database:** removed `DeclarativeBaseModel.db_configs_name()`, which always raised
  `AttributeError`.
- **patera-database:** `disconnect()` forgets the session factory, so a later session reconnects
  instead of opening connections on the disposed engine that were never closed.
- **patera-migrate:** per-database command prefixes; percent-encoded credentials in the URI are
  decoded.
- **Core:** `patera test` accepts pytest options in any order (`patera test -k login -q` failed with
  "unrecognized arguments"), and a missing environment file is a one-line error instead of a
  traceback.
- **Core:** when auto-discovery finds no application because a module failed to import, the error
  names that module instead of asking for an import string.
- **Core:** routes joined from `@path("/")` and `@get("/hello")` are stored as `/hello`, not
  `//hello`.
- **patera-migrate:** `MIGRATE_SQL_MIGRATION_PREFIX`, `_SEPARATOR` and `_SUFFIXES` now take effect
  (they were ignored); files in the migration folder with another ending are skipped, and a
  misnamed migration is an error. pyway is limited to `<0.4`.
- **patera-taskmanager:** the scheduler is the single source of truth for job state; APScheduler is
  limited to version 3 (`<4`), since version 4 changes its API.

### Experimental packages

`patera-aiinterface` and `patera-desktop` are marked Alpha.

**patera-aiinterface 0.11.0:**
- The embedding libraries moved to the `augmentation` extra
  (`pip install "patera-aiinterface[augmentation]"`) and are imported only when an augmentation
  provider starts; the unused `openai` and `docstring-parser` dependencies are gone.
- One vector column type: pgvector's (`augmentation_provider.embeddings.VectorColumn`); the
  package's own `database_types.Vector` was removed.
- Removed the unused `STREAM` and `TOOL_CHOICE` settings and the `@tool` decorator. `RESPONSE_FORMAT`
  now defaults to plain text and is sent when set; `ORGANIZATION_ID`, `PROJECT_ID` and
  `MAX_RETRIES` are used; `TEMPERATURE=None` leaves the provider's default.
- The history stores the user's message without the augmentation texts, and nothing is saved when
  the call fails.
- `AUGMENTATION` settings default when not configured; the embedding model cache no longer changes
  process-wide environment variables.
- The chat pipeline lives in `AiService`: current system prompt, then the session's history, then
  the user message (with augmentation texts when used). Service providers only send messages:
  `BaseServiceProvider.complete(messages, configs)` and `stream(messages, configs)`.
- `@history` methods take an explicit `session_id` argument (`None` starts a new session, returned
  in `ChatResponse.session_id`); the route-based `@session_id` decorator was removed.
- `BaseHistoryProvider` is a small interface (`load`, `append`, `new_session_id`), and
  `SqlHistoryProvider` stores messages in its own transaction, so history works outside requests
  and needs no commit by the handler.
- The system prompt is no longer stored in the history; the current one is always sent.
- `HISTORY_LIMIT` (default 10) caps how many earlier messages are sent.
- `HISTORY_SUMMARY` (`HistorySummaryConfig`): a rolling summary of older messages is sent instead
  of them and updated in the background (one extra call every `EVERY` messages). It is stored as a
  `role="summary"` row of the messages table; `SqlHistoryProvider` supports it out of the box.
- Streaming methods are iterated directly: `async for chunk in service.method(...)`.
- Retrieved documents go in a context message before the user message (`CONTEXT_TEMPLATE`)
  instead of being pasted under the question.
- On PostgreSQL the document search is one pgvector query (closest documents by cosine distance);
  other databases compare the candidates in Python (`RETRIEVAL`: auto, database or python).
  `base_query()` limits the candidates; `add_documents()` / `add_document()` embed and store texts;
  `embed()`, `search()` and `relevant_texts()` are public.
- `REWRITE_QUERY`: with history, the model first rewrites a follow-up question into a standalone
  one for the search (`REWRITE_PROMPT`).
- `ChatMessage` has only `role` and `content` (the unused `thinking`, `name` and `tool_call_id`
  fields and the `"tool"` role are gone). Ollama reports `finish_reason="length"` for an answer cut
  off at the token limit; OpenAI answers fill `request_id`, and `created_at` is ISO 8601 text for
  both providers.
- `augmentation_provider.embeddings` keeps only `VectorColumn`; its Python distance helpers were
  removed.
- Methods without `@history` work outside a request, and a missing history or augmentation
  provider fails at startup.
- In a `@transactional` handler the SQL history and the documents use the request's session (no
  "database is locked" on SQLite; they commit or roll back with the request). A streamed answer,
  saved after the request's transaction has ended, uses a transaction of its own.
- Concurrent writes to one chat session (two quick messages, or two summary updates) no longer get
  the same position or a second summary row, also across worker processes and inside
  `@transactional` requests that commit later: each write first locks the chat session until it
  commits, with an advisory lock on PostgreSQL and the database's write lock on SQLite. That lock is
  taken before the in-process one, so a write waiting for another request's commit no longer
  deadlocks that request's next write (on PostgreSQL it waited forever). Other databases take turns
  within a process.
- `<:name>` placeholders are filled in one pass: text inserted by an argument, such as a user's
  message, can no longer pull other arguments into the prompt.
- The embedding model is loaded on first use, in a worker thread, instead of when the application
  starts (CLI commands no longer load it); `load_embedding_model()` can be overridden.
- Document search decides between pgvector and Python from the database URI, so it works before
  the database has connected (it failed with "Engine not initialized", e.g. in CLI commands).

**patera-desktop:** rewritten, with only one feature for now. The `Desktop` extension adds the CLI
command `desktop:run [dev|prod]`: it starts the application in a separate process, as `patera dev`
or `patera prod` would (on `127.0.0.1` and the `PORT` setting), shows `DESKTOP.INDEX_PAGE` (default
`/`) in a pywebview window, and stops the application when the window is closed. The launcher, the
frontend bridge, frontend tools and the `PATERA_DESKTOP_*` settings are gone, and so is the core
command `patera desktop`. `python -m patera.cli` now runs the `patera` command. `desktop:package
[folder]` packages the application as a program with PyInstaller (extra
`patera-desktop[pyinstaller]`), by default into `dist/desktop/<APP_NAME>/`: the program runs the
server in a background thread with `run_in_window(App)`, on a free port, and writes its log files to
`user_data_dir(APP_NAME)`. Before the application starts, `run_in_window` loads the installation's
settings file, `settings_file(APP_NAME)` (`settings.env` in that folder), like `.env` during
development. The package ships a PyInstaller hook so the `patera.*` extensions are found also in
editable (workspace) installs. Window settings in `DESKTOP`: `TITLE`, `WIDTH`/`HEIGHT` (1024 × 720),
`MIN_WIDTH`/`MIN_HEIGHT`, `REMEMBER_GEOMETRY` (size, position and maximized state restored at the
next start, on by default), `MAXIMIZED`, `FULLSCREEN`, `RESIZABLE`, `ON_TOP`, `CONFIRM_CLOSE`,
`BACKGROUND_COLOR`, `TEXT_SELECT` (on), `ZOOMABLE`, `PERSIST_STORAGE` (cookies and local storage
kept in the user's data folder, on by default; pywebview forgets them at every close otherwise),
`ICON` (also the spec file's default icon), `DEV_TOOLS` and `GUI`. `desktop:env` writes
`desktop.env`, the packaged program's settings: every setting the configuration declares, defaults
commented out, required ones empty. `desktop:package` bundles it, refuses to build while a required
setting is empty, and warns about values that look like secrets. The program loads environment
variables, then the installation's `settings.env`, then `desktop.env`; `${PATERA_DATA_DIR}` is the
user's data folder. `desktop:run` loads `desktop.env` under the development `.env`. A configuration
that declares `SECRET_KEY` gets a key per installation, made at the first start and kept in
`settings.env`. A packaged program reuses the port of its last start, so the page's origin and local
storage stay the same. `user_data_dir` also knows iOS (Application Support in the app's sandbox) and
Android (the app's internal storage, `$HOME`). `desktop:spec [path]` writes a PyInstaller spec file
(default `desktop.spec`) with the defaults as settings to edit (hidden imports, data files, icon,
console, one file, own entry script). The application package is copied without what running and
developing it leave there (`__pycache__`, log files, SQLite databases, `.env`, tool caches;
`PACKAGE_EXCLUDES` in the spec file). `desktop:package [folder] [spec]` builds with the spec file
when it exists, otherwise with a generated one in `build/desktop/`. patera-desktop now depends on
uvicorn.
