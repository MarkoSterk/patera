# Changelog

All notable changes to Patera and its extension packages. Until version 1.0, a minor release may
contain breaking changes; they are listed first in each release.

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
- **Core:** blank query and form values (`?q=`) are kept as `""` instead of being dropped.
- **Core:** `Response.set_cookie()` raises `ValueError` for names or values a browser would change
  (spaces, `;`, `,`, quotes, backslashes, control characters) and for `SameSite=None` without
  `secure=True`.
- **Core:** a request header sent several times is combined into one comma-separated value
  (`Cookie` with `; `); use `Request.header_list()` for the separate values.
- **Core:** loggers read their settings only under the UPPER_SNAKE_CASE name of their class.
- **Core:** removed `patera.utilities.get_range_file()`; use `file_response()`.
- **Core:** the `@app_path` decorator is replaced by the `URL_PREFIX` setting (`PATERA_URL_PREFIX`),
  so the prefix can differ per environment: `@app_path("/demo")` becomes `URL_PREFIX: str = "/demo"`
  in the configuration class. The value must start with `/`; a trailing `/` is removed.
  `Patera.url_prefix` returns it, and `register_controller(with_base_path=...)` is now
  `with_url_prefix=...`.
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
- **patera-database:** `disconnect()` forgets the session factory, so a later session reconnects
  instead of opening connections on the disposed engine that were never closed.
- **patera-migrate:** per-database command prefixes; percent-encoded credentials in the URI are
  decoded.
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
- `augmentation_provider.embeddings` keeps only `VectorColumn`; its Python distance helpers were
  removed.
- Methods without `@history` work outside a request, and a missing history or augmentation
  provider fails at startup.
- In a `@transactional` handler the SQL history and the documents use the request's session (no
  "database is locked" on SQLite; they commit or roll back with the request). A streamed answer,
  saved after the request's transaction has ended, uses a transaction of its own.
- Concurrent writes to one chat session (two quick messages, or two summary updates) no longer get
  the same position or a second summary row: they take turns within a process, and on PostgreSQL an
  advisory lock on the session also covers other worker processes.
- `<:name>` placeholders are filled in one pass: text inserted by an argument, such as a user's
  message, can no longer pull other arguments into the prompt.
- The embedding model is loaded on first use, in a worker thread, instead of when the application
  starts (CLI commands no longer load it); `load_embedding_model()` can be overridden.

`patera-desktop` 0.11.0 is required with `patera` 0.121 (earlier versions import the removed `get_range_file()`).
