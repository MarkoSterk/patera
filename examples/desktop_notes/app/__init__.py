from patera import Patera, app
from patera.desktop import Desktop

from .configs import Config
from .database import Databases


@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Databases, Desktop]
