from pathlib import Path
from patera import BaseConfig
from patera.admin import AdminConfig
from patera.database.sql import SqlDatabaseConfig
from pydantic import Field
from .store import database_path


class Config(BaseConfig):
    BASE_PATH: str = str(Path(__file__).parent)
    APP_NAME: str = "Quick Exams"
    VERSION: str = "1.0.0"
    EXAMS_DB: SqlDatabaseConfig = Field(
        default_factory=lambda: SqlDatabaseConfig(
            DATABASE_URI="sqlite+aiosqlite:///"
            + Path(database_path()).resolve().as_posix(),
            NICE_NAME="Quick Exams",
        )
    )
    ADMIN: AdminConfig = AdminConfig(
        URL_FOR_FOR_LOGIN="AdminAuth.login",
        URL_FOR_FOR_LOGOUT="AdminAuth.logout",
    )
