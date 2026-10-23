from pathlib import Path

from patera import BaseConfig
from patera.desktop import DesktopConfig
from patera.desktop.ui import DesktopUIConfig


class Config(BaseConfig):
    BASE_PATH: str = str(Path(__file__).parent)
    APP_NAME: str = "Patera Python Notes"
    DESKTOP: DesktopConfig = DesktopConfig(INDEX_PAGE="/app/", WIDTH=1000, HEIGHT=700)
    DESKTOP_UI: DesktopUIConfig = DesktopUIConfig(TITLE="Python Notes")
