"""
App configurations
"""

import os
from pyjolt import BaseConfig


class Config(BaseConfig):
    """Config class"""

    APP_NAME: str = "Test app"
    VERSION: str = "1.0"
    SECRET_KEY: str = "46373hdnsfshf73462twvdngnghjdgsfd"
    BASE_PATH: str = os.path.dirname(__file__)

    DATABASE_URI: str = "sqlite+aiosqlite:///./test.db"
    ALEMBIC_DATABASE_URI_SYNC: str = "sqlite:///./test.db"

    CONTROLLERS: list[str] = ["app.api.example_api:ExampleApi"]

    CLI_CONTROLLERS: list[str] = ["app.cli.cli_controller:UtilityCLIController"]

    EXTENSIONS: list[str] = [
        "app.extensions:db",
        "app.extensions:migrate",
        "app.authentication:auth",
    ]

    MODELS: list[str] = ["app.api.models:Example"]

    EXCEPTION_HANDLERS: list[str] = ["app.api.exceptions.exception_handler:Handler"]
