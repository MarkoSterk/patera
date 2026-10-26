"""Install the release wheels together in a fresh environment and check imports.

Run after release.py build. No editable imports or source-tree fallbacks are used.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

from release import discover, publish


def main():
    root = Path(__file__).resolve().parent.parent
    packages = discover(root)
    publish(root, packages, dry_run=True)
    wheels = sorted((root / "dist").glob("*.whl"))
    modules = [
        tomllib.loads(package.path.read_text("utf-8"))
        .get("tool", {})
        .get("uv", {})
        .get("build-backend", {})
        .get("module-name", package.name.replace("-", "_"))
        for package in packages
    ]
    # Use a workspace-local temporary directory, also convenient on Windows.
    (root / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="wheel-smoke-", dir=root / "build"
    ) as temporary:
        environment = Path(temporary) / "venv"
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(environment)], check=True
        )
        python = environment / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), *map(str, wheels)],
            check=True,
        )
        code = """
import importlib, importlib.metadata, json, pathlib, sys
for name in json.loads(sys.argv[1]):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).is_relative_to(sys.prefix), module.__file__
from patera.migrate import MigrateConfig
from patera.desktop.ui import DesktopUI
from patera.joltui import PateraJoltui
from importlib.resources import files
assert files('patera.desktop.ui').joinpath('assets/bootstrap.py').is_file()
assert files('patera').joinpath('cli/agent_templates/SKILL.md').is_file()
print('All release wheels import together from the isolated environment')
"""
        subprocess.run(
            [str(python), "-I", "-c", code, json.dumps(modules)],
            cwd=temporary,
            check=True,
        )


if __name__ == "__main__":
    main()
