# Command line interface

Besides running servers, the `patera` command runs application commands: maintenance tasks,
imports, database migrations and anything else you write as a CLI controller. The built-in
commands are listed in the [CLI reference](../reference/cli.md).

## CLI controllers

Commands are methods of CLI controllers:

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
uv run patera cli --list          # list application commands and their help
```

- Arguments are **positional** and converted according to the parameter annotations (`str`,
  `int`, `float`, `bool`, optional single types and other callables). Parameters with defaults
  are optional. Named options are not parsed.
- A failing command prints the error and exits with status code `1`.
- CLI controllers support [dependency injection](dependency-injection.md) like any other
  component; inject services for the business logic.
- Controller aliases (`name=`) must be unique.

Select an application or environment file explicitly:

```sh
uv run patera cli --app app:App --env-file .env.tools maintenance:greet Ana
```

## CLI mode

The application is created in CLI mode: no HTTP server, no middleware, and **no ASGI lifespan**.
Acquire and close resources explicitly:

- database commands can use `@cli_session("main")` from `patera.database.sql`, which opens a
  session and a transaction for the command (see [SQL databases](../extensions/database.md#outside-requests)),
- HTTP clients such as an [API interface](../extensions/apiinterface.md) need `aclose()` in `finally`.

HTTP request middleware and HTTP transaction decorators do not apply to commands.

## Commands from extensions

Extensions register CLI controller **instances** (unlike HTTP controllers, which are registered
as classes):

```python
self.app.register_cli_controller(GreetingCLI(self.app))
```

This is how [migrations](../extensions/migrations.md) (`migrate:*`), the
[desktop](../extensions/desktop.md) extension (`desktop:*`) and
[desktop UI](../extensions/desktop-ui/index.md) (`ui:*`) add their commands.
