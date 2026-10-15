"""
Patera cli
"""

import argparse
import sys
from typing import Any, Callable
from pathlib import Path

from .start_project import (
    start_dev,
    start_prod,
    start_cli,
    start_testing,
)

methods: dict[str, Callable] = {
    "dev": start_dev,
    "prod": start_prod,
    "cli": start_cli,
    "test": start_testing,
}


def parse_test_arguments(argv: list[str]) -> dict[str, Any]:
    """
    Arguments of ``patera test``: its own --env-file option, wherever it
    appears, and everything else for pytest unchanged, so pytest options
    may come first (``patera test -k login -q``). Arguments after a bare
    ``--`` all go to pytest.
    """
    env_file = None
    pytest_args: list[str] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--":
            pytest_args.extend(argv[index + 1 :])
            break
        if argument == "--env-file":
            if index + 1 >= len(argv):
                raise SystemExit("patera test: --env-file needs a file name")
            env_file = argv[index + 1]
            index += 2
            continue
        if argument.startswith("--env-file="):
            env_file = argument.split("=", 1)[1]
        else:
            pytest_args.append(argument)
        index += 1
    return {"env_file": env_file, "pytest_args": pytest_args}


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["test"] and not {"-h", "--help"} & set(argv[1:2]):
        return methods["test"](
            Path.cwd(), command="test", **parse_test_arguments(argv[1:])
        )

    parser = argparse.ArgumentParser(prog="patera")
    subparsers = parser.add_subparsers(dest="command")

    start_dev_parser = subparsers.add_parser("dev")
    start_dev_parser.add_argument(
        "--app",
        type=str,
        default=None,
        required=False,
        help="Import string of App class implementation",
    )
    start_dev_parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        required=False,
        help="Path to environment variable file",
    )

    start_prod_parser = subparsers.add_parser("prod")
    start_prod_parser.add_argument(
        "--app",
        type=str,
        default=None,
        required=False,
        help="Import string of App class implementation",
    )
    start_prod_parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        required=False,
        help="Path to environment variable file",
    )

    start_cli_parser = subparsers.add_parser("cli")
    start_cli_parser.add_argument(
        "--app",
        type=str,
        default=None,
        required=False,
        help="Import string of App class implementation",
    )
    start_cli_parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        required=False,
        help="Path to environment variable file",
    )
    start_cli_parser.add_argument(
        "--list",
        action="store_true",
        help="List the application's commands (also the default without a name)",
    )
    start_cli_parser.add_argument(
        "command_name",
        type=str,
        nargs="?",
        default=None,
        help="CLI command to run, as controller:command. Omit to list commands.",
    )
    start_cli_parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the CLI command",
    )

    # Only for the help text: main() reads the test arguments itself, so
    # that pytest options may come first.
    start_testing_parser = subparsers.add_parser(
        "test", help="Run pytest after loading the test environment file"
    )
    start_testing_parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        required=False,
        help="Environment file to load (default: .env.test when it exists)",
    )
    start_testing_parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to pytest, in any order",
    )

    args = parser.parse_args()

    method = methods.get(args.command)
    if method is None:
        parser.print_help()
        return

    args_dict = vars(args)

    return method(Path.cwd(), **args_dict)
