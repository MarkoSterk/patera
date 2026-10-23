from patera.desktop import Desktop
from patera.desktop.ui import DesktopUI

from patera import Patera, app

from .configs import Config


@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Desktop, DesktopUI]
