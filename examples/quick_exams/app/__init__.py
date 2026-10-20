from patera import Patera, app

from .admin import Admin
from .configs import Config
from .database import Databases
from .services.accounts import AccountService
from .services.attempts import AttemptService
from .services.authoring import AuthoringService
from .services.reports import ReportService


@app(__name__, configs=Config)
class App(Patera[Config]):
    # Services are created at startup because Admin model hooks look them up.
    app_extensions = [
        Databases,
        Admin,
        AccountService,
        AuthoringService,
        AttemptService,
        ReportService,
    ]
