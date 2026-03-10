"""
CLI controller module for PyJolt.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Callable, cast, Type
from functools import wraps

from ..utilities import run_sync_or_async

if TYPE_CHECKING:
    from ..pyjolt import PyJolt


class CLIController:
    """
    Base class for CLI controllers.
    This class automatically registers methods decorated with @command and @argument
    as CLI commands in the provided PyJolt app instance.
    """

    def __init__(self, app: "PyJolt", cli_commands: dict):
        self._app: "PyJolt" = app
        self._cli_commands: dict = cli_commands
        self._register_commands()

    def _register_commands(self):
        for attr_name in dir(self):
            method = getattr(self, attr_name)
            if callable(method):
                command = getattr(method, "cli_command", {})
                if command.get("is_cli_command", False):
                    self._register_command(method, command)

    def _register_command(self, method: Callable, command: dict):

        cli_command = self._app.subparsers.add_parser(
            cast(str, command.get("command_name")),
            help="Initialize the Alembic migration environment.",
        )
        for arg_name, arg_info in command.get("arguments", {}).items():
            if arg_name.startswith("--"):
                cli_command.add_argument(arg_name, help=arg_info.get("description", ""))
            else:
                cli_command.add_argument(
                    f"--{arg_name}", help=arg_info.get("description", "")
                )
        cli_command.set_defaults(
            func=lambda *args, **kwargs: self.run_command(
                method, command.get("arguments", {}), *args, **kwargs
            )
        )

    def run_command(self, method: Callable, arg_info: dict[str, Any], *args, **kwargs):
        for arg_name, info in arg_info.items():
            if arg_name in kwargs and "arg_type" in info:
                arg_type = info.get("arg_type", None)
                if not arg_type:
                    continue
                try:
                    kwargs[arg_name] = arg_type(kwargs[arg_name])
                except (ValueError, TypeError) as exc:
                    raise ValueError(
                        f"Invalid type for argument '{arg_name}'. Expected {arg_type.__name__}."
                    ) from exc
        return asyncio.run(run_sync_or_async(method, *args, **kwargs))

    @property
    def app(self) -> "PyJolt":
        """Returns the PyJolt app instance."""
        return self._app


def command(command_name: str, help: str = ""):

    def decorator(func):
        @wraps(func)
        async def wrapper(self: "CLIController", *args, **kwargs):
            return await run_sync_or_async(func, self, *args, **kwargs)

        attr = getattr(wrapper, "cli_command", {})
        attr["is_cli_command"] = True
        attr["command_name"] = command_name
        attr["help"] = help
        arguments = attr.get("arguments", {})
        attr["arguments"] = arguments
        setattr(wrapper, "cli_command", attr)
        return wrapper

    return decorator


def argument(name: str, arg_type: Type[int | float | str], description: str = ""):
    """
    Argument decorator defines a command-line argument for a CLI command method.
    To use the argument in the command method, ensure the argument name matches the parameter name. Leading "--" are optional (are automatically added).
    The argument type can be int, float, or str. Input values are automatically converted to the specified type.
    Example:
    ```
        @command("greet", help="Greet a user with a message.")
        @argument("name", arg_type=str, description="The name of the user to greet.")
        async def greet(self, name: str):
            print(f"Hello, {name}!")

        @command("add", help="Adds two numbers")
        @argument("a", arg_type=int, description="First number")
        @argument("b", arg_type=int, description="Second number")
        async def add(self, a: int, b: int):
            print(f"{a} + {b} = {a+b}")
    ```
    Example usage:
        $ uv run app/cli.py greet --name Alice
        Hello, Alice!

        $ uv run app/cli.py add --a 2 --b 5
        2 + 5 = 7

    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self: "CLIController", *args, **kwargs):
            return await run_sync_or_async(func, self, *args, **kwargs)

        attr = getattr(wrapper, "cli_command", {})
        arguments = attr.get("arguments", {})
        arguments[name] = {"description": description, "arg_type": arg_type}
        attr["arguments"] = arguments
        setattr(wrapper, "cli_command", attr)
        return wrapper

    return decorator
