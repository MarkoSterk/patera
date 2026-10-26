# Running the application

The `patera` command finds your application class automatically: it looks for the class
decorated with `@app` in `app/__init__.py`, `app/app.py`, `app/main.py`, ... Use
`--app module:Class` or the `PATERA_IMPORT` environment variable to point at it explicitly, and
`PATERA_APP_PACKAGE` if your package is not called `app`.

| Command | Description |
| --- | --- |
| `patera dev [--app app:App] [--env-file .env]` | Development server (Uvicorn) with auto-reload. Loads `.env`, `.env.dev` or `.env.local` if no file is given. Host and port from `PATERA_HOST`/`PATERA_PORT` (default `localhost:3000`). |
| `patera prod [--app app:App] [--env-file .env.prod]` | Production server ([Granian](https://github.com/emmett-framework/granian), installed with the `prod` extra), `DEBUG` is forced off. Only an environment file given with `--env-file` is loaded. Host and port from `PATERA_HOST`/`PATERA_PORT` (default `0.0.0.0:80`), event loop from `PATERA_LOOP`. |
| `patera cli Controller:command [args...]` | Runs a [CLI command](../guide/cli.md). |
| `patera agents [codex\|claude\|all]` | Generates [coding-agent instructions](../guide/coding-agents.md) and Patera skills without loading an application. |
| `patera test [--env-file FILE] [pytest args...]` | Runs pytest after loading the test environment file (`.env.test` when the project has one). See [Testing](../guide/testing.md). |

=== "Development"

    ```sh
    uv run patera dev
    ```

=== "Production"

    ```sh
    uv add "patera[prod]"
    uv run patera prod --env-file .env.prod
    ```

## Environment files

- `patera dev` and application CLI commands load an explicit `--env-file`, or search `.env`,
  `.env.dev` and `.env.local` in that order.
- `patera prod` loads **only** an environment file named with `--env-file`.
- `patera test` loads `.env.test` when present; an explicit `--env-file` must exist.
- Values already present in the process environment win over values from the file.

## Address

The address is resolved in this order:

1. `PATERA_HOST` / `PATERA_PORT` environment variables,
2. defaults set on your configuration class (`HOST`, `PORT`),
3. launcher defaults: `localhost:3000` for `dev`, `0.0.0.0:80` for `prod`.

In production, `localhost` is mapped to `0.0.0.0`. Configure the deployment address explicitly.

## Other ASGI servers

The application class is an ASGI application factory, so any ASGI server works:

```sh
uvicorn app:App --factory --lifespan on
```

!!! warning "Keep lifespan enabled"

    Startup and shutdown hooks (database connections, schedulers, caches, ...) depend on the ASGI
    lifespan protocol. Simply calling `App()` does not start resource hooks.

See [Deployment](../deployment.md) for production advice.
