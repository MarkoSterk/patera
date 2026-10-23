# CLI controllers

```python
from patera.cli import CLIController, cli_controller, command

@cli_controller(name="greetings")
class GreetingCLI(CLIController):
    @command("repeat", help="Print a greeting several times")
    async def repeat(self, name: str, times: int = 1):
        for _ in range(times):
            print(f"Hello, {name}!")
```

Place in `app/cli/greeting_cli.py`. Invoke with
`patera cli greetings:repeat Ada 3`. Arguments are positional; annotations convert
str/int/float/bool and optional single types, with defaults for missing trailing
arguments. Do not assume arbitrary named-option parsing. Aliases must be unique.
`patera cli` and `patera cli --list` list application commands and their help.

Inject services for business operations. Extensions register CLI **instances**,
e.g. `self.app.register_cli_controller(GreetingCLI(self.app))`, unlike HTTP
controller registration, which takes classes.

Application commands construct the app in CLI mode and do not run normal ASGI
lifespan automatically. Explicitly acquire and close resources. Database commands
can use `cli_session` from `patera.database.sql`; HTTP clients need `aclose()` in
`finally`. HTTP request middleware and HTTP transaction decorators do not provide
a CLI session.

Use `patera cli --app app:App --env-file .env.tools greetings:repeat Ada` to
select an app or environment. The built-in `patera agents [codex|claude|all]`
instead generates instructions in the current directory without loading an app
or environment. `--dry-run` previews; `--force` replaces conflicting skill files.

Sources: tutorial chapter 6; architecture chapter 13.
