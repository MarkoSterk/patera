"""
Pyway implementation for Patera
"""

import os
import re
from contextlib import contextmanager
from urllib.parse import unquote, urlparse
from typing import Any, Dict, Generic, Iterator, Optional, TypeVar
from patera import Patera
from patera.cli import CLIController, command, cli_controller
from patera.database.sql import SqlDatabase

from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict

from pyway import settings as pyway_settings
from pyway.configfile import ConfigFile as PywayConfigFile
from pyway.helpers import Utils as PywayUtils
from pyway.info import Info as PywayInfo
from pyway.migrate import Migrate as PywayMigrate
from pyway.validate import Validate as PywayValidate
from pyway.checksum import Checksum as PywayChecksum


class MigrateConfig(BaseModel):
    """Public configuration for the migration CLI and file naming."""

    model_config = ConfigDict(extra="allow")

    MIGRATE_CLI_NAME: str = Field(
        "migrate", description="Name of the cli command prefix"
    )
    MIGRATE_DATABASE_MIGRATION_DIR: str = Field("migrations", description="")
    MIGRATE_SQL_MIGRATION_PREFIX: str = Field(
        "V", description="Start of every migration file name (V1_0__init.sql)"
    )
    MIGRATE_SQL_MIGRATION_SEPARATOR: str = Field(
        "__", min_length=1, description="Text between the version and the description"
    )
    MIGRATE_SQL_MIGRATION_SUFFIXES: str = Field(
        ".sql",
        min_length=1,
        description="File endings of migrations; several are separated by commas",
    )
    MIGRATE_TABLE: str = Field("pyway_migrations", description="")
    MIGRATE_CONFIG_FILE: str = Field(".pyway.conf", description="")


# Compatibility for applications that imported the former private name.
_PateraPywayConfigs = MigrateConfig

AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class MigrationNaming:
    """
    The file names of one database's migrations:
    <PREFIX><version><SEPARATOR><description><SUFFIX>, for example
    V1_0__create_notes.sql. The version has at least two numbers separated
    by "_" or "." (1_0, 2.1, 3_0_1).

    Pyway itself reads every file in the folder and expects V and __, so the
    commands run inside ``applied()``, which makes Pyway use these names.
    """

    def __init__(self, prefix: str, separator: str, suffixes: str) -> None:
        self.prefix = prefix
        self.separator = separator
        self.suffixes = tuple(
            part.strip() for part in suffixes.split(",") if part.strip()
        )
        self._pattern = re.compile(
            rf"^{re.escape(prefix)}(?P<version>\d+(?:[._]\d+)+)"
            rf"{re.escape(separator)}.+$"
        )

    def example(self) -> str:
        return f"{self.prefix}1_0{self.separator}description{self.suffixes[0]}"

    def is_migration_file(self, name: str) -> bool:
        """Files with another ending (README.md, notes.txt) are not migrations."""
        return not name.startswith(".") and name.lower().endswith(
            tuple(suffix.lower() for suffix in self.suffixes)
        )

    def version(self, name: str) -> str:
        """The version of a migration file name, as Pyway stores it (1.0)."""
        match = self._pattern.match(name)
        if match is None:
            raise ValueError(
                f"Migration file {name!r} does not match the configured naming "
                f"(for example {self.example()!r}): MIGRATE_SQL_MIGRATION_PREFIX="
                f"{self.prefix!r}, MIGRATE_SQL_MIGRATION_SEPARATOR={self.separator!r}."
            )
        return match.group("version").replace("_", ".")

    @contextmanager
    def applied(self) -> Iterator[None]:
        """Pyway uses these names while the block runs, then its own again."""
        naming = self
        saved_settings = (
            pyway_settings.SQL_MIGRATION_PREFIX,
            pyway_settings.SQL_MIGRATION_SEPARATOR,
            pyway_settings.SQL_MIGRATION_SUFFIXES,
        )
        saved_files = PywayUtils.__dict__["get_local_files"]
        saved_version = PywayUtils.__dict__["get_version_from_name"]
        original_files = saved_files.__func__

        def get_local_files(directory: str) -> list[str]:
            return [
                name
                for name in original_files(directory)
                if naming.is_migration_file(name)
            ]

        pyway_settings.SQL_MIGRATION_PREFIX = self.prefix
        pyway_settings.SQL_MIGRATION_SEPARATOR = self.separator
        pyway_settings.SQL_MIGRATION_SUFFIXES = self.suffixes[0]
        PywayUtils.get_local_files = staticmethod(get_local_files)  # type: ignore[method-assign]
        PywayUtils.get_version_from_name = staticmethod(self.version)  # type: ignore[method-assign]
        try:
            yield
        finally:
            (
                pyway_settings.SQL_MIGRATION_PREFIX,
                pyway_settings.SQL_MIGRATION_SEPARATOR,
                pyway_settings.SQL_MIGRATION_SUFFIXES,
            ) = saved_settings
            PywayUtils.get_local_files = saved_files  # type: ignore[method-assign]
            PywayUtils.get_version_from_name = saved_version  # type: ignore[method-assign]


