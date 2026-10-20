from pathlib import Path

from patera import BaseConfig
from patera.admin import AdminConfig
from patera.database.sql import SqlDatabaseConfig
from pydantic import Field

APP_DIR = Path(__file__).parent
DEFAULT_DATABASE = (APP_DIR.parent / "exams.sqlite3").resolve().as_posix()


class Config(BaseConfig):
    """
    Quick Exams settings. Every field can be set from the environment or a
    ``.env`` file with the ``PATERA_`` prefix, for example
    ``PATERA_SECRET_KEY`` or ``PATERA_EXAMS_DB__DATABASE_URI``.
    """

    BASE_PATH: str = str(APP_DIR)
    APP_NAME: str = "Quick Exams"
    VERSION: str = "1.0.0"

    SECRET_KEY: str = Field(min_length=32)
    JWT_LIFETIME_SECONDS: int = Field(8 * 60 * 60, gt=0)
    AUTH_COOKIE_NAME: str = "quick_exams_token"

    PUBLIC_URL: str = "http://localhost:3000"

    MAX_CONTENT_LENGTH: int = 4 * 1024 * 1024
    CORS_ENABLED: bool = False

    EXAMS_DB: SqlDatabaseConfig = SqlDatabaseConfig(
        DATABASE_URI=f"sqlite+aiosqlite:///{DEFAULT_DATABASE}",
        NICE_NAME="Quick Exams",
        SQLITE_FOREIGN_KEYS=True,
    )
    ADMIN: AdminConfig = AdminConfig(
        URL_FOR_FOR_LOGIN="AuthApi.login",
        URL_FOR_FOR_LOGOUT="AuthApi.logout",
    )

    @property
    def secure_cookies(self) -> bool:
        return self.PUBLIC_URL.startswith("https://")
