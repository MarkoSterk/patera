"""
PyJolt cli
"""

import argparse
from typing import Callable
from pathlib import Path

from .new_project import new_project
from .start_project import start_dev, start_prod

methods: dict[str, Callable] = {
    "new-project": new_project,
    "dev": start_dev,
    "prod": start_prod,
}


def main():
    parser = argparse.ArgumentParser(prog="pyjolt")
    subparsers = parser.add_subparsers(dest="command")

    new_project_parser = subparsers.add_parser("new-project")
    new_project_parser.add_argument(
        "--name", type=str, required=True, help="Name of the new project"
    )

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
        help="Import string of App class implementation",
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
        help="Import string of App class implementation",
    )

    args = parser.parse_args()
    method = methods.get(args.command, None)
    if method is not None:
        args = vars(args)
        del args["command"]
        return method(Path.cwd(), **args)
