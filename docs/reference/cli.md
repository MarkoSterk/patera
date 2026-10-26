# CLI commands

## The `patera` command

| Command | Description |
| --- | --- |
| `patera dev [--app app:App] [--env-file .env]` | Development server (Uvicorn) with auto-reload. Loads `.env`, `.env.dev` or `.env.local` if no file is given. |
| `patera prod [--app app:App] [--env-file .env.prod]` | Production server (Granian, `prod` extra). `DEBUG` is forced off; only an explicit `--env-file` is loaded. |
| `patera cli [--app app:App] [--env-file FILE] Controller:command [args...]` | Runs an application [CLI command](../guide/cli.md). |
| `patera cli --list` | Lists application commands and their help. |
| `patera test [--env-file FILE] [pytest args...]` | Runs pytest after loading `.env.test` (or the given file). Everything after `--` goes to pytest unchanged. |
| `patera agents [codex\|claude\|all] [--dry-run] [--force]` | Generates [coding-agent instructions](../guide/coding-agents.md). |

See [Running the application](../getting-started/running.md) for environment files and address
resolution.

## Commands added by extensions

| Command | Extension | Description |
| --- | --- | --- |
| `migrate:init` | [Migrations](../extensions/migrations.md) | Write `.pyway.conf` into the migration directory. |
| `migrate:info` | Migrations | Show the migration status. |
| `migrate:migrate` | Migrations | Apply pending migrations. |
| `migrate:validate` | Migrations | Validate applied migrations. |
| `desktop:run [prod]` | [Desktop](../extensions/desktop.md) | Run the application in a window. |
| `desktop:package [folder] [spec]` | Desktop | Package the application with PyInstaller. |
| `desktop:spec [file]` | Desktop | Write a PyInstaller spec file to edit. |
| `desktop:env` | Desktop | Write `desktop.env` from the configuration class. |
| `ui:lock-runtime ...` | [Desktop UI](../extensions/desktop-ui/index.md) | Record the offline PyScript/Pyodide runtime. |
| `ui:build` | Desktop UI | Build the browser bundle. |
| `ui:watch` | Desktop UI | Rebuild on changes. |
| `ui:run [prod]` | Desktop UI | Build, watch and run the desktop window. |

The migration prefix is configurable per database with `MIGRATE_CLI_NAME`.
