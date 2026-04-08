"""
Pyway implementation for Patera
"""

import os
from urllib.parse import urlparse
from typing import Dict, Generic, Optional, TypeVar, cast
from patera import Patera
from patera.cli import CLIController, command
from patera.database.sql import SqlDatabase

from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict

from pyway.configfile import ConfigFile as PywayConfigFile
from pyway.info import Info as PywayInfo
from pyway.migrate import Migrate as PywayMigrate
from pyway.validate import Validate as PywayValidate
from pyway.checksum import Checksum as PywayChecksum


class _PateraPywayConfigs(BaseModel):
    model_config = ConfigDict(extra="allow")

    MIGRATE_CLI_NAME: Optional[str] = Field(
        "migrate", description="Name of the cli command prefix"
    )
    MIGRATE_DATABASE_MIGRATION_DIR: Optional[str] = Field("migrations", description="")
    MIGRATE_SQL_MIGRATION_PREFIX: Optional[str] = Field("V", description="")
    MIGRATE_SQL_MIGRATION_SEPARATOR: Optional[str] = Field("__", description="")
    MIGRATE_SQL_MIGRATION_SUFFIXES: Optional[str] = Field(".sql", description="")
    MIGRATE_TABLE: Optional[str] = Field("pyway_migrations", description="")
    MIGRATE_CONFIG_FILE: Optional[str] = Field(".pyway.conf", description="")


AppT = TypeVar("AppT", bound="Patera")


class PywayCLIController(CLIController[AppT]):
    def __init__(self, app: AppT, extension: "Migrate"):
        super().__init__(app)
        self._ext = extension

    def _get_configs_from_file(self) -> PywayConfigFile:
        configs = {}
        os.environ["PYWAY_DATABASE_MIGRATION_DIR"] = str(self._ext._migrations_path)
        os.environ["PYWAY_CONFIG_FILE"] = str(self._ext._configs_path)
        with open(str(self._ext._configs_path)) as config_file:
            for line in config_file.readlines():
                config, value = line.split(": ")
                configs[config.strip()] = value.strip()
        pyway_configs = PywayConfigFile(**configs)
        return pyway_configs

    def _clear_env_vars(self) -> None:
        os.environ.pop("PYWAY_DATABASE_MIGRATION_DIR", None)
        os.environ.pop("PYWAY_CONFIG_FILE", None)

    @command("init", help="Initilizes Patera migration extension for database")
    def init(self) -> None:
        """Initilizes pyway configs"""
        self._ext.create_pyway_config()

    @command("info", help="Provides information about current migrations and db status")
    def info(self) -> None:
        pyway_configs = self._get_configs_from_file()
        try:
            pyway_info = PywayInfo(pyway_configs)
            print(pyway_info.run())
        finally:
            self._clear_env_vars()

    @command(
        "validate",
        help="Validate helps you verify that the migrations applied to the database match the ones available locally.",
    )
    def validate(self) -> None:
        pyway_configs = self._get_configs_from_file()
        try:
            pyway_validate = PywayValidate(pyway_configs)
            print(pyway_validate.run())
        finally:
            self._clear_env_vars()

    @command("migrate", help="Perform database migration")
    def migrate(self) -> None:
        pyway_configs = self._get_configs_from_file()
        try:
            pyway_migrate = PywayMigrate(pyway_configs)
            print(pyway_migrate.run())
        finally:
            self._clear_env_vars()

    @command(
        "checksum",
        help="Updates a checksum in the database. This is for advanced use only, as it could put the pyway database out of sync with reality. ",
    )
    def checksum(self, checksum_file: str) -> None:
        pyway_configs = self._get_configs_from_file()
        pyway_configs.checksum_file = checksum_file  # type: ignore
        try:
            pyway_checksum = PywayChecksum(pyway_configs)
            print(pyway_checksum.run())
        finally:
            self._clear_env_vars()


class Migrate(Generic[AppT]):
    __db_name__: str

    def __init__(self, app: AppT, db: SqlDatabase):
        self._app = app
        self._db = db
        self.__db_name__ = db.__db_name__
        self._configs = self._app.get_conf(self.configs_name, {})
        self._configs = self._db.validate_configs(self._configs, _PateraPywayConfigs)
        self._cli_controller = PywayCLIController(self._app, self)
        self._cli_controller.set_ctrl_name(
            cast(str, self._configs.get("MIGRATE_CLI_NAME"))
        )
        self._app.register_cli_controller(self._cli_controller)
        self._migrations_path: Path = Path(self._app.root_path) / cast(
            str, self._configs.get("MIGRATE_DATABASE_MIGRATION_DIR")
        )
        self._migrations_path.mkdir(exist_ok=True)
        self._configs_path: Path = self._migrations_path / cast(
            str, self._configs.get("MIGRATE_CONFIG_FILE")
        )
        # configs need to be initilized manually
        # self.create_pyway_config()

    def create_pyway_config(self) -> None:
        if self._configs_path.exists():
            return

        db = self.parse_database_uri(self.database_uri)

        lines = [
            f"database_migration_dir: {self._configs.get('MIGRATE_DATABASE_MIGRATION_DIR')}",
            f"database_table: {self._configs.get('MIGRATE_TABLE')}",
            f"database_type: {db.get('type')}",
            f"database_username: {db.get('username')}",
            f"database_password: {db.get('password')}",
            f"database_host: {db.get('host')}",
            f"database_port: {db.get('port')}",
            f"database_name: {db.get('database')}",
        ]

        filtered = [line for line in lines if not line.endswith(": None")]
        self._configs_path.write_text("\n".join(filtered) + "\n")

    def parse_database_uri(self, uri: str) -> Dict[str, Optional[str]]:
        parsed = urlparse(uri)
        db_type = parsed.scheme.split("+")[0]

        if db_type == "sqlite":
            return {
                "type": "sqlite",
                "username": None,
                "password": None,
                "host": None,
                "port": None,
                "database": parsed.path.lstrip("/"),
            }

        return {
            "type": db_type,
            "username": parsed.username,
            "password": parsed.password,
            "host": parsed.hostname,
            "port": str(parsed.port) if parsed.port else None,
            "database": parsed.path.lstrip("/") if parsed.path else None,
        }

    @property
    def database_uri(self) -> str:
        return self._db.db_uri

    @property
    def configs_name(self) -> str:
        return self.__class__.__name__
