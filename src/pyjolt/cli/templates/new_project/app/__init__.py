"""
Test app implementation
"""

from pyjolt import PyJolt, app
from app.configs import Config


@app(__name__, configs=Config)
class Application(PyJolt):
    pass
