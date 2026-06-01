from patera import Patera, app

from .configs import Config


@app(__name__, configs=Config)
class App(Patera[Config]):
    pass
