from patera import Patera, app

from .assistant import Assistant
from .configs import Config
from .database import Databases


@app(__name__, configs=Config)
class App(Patera[Config]):
    # The databases first: the assistant's history and documents live there.
    app_extensions = [Databases, Assistant]
