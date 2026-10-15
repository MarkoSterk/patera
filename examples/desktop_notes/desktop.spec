# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build file of "Patera Notes", made by "patera cli desktop:spec".

"patera cli desktop:package" builds with it; so does "pyinstaller desktop.spec".
Change the settings below for what the program needs beyond the defaults.
Paths are relative to the folder of this file.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

from patera.desktop.packaging import HOOKS_FOLDER, package_files

# The program's name: the name of its executable and folder.
NAME = "Patera Notes"
# The application class the program runs, and the module it is in.
APP_MODULE = "app"
APP_CLASS = "App"
# The application's package and the folder it is in. The package is copied
# next to the executable: Patera finds controllers, middleware and templates
# by looking at its files.
PACKAGE = "app"
PACKAGE_PARENT = "."
# Files and folders of the package that are not copied: what running or
# developing the application leaves there. A name pattern matches anywhere in
# the package; a pattern with "/" matches the path from the package folder,
# such as "static/uploads". Remove "*.db" to ship a database with the program.
PACKAGE_EXCLUDES = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "logs",
    "*.log",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.db-journal",
    "*.sqlite-journal",
    "*-wal",
    "*-shm",
    ".env",
    ".env.*",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    ".git",
    ".DS_Store",
    "desktop.ini",
]

# Modules PyInstaller does not find by itself, such as ones imported by name.
# SQLAlchemy imports the database driver named in DATABASE_URI
# ("sqlite+aiosqlite:///...") by name, so PyInstaller cannot see it.
HIDDEN_IMPORTS = ["aiosqlite"]
# Packages included with every module they have (uvicorn imports some by name).
COLLECT_SUBMODULES = [PACKAGE, "uvicorn"]
# Packages whose data files are included: the Patera core and the extensions
# the application uses. Add an extension here when the application starts
# using one, and any other package that needs its data files.
COLLECT_DATA = ["patera", "patera.database", "patera.desktop"]
# More files and folders for the program: (source, folder in the program).
DATAS = []
# More binaries, such as DLLs: (source, folder in the program).
BINARIES = []
# Modules left out: development tools that dependencies import optionally.
EXCLUDES = ["mypy", "pytest", "_pytest"]
# The program's icon (.ico on Windows, .icns on macOS), or None.
ICON = None
# True shows a console window with the program's output, handy when debugging.
CONSOLE = False
# True makes one executable file instead of a folder. It is unpacked again at
# every start, so it starts slower.
ONE_FILE = False
# Your own entry script instead of the generated one, which only calls
# run_in_window(APP_CLASS); for example to prepare something first.
ENTRY_SCRIPT = None


def _path(path):
    return os.path.normpath(os.path.join(SPECPATH, path))


if ENTRY_SCRIPT:
    entry = _path(ENTRY_SCRIPT)
else:
    os.makedirs(workpath, exist_ok=True)
    entry = os.path.join(workpath, "desktop_main.py")
    with open(entry, "w", encoding="utf-8") as file:
        file.write(
            f"from {APP_MODULE} import {APP_CLASS}\n"
            "from patera.desktop import run_in_window\n\n"
            'if __name__ == "__main__":\n'
            f"    run_in_window({APP_CLASS})\n"
        )

hiddenimports = list(HIDDEN_IMPORTS)
for package in COLLECT_SUBMODULES:
    hiddenimports += collect_submodules(package)
datas = package_files(_path(PACKAGE_PARENT), PACKAGE, PACKAGE_EXCLUDES)
for package in COLLECT_DATA:
    datas += collect_data_files(package)
datas += [(_path(source), target) for source, target in DATAS]
icon = _path(ICON) if ICON else None

a = Analysis(
    [entry],
    pathex=[_path(PACKAGE_PARENT)],
    binaries=[(_path(source), target) for source, target in BINARIES],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(HOOKS_FOLDER)],
    excludes=EXCLUDES,
)
pyz = PYZ(a.pure)

if ONE_FILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=CONSOLE, icon=icon)
    program = exe
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=CONSOLE, icon=icon)
    program = COLLECT(exe, a.binaries, a.datas, name=NAME)

if sys.platform == "darwin" and not CONSOLE:
    app = BUNDLE(program, name=f"{NAME}.app", icon=icon)
