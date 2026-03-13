"""
Pyway implementation for Patera
"""

from urllib.parse import urlparse
from typing import Dict, Optional, cast
from patera import Patera
from patera.cli import CLIController, command
from patera.base_extension import BaseExtension
from patera.database.sql import SqlDatabase

from pathlib import Path

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
    def __init__(self, app: Patera, extension: "PateraPyway"):
        super().__init__(app)
        self._ext = extension

    @command("migrate", help="Perform database migration")
    def migrate(self, *args, **kwargs) -> None:
        print("Migrating....", args, kwargs)


class PateraPyway(BaseExtension):
    def __init__(self, db: SqlDatabase, configs_name: Optional[str] = None):
        self._app = cast(Patera, None)
        self._db = db
        self._configs_name = (
            configs_name if configs_name is not None else db.configs_name
        )

    def init_app(self, app: Patera) -> None:
        self._app = app
        self._configs = self._app.get_conf(self._configs_name, {})
        self._configs = self.validate_configs(self._configs, _PateraPywayConfigs)
        self._cli_controller = PywayCLIController(app, self)
        self._cli_controller.set_ctrl_name(
            cast(str, self._configs.get("PYWAY_CLI_NAME"))
        )
        self._app.register_cli_controller(self._cli_controller)
        self._migrations_path: Path = Path(self.app.root_path) / cast(
            str, self._configs.get("PYWAY_DATABASE_MIGRATION_DIR")
        )
        self._migrations_path.mkdir(exist_ok=True)
        self._configs_path: Path = Path(self.app.root_path) / cast(
            str, self._configs.get("PYWAY_CONFIG_FILE")
        )

    def create_pyway_config(self) -> None:
        """
        Create the .pyway.conf file from validated PYWAY_* configuration values.
        """
        if self._configs_path.exists():
            return
        lines: list[str] = []
        for key, value in self._configs.items():
            if key == "PYWAY_CONFIG_FILE":
                continue
            conf_key = key.removeprefix("PYWAY_").lower()
            lines.append(f"{conf_key}: {value}")
        for key, value in self.parse_database_uri(self.database_uri).items():
            lines.append(f"{key}: {value}")
        self._configs_path.write_text("\n".join(lines) + "\n")

    def parse_database_uri(self, uri: str) -> Dict[str, Optional[str]]:
        """
        Parse a SQLAlchemy-style database URI and extract database parameters.

        Args:
            uri: Database URI

        Returns:
            Dict containing:
                type
                username
                password
                host
                port
                database
        """
        parsed = urlparse(uri)

        db_type = parsed.scheme.split("+")[0]  # remove driver if present

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
        return self._db.database_uri
