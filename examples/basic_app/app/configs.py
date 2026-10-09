import os
from patera import BaseConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    APP_NAME: str = "Basic App"
    VERSION: str = "1.0.0"

    # Serve the HTML files in app/pages at /pages/<name>
    USE_STATIC_PAGES: bool = True
    STATIC_PAGES_DIR: str = "pages"
    STATIC_PAGES_URL: str = "/pages"
