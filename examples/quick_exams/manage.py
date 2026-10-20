"""Compatibility wrapper; prefer `patera cli users:create EMAIL ROLE`."""

import argparse
from app import App

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument(
        "role", choices=["instructor", "admin", "both"], default="both", nargs="?"
    )
    args = parser.parse_args()
    App(cli_mode=True).run_cli("users:create", command_args=[args.email, args.role])
