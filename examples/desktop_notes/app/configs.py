import os

from patera import BaseConfig
from patera.database.sql import SqlDatabaseConfig
from patera.desktop import DesktopConfig, user_data_dir

APP_NAME = "Patera Notes"

# The notes live in the user's data folder (%APPDATA%\Patera Notes on Windows),
# not next to the program, whose folder may be read-only and is replaced by
# every update.
DATA_FOLDER = user_data_dir(APP_NAME)


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    APP_NAME: str = APP_NAME
    VERSION: str = "1.0.0"

    # Named after the NotesDb class. An installation can keep its notes
    # elsewhere with a line in its settings.env, for example
    # PATERA_NOTES_DB__DATABASE_URI=sqlite+aiosqlite:///D:/Sync/notes.db
    NOTES_DB: SqlDatabaseConfig = SqlDatabaseConfig(
        DATABASE_URI=f"sqlite+aiosqlite:///{(DATA_FOLDER / 'notes.db').as_posix()}"
    )

    # The window: the page it opens (relative to URL_PREFIX), and a size that
    # fits the two columns. The size and position the user leaves it with are
    # remembered between starts (REMEMBER_GEOMETRY, on by default).
    DESKTOP: DesktopConfig = DesktopConfig(
        INDEX_PAGE="/",
        WIDTH=1100,
        HEIGHT=720,
        MIN_WIDTH=640,
        MIN_HEIGHT=420,
    )
