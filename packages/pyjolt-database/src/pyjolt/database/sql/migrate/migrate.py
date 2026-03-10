"""
migrate.py
Alembic integration for database migrations, with argparse subparsers for CLI commands.
"""

import os
import shutil
from typing import Optional, cast, Any
from alembic.config import Config
from alembic import command
from sqlalchemy import MetaData
from pydantic import BaseModel, Field, ConfigDict

from ....pyjolt import PyJolt
from ..sql_database import SqlDatabase
from ....base_extension import BaseExtension
from ....utilities import to_kebab_case


def register_db_commands(app: PyJolt, migrate: "Migrate"):
    """
    Registers subparsers (CLI commands) for database migrations to the app's CLI.
    This replaces the old app.add_cli_command(...) calls with subparser definitions
    so that we can parse arguments like "db-upgrade <revision>" or "db-migrate --message '...'",
    etc.
    """

    # init
    sp_init = app.subparsers.add_parser(
        f"{migrate.command_prefix}-init",
        help="Initialize the Alembic migration environment.",
    )
    sp_init.set_defaults(func=migrate.init)

    # migrate
    sp_migrate = app.subparsers.add_parser(
        f"{migrate.command_prefix}-migrate",
        help="Generate a new revision file (autogenerate).",
    )
    sp_migrate.add_argument("--message", default="", help="Revision message.")
    sp_migrate.set_defaults(
        func=lambda *args, **kwargs: migrate.migrate(message=kwargs["message"])
    )

    # upgrade
    sp_upgrade = app.subparsers.add_parser(
        f"{migrate.command_prefix}-upgrade",
        help="Upgrade the database to a specified (or head) revision.",
    )
    sp_upgrade.add_argument(
        "--revision",
        nargs="?",
        default="head",
        help="Revision identifier (default=head).",
    )
    sp_upgrade.set_defaults(
        func=lambda *args, **kwargs: migrate.upgrade(revision=kwargs["revision"])
    )

    # downgrade
    sp_downgrade = app.subparsers.add_parser(
        f"{migrate.command_prefix}-downgrade",
        help="Downgrade the database to a specified (or one step) revision.",
    )
    sp_downgrade.add_argument(
        "--revision",
        nargs="?",
        default="-1",
        help="Revision identifier (default=-1, i.e. one step down).",
    )
    sp_downgrade.set_defaults(
        func=lambda *args, **kwargs: migrate.downgrade(revision=kwargs["revision"])
    )

    # history
    sp_history = app.subparsers.add_parser(
        f"{migrate.command_prefix}-history", help="Show revision history."
    )
    sp_history.add_argument(
        "--verbose", action="store_true", help="Show more details about each revision."
    )
    sp_history.add_argument(
        "--indicate-current",
        action="store_true",
        help="Mark the current revision in the log.",
    )
    sp_history.set_defaults(
        func=lambda *args, **kwargs: migrate.history(
            verbose=kwargs["verbose"], indicate_current=kwargs["indicate_current"]
        )
    )

    # current
    sp_current = app.subparsers.add_parser(
        f"{migrate.command_prefix}-current",
        help="Show the current revision of the database.",
    )
    sp_current.add_argument(
        "--verbose",
        action="store_true",
        help="Show more details about the current revision.",
    )
    sp_current.set_defaults(
        func=lambda *args, **kwargs: migrate.current(verbose=kwargs["verbose"])
    )

    # heads
    sp_heads = app.subparsers.add_parser(
        f"{migrate.command_prefix}-heads", help="Show all current 'head' revisions."
    )
    sp_heads.add_argument("--verbose", action="store_true", help="Show more details.")
    sp_heads.set_defaults(
        func=lambda *args, **kwargs: migrate.heads(verbose=kwargs["verbose"])
    )

    # show
    sp_show = app.subparsers.add_parser(
        f"{migrate.command_prefix}-show", help="Show details of a given revision."
    )
    sp_show.add_argument(
        "--revision",
        nargs="?",
        default="head",
        help="The revision to show (default=head).",
    )
    sp_show.set_defaults(
        func=lambda *args, **kwargs: migrate.show(revision=kwargs["revision"])
    )

    # stamp
    sp_stamp = app.subparsers.add_parser(
        f"{migrate.command_prefix}-stamp",
        help="Stamp the database with a given revision (no actual migration).",
    )
    sp_stamp.add_argument(
        "--revision",
        nargs="?",
        default="head",
        help="Revision to stamp (default=head).",
    )
    sp_stamp.set_defaults(
        func=lambda *args, **kwargs: migrate.stamp(revision=kwargs["revision"])
    )


class MigrateConfig(BaseModel):
    """Configuration options for Migrate extension"""

    model_config = ConfigDict(extra="allow")

    ALEMBIC_MIGRATION_DIR: str = Field(
        "migrations", description="Connection string for the database"
    )
    ALEMBIC_DATABASE_URI_SYNC: str = Field(
        description="AsyncSession variable name for use with @managed_session decorator and @readonly_session decorator"
    )


