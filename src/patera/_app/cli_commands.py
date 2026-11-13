"""
Listing, printing and running the application's CLI commands.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

from typing import (
    Any,
    cast,
)


from ..cli import CLIController
from ..cli.cli_controller import CLICommand

from ._base import AppPart


class CliCommands(AppPart):
    """
    Listing, printing and running the application's CLI commands.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    def cli_commands(self) -> "list[CLICommand]":
        """Lists every registered CLI command, sorted by name."""
        app = self._app
        commands = [
            command
            for ctrl in app._cli_controllers.values()
            for command in ctrl.commands()
        ]
        return sorted(commands, key=lambda command: command.name)

    def print_cli_commands(self, file: Any = None) -> None:
        """Prints the registered CLI commands with their arguments and help."""
        app = self._app
        commands = app.cli_commands()
        if not commands:
            print("No CLI commands are registered.", file=file)
            return
        rows = [(f"{c.name} {c.usage}".strip(), c.help) for c in commands]
        width = max(len(left) for left, _ in rows)
        print("Available commands:", file=file)
        for left, help_text in rows:
            print(f"  {left.ljust(width)}  {help_text}".rstrip(), file=file)

    def run_cli(self, command_name: str, *args, **kwargs) -> None:
        """
        Runs the command ``command_name``, written as
        ``<controller>:<command>``. An invalid name, an unknown controller
        or an unknown command prints an error to standard error and exits
        with status 1.
        """
        app = self._app
        from ..cli.start_project import cli_fail

        if command_name is None or ":" not in command_name:
            cli_fail(
                "Invalid command name. Command name must be of the format "
                "CLIController:Command"
            )

        ctrl_name, command = command_name.split(":", 1)
        ctrl = cast(CLIController, app._cli_controllers.get(ctrl_name, None))

        if ctrl is None:
            cli_fail(f"ERROR: CLI controller with name {ctrl_name} was not found")

        method = ctrl.find_method(command)

        if method is None:
            cli_fail(
                f"CLI method with name {command} in controller {ctrl_name} not found."
            )

        ctrl.run_command(method, *args, **kwargs)
