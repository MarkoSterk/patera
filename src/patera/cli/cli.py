"""
Patera cli
"""

import argparse
from typing import Callable
from pathlib import Path

from .start_project import (
    start_dev,
    start_prod,
    start_cli,
    start_testing,
    start_desktop,
)

methods: dict[str, Callable] = {
    "dev": start_dev,
    "prod": start_prod,
    "cli": start_cli,
    "test": start_testing,
    "desktop": start_desktop,
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

    start_desktop_parser = subparsers.add_parser("desktop")
    start_desktop_parser.add_argument(
        "--app",
        type=str,
        default=None,
        required=False,
        help="Import string of App class implementation",
    )
    start_desktop_parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        required=False,
        help="Path to environment variable file",
    )
    start_desktop_parser.add_argument(
        "--mode",
        type=str,
        default="dev",
        choices=["dev", "prod"],
        required=False,
        help="To start the desktop app in dev or prod mode",
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
        "--app",
        type=str,
        default=None,
        required=False,
        help="Environment file to use with testing",
    )
    start_testing_parser.add_argument(
        "--env-file",
        type=str,
        default=".env.test",
        required=False,
        help="Environment file to use with testing",
    )
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
