"""Runs inside the bundled Pyodide interpreter."""

import importlib
import json
import sys
import zipfile

from js import document

try:
    sys.path.insert(0, "patera-ui.zip")
    config = json.loads(str(document.getElementById("patera-ui-config").textContent))
    with zipfile.ZipFile("patera-ui.zip") as bundle:
        manifest = json.loads(bundle.read("ui.json"))
    module, attribute = manifest["entrypoint"].split(":")
    application = getattr(importlib.import_module(module), attribute)
    application.templates.update(manifest["templates"])
    await application.start(config=config)  # noqa: F704 - PyScript supports top-level await
except Exception as error:
    document.getElementById("app").textContent = f"Unable to start the UI: {error}"
    raise
