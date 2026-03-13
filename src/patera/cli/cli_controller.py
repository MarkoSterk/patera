"""
CLI controller module for Patera.
"""

import inspect
import asyncio
from typing import TYPE_CHECKING, Any, Callable, cast
from functools import wraps

from ..utilities import run_sync_or_async

if TYPE_CHECKING:
    from ..patera import Patera


class CLIController:
    """
    Base class for CLI controllers.
    This class automatically registers methods decorated with @command and @argument
    as CLI commands in the provided Patera app instance.
    """

    def __init__(self, app: "Patera"):
        self._app: "Patera" = app
        self._cli_commands: dict[str, Callable] = {}
        self._cli_commands_help: dict[str, str] = {}
        self._register_commands()

    def _register_commands(self):
        for attr_name in dir(self):
            method = getattr(self, attr_name)
            if callable(method):
                command = getattr(method, "cli_command", {})
                if command.get("is_cli_command", False):
                    self._register_command(method, command)

    def _register_command(self, method: Callable, command: dict):
        self._cli_commands[method.__name__] = method
        self._cli_commands[cast(str, command.get("command_name"))] = method
        self._cli_commands_help[method.__name__] = command.get("help", "")

    def find_method(self, method: str) -> Callable | None:
        return self._cli_commands.get(method, None)

    def run_command(self, method: Callable, *args, **kwargs):
        try:
            converted_values = self.prepare_cli_args(
                method, kwargs.get("command_args", [])
            )
            return asyncio.run(run_sync_or_async(method, *converted_values))
        except Exception as exc:
            print(f"Failed to run method: {method.__name__}")
            print(
                "Help: ",
                self._cli_commands_help.get(method.__name__, "No help string provided"),
            )
            print(exc)

    def convert_value(self, value: str, annotation: type) -> Any:
        """
        Convert a CLI string value to the annotated type.
        """
        if annotation is inspect.Parameter.empty or annotation is str:
            return value

        if annotation is int:
            return int(value)

        if annotation is float:
            return float(value)

        if annotation is bool:
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y", "on"}:
                return True
            if lowered in {"false", "0", "no", "n", "off"}:
                return False
            raise ValueError(f"Cannot convert '{value}' to bool")

        return annotation(value)

    def prepare_cli_args(self, method, raw_args: list[str]) -> list[Any]:
        """
        Convert raw CLI args to properly typed args based on method annotations.
        """
        sig = inspect.signature(method)
        params = list(sig.parameters.values())
        converted = []
        raw_index = 0

        for param in params:
            if param.name == "self":
                continue

            if raw_index >= len(raw_args):
                if param.default is not inspect.Parameter.empty:
                    converted.append(param.default)
                    continue
                raise ValueError(f"Missing required argument: {param.name}")

            raw_value = raw_args[raw_index]
            converted.append(self.convert_value(raw_value, param.annotation))
            raw_index += 1

        if raw_index < len(raw_args):
            raise ValueError(f"Too many arguments provided: {raw_args[raw_index:]}")

        return converted

    @property
    def app(self) -> "Patera":
        """Returns the Patera app instance."""
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
        setattr(wrapper, "cli_command", attr)
        return wrapper

    return decorator
