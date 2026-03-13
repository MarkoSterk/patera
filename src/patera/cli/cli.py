"""
Patera cli
"""

import argparse
from typing import Callable
from pathlib import Path

from .start_project import start_dev, start_prod, start_cli, start_testing

methods: dict[str, Callable] = {
    "dev": start_dev,
    "prod": start_prod,
    "cli": start_cli,
    "test": start_testing,
}


def main():
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
        help="Environment file to load",
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
        help="Environment file to load",
    )

    start_cli_parser = subparsers.add_parser("cli")
    start_cli_parser.add_argument(
        "command_name",
        type=str,
        help="CLI command name to run",
    )
    start_cli_parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the CLI command",
    )

    start_testing_parser = subparsers.add_parser("test")
    start_testing_parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to pytest",
    )

    args = parser.parse_args()

    method = methods.get(args.command)
    if method is None:
        parser.print_help()
        return

    args_dict = vars(args)

    return method(Path.cwd(), **args_dict)
