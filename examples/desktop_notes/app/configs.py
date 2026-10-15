import os

from patera import BaseConfig
from patera.database.sql import SqlDatabaseConfig
from patera.desktop import DesktopConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    APP_NAME: str = "Patera Notes"
    VERSION: str = "1.0.0"

    # The values come from the environment: .env during development, the
    # bundled desktop.env (and the installation's settings.env) in the
    # packaged program.
    NOTES_DB: SqlDatabaseConfig  # named after NotesDb; DATABASE_URI is required
    DESKTOP: DesktopConfig  # the window; every field has a default
