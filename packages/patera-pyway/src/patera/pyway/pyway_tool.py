"""
Pyway implementation for Patera
"""

from typing import Optional, cast
from patera import Patera
from patera.cli import CLIController, command
from patera.base_extension import BaseExtension
from patera.database import SqlDatabase

from pydantic import BaseModel, Field, ConfigDict


class _PateraPywayConfigs(BaseModel):
    model_config = ConfigDict(extra="allow")

    PYWAY_CLI_NAME: Optional[str] = Field(
        "pyway", description="Name of the cli command prefix"
    )
    PYWAY_DATABASE_MIGRATION_DIR: Optional[str] = Field("migrations", description="")
    PYWAY_SQL_MIGRATION_PREFIX: Optional[str] = Field("V", description="")
    PYWAY_SQL_MIGRATION_SEPARATOR: Optional[str] = Field("__", description="")
    PYWAY_SQL_MIGRATION_SUFFIXES: Optional[str] = Field(".sql", description="")
    PYWAY_TABLE: Optional[str] = Field("pyway_migrations", description="")
    PYWAY_CONFIG_FILE: Optional[str] = Field(".pyway.conf", description="")


class PywayCLIController(CLIController):
    @command("migrate", help="Perform database migration")
    def migrate(self) -> None:
        print("Migrating....")


class PateraPyway(BaseExtension):
    def __init__(self, db: SqlDatabase, config_name: Optional[str] = None):
        self._app = cast(Patera, None)
        self._db = db
        self._config_name = config_name if config_name is not None else db.configs_name
        self._database_uri = cast(str, None)

    def init_app(self, app: Patera) -> None:
        self._app = app
        self._configs = self._app.get_conf(self._config_name, {})
        self._configs = self.validate_configs(self._configs, _PateraPywayConfigs)
        self._cli_controller = PywayCLIController(app)
        self._cli_controller.set_ctrl_name(
            cast(str, self._configs.get("PYWAY_CLI_NAME"))
        )
        self._app.register_cli_controller(self._cli_controller)

    @property
    def database_uri(self) -> str:
        return self._db.database_uri
