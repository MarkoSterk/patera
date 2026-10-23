from patera.desktop import Desktop

from patera import Patera, app

from .configs import Config
from .database import Databases


@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Databases, Desktop]
