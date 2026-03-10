import sys

ZIP_PATH = "pyjolt_app.zip"
sys.path.insert(0, ZIP_PATH)
import asyncio

from frontend import app

asyncio.create_task(app.initialize())
