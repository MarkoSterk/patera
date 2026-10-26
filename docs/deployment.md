# Deployment

## The production server

```sh
uv add "patera[prod]"
uv run patera prod --env-file .env.prod
```

`patera prod` runs [Granian](https://github.com/emmett-framework/granian) with `DEBUG` forced off.

- Only an environment file named with `--env-file` is loaded; values in the process environment
  win.
- The address comes from `PATERA_HOST` / `PATERA_PORT`, then the defaults on your config class,
  then `0.0.0.0:80`. `localhost` is mapped to `0.0.0.0`.
- `PATERA_LOOP` selects the event loop.
- The application is found in the conventional `app` package; select another with
  `--app module:Class` or `PATERA_IMPORT`.

Any other ASGI server works with the application factory:

```sh
uvicorn app:App --factory --lifespan on
```

## Checklist

- [x] **Keep the ASGI lifespan enabled.** Database connections, caches, schedulers and cleanup
  hooks depend on it.
- [x] **Set `DEBUG=False`** (`patera prod` does this). Unhandled errors then become a neutral
  `500` and are logged.
- [x] **Apply reviewed [migrations](extensions/migrations.md)** as an explicit deployment step.
- [x] **Restrict CORS** with an explicit `CORS_ALLOW_ORIGINS` list, especially with credentials.
- [x] **Keep secrets in the environment**, not in the configuration class or the repository.
- [x] **Persist data outside replaceable images**: databases, uploads and the log files you need.
  Never put private uploads under the public static directory.
- [x] **Match the proxy's path handling** to `URL_PREFIX` and `STATIC_URL`. Static files can be
  served by the reverse proxy directly.
- [x] **Add a health endpoint** that checks the readiness you depend on.
- [x] **Pin dependencies** and test the production configuration.

## Several workers

Each worker process has its own singletons, in-memory caches and schedulers:

- the in-memory [cache](extensions/caching.md) backend is not shared; use Redis or SQLite for a
  shared cache,
- [scheduled jobs](extensions/taskmanager.md) run in every worker that starts a scheduler;
  choose one scheduler owner or add distributed coordination (job IDs do not prevent execution in
  several processes),
- [log file](guide/logging.md#log-files) rotation is not coordinated between processes: set
  `ROTATION=None` and rotate externally, or run a single worker,
- the [admin dashboard](extensions/admin.md) request statistics are per worker.

## Containers

Docker Compose and similar tools are optional; follow your project's deployment system. A minimal
image installs the project with uv and runs `patera prod`:

```dockerfile
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv/app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
RUN uv sync --locked --no-dev
ENV PATERA_HOST=0.0.0.0 PATERA_PORT=8000
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "patera", "prod"]
```

Provide the environment (database URL, secret key, ...) at runtime, and mount volumes for
persistent data.

## Desktop programs

To ship the application as a desktop program instead of a server, see
[Desktop applications](extensions/desktop.md#packaging-a-program).
