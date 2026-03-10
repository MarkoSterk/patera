"""CLI utility script"""


# Available cli command for db migrations
# Database models must be imported into the create_app factory function in order
# for the migration module to detect the correctly
# uv run cli.py db-init
# uv run cli.py db-migrate
# uv run cli.py db-upgrade

if __name__ == "__main__":
    ##CLI interface for application
    from app import Application

    app = Application()
    app.run_cli()