class PywayCLIController(CLIController[AppT]):
    def __init__(self, app: AppT, extension: "Migrate[AppT]"):
        super().__init__(app)
        self._ext = extension

    def _get_configs_from_file(self) -> PywayConfigFile:
        """
        Pyway settings: the connection from the database's DATABASE_URI,
        then the migration settings, then anything set in the config file
        (which wins, so a value can be overridden there).
        """
        configs: dict[str, str] = self._ext.pyway_settings()
        os.environ["PYWAY_DATABASE_MIGRATION_DIR"] = str(self._ext._migrations_path)
        os.environ["PYWAY_CONFIG_FILE"] = str(self._ext._configs_path)
        if self._ext._configs_path.exists():
            text = self._ext._configs_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                # Split on the first colon only: values may contain colons.
                config, value = line.split(":", 1)
                configs[config.strip()] = value.strip()
        return PywayConfigFile(**configs)

    def _clear_env_vars(self) -> None:
        os.environ.pop("PYWAY_DATABASE_MIGRATION_DIR", None)
        os.environ.pop("PYWAY_CONFIG_FILE", None)

    def _run(self, command_class: Any, checksum_file: Optional[str] = None) -> None:
        """Runs one Pyway command with this database's settings and file names."""
        pyway_configs = self._get_configs_from_file()
        if checksum_file is not None:
            pyway_configs.checksum_file = checksum_file  # type: ignore[assignment]
        try:
            with self._ext.naming.applied():
                print(command_class(pyway_configs).run())
        finally:
            self._clear_env_vars()

    @command("init", help="Initilizes Patera migration extension for database")
    def init(self) -> None:
        """Initilizes pyway configs"""
        self._ext.create_pyway_config()

    @command("info", help="Provides information about current migrations and db status")
    def info(self) -> None:
        self._run(PywayInfo)

    @command(
        "validate",
        help="Validate helps you verify that the migrations applied to the database match the ones available locally.",
    )
    def validate(self) -> None:
        self._run(PywayValidate)

    @command("migrate", help="Perform database migration")
    def migrate(self) -> None:
        self._run(PywayMigrate)

    @command(
        "checksum",
        help="Updates a checksum in the database. This is for advanced use only, as it could put the pyway database out of sync with reality. ",
    )
    def checksum(self, checksum_file: str) -> None:
        self._run(PywayChecksum, checksum_file)