class Migrate(BaseExtension):
    """
    Integrates Alembic with the application for managing database migrations.
    Uses the same configs name as the SqlDatabase instance.

    Commands available in the migration CLI tool are:
    <kebab-case-db-name>-init (default: db-init)
    <kebab-case-db-name>-migrate (default: db-migrate)
    <kebab-case-db-name>-upgrade (default: db-upgrade)
    <kebab-case-db-name>-downgrade
    <kebab-case-db-name>-history
    <kebab-case-db-name>-current
    <kebab-case-db-name>-heads
    <kebab-case-db-name>-show
    <kebab-case-db-name>-stamp
    """

    def __init__(self, db: SqlDatabase):
        self._app: "PyJolt"
        self._root_path: str
        self._db: SqlDatabase = db
        self._configs_name: str = db.configs_name
        self._configs: dict[str, Any] = {}
        self._migrations_path: Optional[str] = None
        self._migration_dir: Optional[str] = None
        self._database_uri: Optional[str] = None
        self._command_prefix: str = to_kebab_case(db.db_name)

    def init_app(self, app: PyJolt):
        """
        Initializes Alembic for the given app.
        """
        self._app = app
        self._root_path = self._app.root_path
        self._configs = app.get_conf(self._configs_name, None)
        if self._configs is None:
            raise ValueError(
                f"Configurations for {self._configs_name} for {self.__class__.__name__} not found in app configurations."
            )
        self._configs = self.validate_configs(self._configs, MigrateConfig)
        self._migration_dir = self._configs.get("ALEMBIC_MIGRATION_DIR")
        self._migrations_path = os.path.join(
            self._root_path, cast(str, self._migration_dir)
        )
        # SYNC driver for migrations
        self._database_uri = self._configs.get("ALEMBIC_DATABASE_URI_SYNC")
        # Register all the subparser commands
        register_db_commands(self._app, self)

    def get_alembic_config(self) -> Config:
        """
        Builds an Alembic Config that is OS-portable and does not depend on
        a hardcoded script_location inside alembic.ini.

        - If alembic.ini exists, it is loaded.
        - If it doesn't exist yet (first-time init), we still return a working Config.
        - script_location is forced to self._migrations_path to avoid macOS/Windows path issues.
        """
        migrations_path = cast(str, self._migrations_path)
        ini_path = os.path.join(migrations_path, "alembic.ini")

        # Load ini if present; otherwise create an empty Config (init-safe)
        config = Config(ini_path) if os.path.exists(ini_path) else Config()

        # Force portability: do NOT trust script_location from alembic.ini
        config.set_main_option("script_location", migrations_path)

        # Optional, but often useful: ensure versions/ exists where you expect
        versions_path = os.path.join(migrations_path, "versions")
        config.set_main_option("version_locations", versions_path)

        # DB URL for migrations
        config.set_main_option("sqlalchemy.url", cast(str, self._database_uri))

        # Build target_metadata restricted to this db's models
        associated_models = list(self._db._models.values())
        if not associated_models:
            raise Exception(f"No models associated with db: {self._db.db_name}")

        md = MetaData()
        for model in associated_models:
            model_db_name = getattr(model, "__db_name__", None)
            if model_db_name is not None and model_db_name != self._db.db_name:
                continue
            model.__table__.tometadata(md)

        if not md.tables:
            raise Exception(f"No tables found in metadata for db: {self._db.db_name}")

        config.attributes["target_metadata"] = md
        return config

    def _copy_env_template(self):
        """
        Copies the env.py template to the migrations directory.
        """
        template_path = os.path.join(os.path.dirname(__file__), "env_template.py")
        destination_path = os.path.join(cast(str, self._migrations_path), "env.py")
        shutil.copy(template_path, destination_path)

    def init(self):
        migrations_path = cast(str, self._migrations_path)
        os.makedirs(migrations_path, exist_ok=True)

        ini_path = os.path.join(migrations_path, "alembic.ini")

        # already initialized -> don't call alembic init again
        if os.path.exists(ini_path):
            # optionally ensure env.py template exists / updated
            if not os.path.exists(os.path.join(migrations_path, "env.py")):
                self._copy_env_template()
            return

        # Alembic wants config_file_name to be set
        cfg = Config(ini_path)  # sets cfg.config_file_name = ini_path
        command.init(cfg, migrations_path, template="generic")

        self._copy_env_template()

    def migrate(self, message="Generate migration"):
        """
        Creates a new Alembic revision script (autogenerated) with the given message.
        """
        config = self.get_alembic_config()
        command.revision(config, autogenerate=True, message=message)

    def upgrade(self, revision="head"):
        """
        Upgrades the database to the given revision (default=head).
        """
        config = self.get_alembic_config()
        command.upgrade(config, revision)

    def downgrade(self, revision="-1"):
        """
        Downgrades the database to the given revision (default=-1, i.e. one step).
        """
        config = self.get_alembic_config()
        command.downgrade(config, revision)

    def history(self, verbose=False, indicate_current=False):
        """
        Shows the revision history.
        """
        config = self.get_alembic_config()
        command.history(config, verbose=verbose, indicate_current=indicate_current)

    def current(self, verbose=False):
        """
        Shows the current revision of the database.
        """
        config = self.get_alembic_config()
        command.current(config, verbose=verbose)

    def stamp(self, revision="head"):
        """
        Stamps the database with a given revision, without running migrations.
        """
        config = self.get_alembic_config()
        command.stamp(config, revision)

    def heads(self, verbose=False):
        """
        Displays all current head revisions.
        """
        config = self.get_alembic_config()
        command.heads(config, verbose=verbose)

    def show(self, revision="head"):
        """
        Shows details of a specific revision (default=head).
        """
        config = self.get_alembic_config()
        command.show(config, revision)

    @property
    def command_prefix(self) -> str:
        """
        Returns the command prefix for the CLI
        """
        return self._command_prefix
