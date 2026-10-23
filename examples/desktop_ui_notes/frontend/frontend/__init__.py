from patera.desktop.ui import Application
from .layouts.main import MainLayout

app = Application(__name__, base_layout=MainLayout, data={"notes": []})