class Migrate(Generic[AppT]):
    __db_name__: str

    def __init__(self, app: AppT, db: SqlDatabase):
        self._app = app
        self._db = db
        self.__db_name__ = db.db_name
        _configs = db.configs.model_dump()
        self._configs = _PateraPywayConfigs(**_configs)

        # A subclass per database: the command prefix lives on that class,
        # so two migrating databases never overwrite each other's name.
        db_cli_ctrl: type[PywayCLIController[AppT]] = cli_controller(
            name=self._configs.MIGRATE_CLI_NAME
        )(
            type(
                f"{db.__class__.__name__}PywayCLIController",
                (PywayCLIController,),
                {"__module__": PywayCLIController.__module__},
            )
        )
        self._cli_controller = db_cli_ctrl(self._app, self)
        try:
            self._app.register_cli_controller(self._cli_controller)
        except ValueError as exc:
            raise ValueError(
                f"Database {db.db_name!r} uses the migration command prefix "
                f"{self._configs.MIGRATE_CLI_NAME!r}, which is already taken. "
                "Set a different MIGRATE_CLI_NAME in its configuration."
            ) from exc
        self._migrations_path: Path = (
            Path(self._app.root_path) / self._configs.MIGRATE_DATABASE_MIGRATION_DIR
        )
        self._migrations_path.mkdir(parents=True, exist_ok=True)
        self._configs_path: Path = (
            self._migrations_path / self._configs.MIGRATE_CONFIG_FILE
        )
        self.naming = MigrationNaming(
            self._configs.MIGRATE_SQL_MIGRATION_PREFIX,
            self._configs.MIGRATE_SQL_MIGRATION_SEPARATOR,
            self._configs.MIGRATE_SQL_MIGRATION_SUFFIXES,
        )

    def pyway_settings(self) -> Dict[str, str]:
        """
        Pyway settings for this database: the connection, parsed from
        DATABASE_URI at the time of the command, and the migration
        directory and table. Credentials are never written to disk.
        """
        db = self.parse_database_uri(self.database_uri)
        settings = {
            "database_migration_dir": self._configs.MIGRATE_DATABASE_MIGRATION_DIR,
            "database_table": self._configs.MIGRATE_TABLE,
            "database_type": db.get("type"),
            "database_username": db.get("username"),
            "database_password": db.get("password"),
            "database_host": db.get("host"),
            "database_port": db.get("port"),
            "database_name": db.get("database"),
        }
        return {key: value for key, value in settings.items() if value is not None}

    def create_pyway_config(self) -> None:
        """
        Writes the migration settings file into the migration directory
        (<app package>/<MIGRATE_DATABASE_MIGRATION_DIR>/<MIGRATE_CONFIG_FILE>).
        Each developer generates their own copy, so the file belongs in
        .gitignore. It holds no connection details: those come from
        DATABASE_URI (usually an environment variable) each time a command
        runs, and a database_* value added to the file overrides them.
        """
        if self._configs_path.exists():
            return

        lines = [
            "# Pyway settings for Patera. The connection (type, host, user,",
            "# password, database) is read from DATABASE_URI when a command runs;",
            "# a database_* value set here overrides it.",
            f"database_migration_dir: {self._configs.MIGRATE_DATABASE_MIGRATION_DIR}",
            f"database_table: {self._configs.MIGRATE_TABLE}",
        ]
        self._configs_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def parse_database_uri(self, uri: str) -> Dict[str, Optional[str]]:
        parsed = urlparse(uri)
        db_type = parsed.scheme.split("+")[0]

        if db_type == "sqlite":
            # sqlite:///relative.db -> "relative.db"
            # sqlite:////abs/path.db -> "/abs/path.db"
            path = parsed.path[1:] if parsed.path.startswith("/") else parsed.path
            return {
                "type": "sqlite",
                "username": None,
                "password": None,
                "host": None,
                "port": None,
                "database": path,
            }

        # URIs percent-encode reserved characters ("p%40ss" for "p@ss");
        # Pyway needs the real values.
        return {
            "type": db_type,
            "username": unquote(parsed.username) if parsed.username else None,
            "password": unquote(parsed.password) if parsed.password else None,
            "host": parsed.hostname,
            "port": str(parsed.port) if parsed.port else None,
            "database": unquote(parsed.path.lstrip("/")) if parsed.path else None,
        }

    @property
    def database_uri(self) -> str:
        return self._db.db_uri

    @property
    def configs_name(self) -> str:
        return self.__class__.__name__
