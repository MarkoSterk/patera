import os
from patera import BaseConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    APP_NAME: str = "Basic App"
    APP_VERSION: str = "1.0.0"
