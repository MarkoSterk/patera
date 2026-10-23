"""
Packaging a Patera application as a desktop program with PyInstaller.

PyInstaller builds from a spec file, a Python file that lists what goes into
the program. ``patera cli desktop:spec [path]`` writes one with sensible
defaults (``desktop.spec`` in the current folder) for you to edit, for
example to add hidden imports or data files. ``patera cli desktop:package
[output] [spec]`` builds with that file, or, when the project has none, with
a generated one in ``build/desktop``. The defaults:

- one folder with the executable: it starts faster than a single file,
  which is unpacked again at every start;
- no console window;
- an entry script that calls ``run_in_window(App)``, written on every build;
- the application package copied next to the executable, because Patera
  finds controllers, exception handlers, middleware and templates by looking
  at its files, and also compiled in. What development and running leave in
  it (``__pycache__``, log files, SQLite databases, tool caches, ``.env``) is
  not copied;
- the data files (templates, static files) of the Patera packages the
  application uses, and every uvicorn module (uvicorn imports some by name).

PyInstaller builds for the operating system it runs on: build the Windows
program on Windows. Needs ``pip install "patera-desktop[pyinstaller]"``.
"""

from __future__ import annotations

import fnmatch
import ast
import importlib
import importlib.util
import json
import os
import pprint
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

#: Build files (generated spec file, entry script, PyInstaller's work folder).
BUILD_FOLDER = Path("build") / "desktop"

#: The project's spec file, which ``desktop:package`` builds with when it exists.
DEFAULT_SPEC_FILE = "desktop.spec"

MISSING_PYINSTALLER = (
    'Packaging needs PyInstaller: pip install "patera-desktop[pyinstaller]" '
    '(or uv add "patera-desktop[pyinstaller]").'
)

#: PyInstaller hooks of this package (see pyinstaller_hooks/).
HOOKS_FOLDER = Path(__file__).parent / "pyinstaller_hooks"

#: Development tools that dependencies import optionally (pydantic's mypy
#: plugin, pytest helpers); a desktop program does not need them.
EXCLUDED_MODULES = ("mypy", "pytest", "_pytest")

#: Files and folders of the application package that are not copied into the
#: program: what running or developing the application leaves there. A name
#: pattern matches a file or folder anywhere in the package; a pattern with
#: "/" matches the path from the package folder (``"static/uploads"``).
PACKAGE_EXCLUDES = (
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
)


def package_excludes(app: Any, package_folder: Path) -> list[str]:
    """PACKAGE_EXCLUDES and the application's own log files, when they are
    in its package (``LOG_FILES.PATH``)."""
    excludes = list(PACKAGE_EXCLUDES)
    log_file = Path(app.log_files.path).resolve()
    if not log_file.is_relative_to(package_folder):
        return excludes
    log_folder = log_file.parent.relative_to(package_folder)
    if log_folder.parts:
        pattern = (
            log_folder.as_posix() if len(log_folder.parts) > 1 else log_folder.name
        )
        names = [pattern]
    else:
        # In the package folder itself: the file and its rotated copies.
        names = [log_file.name, f"{log_file.stem}.*{log_file.suffix}"]
    excludes += [name for name in names if name not in excludes]
    return excludes


def _excluded(relative: Path, excludes: Any) -> bool:
    path = relative.as_posix()
    for pattern in excludes:
        if "/" in pattern:
            if fnmatch.fnmatch(path, pattern.strip("/")):
                return True
        elif fnmatch.fnmatch(relative.name, pattern):
            return True
    return False


def package_files(parent: str, package: str, excludes: Any) -> list[tuple[str, str]]:
    """
    The files of the package ``package`` in the folder ``parent``, without
    the ones ``excludes`` matches (see PACKAGE_EXCLUDES), as PyInstaller
    data entries: (file, folder in the program). Spec files call it.
    """
    root = Path(parent) / package
    files: list[tuple[str, str]] = []
    for folder, folders, names in os.walk(root):
        relative_folder = Path(folder).relative_to(root)
        folders[:] = sorted(
            name for name in folders if not _excluded(relative_folder / name, excludes)
        )
        target = (Path(package) / relative_folder).as_posix()
        for name in sorted(names):
            if not _excluded(relative_folder / name, excludes):
                files.append((str(Path(folder) / name), target))
    return files


def program_name(app: Any) -> str:
    """The executable's name: APP_NAME without characters files cannot have."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(app.app_name)).strip(" .")
    return name or "PateraApp"


def application_package(app: Any) -> tuple[str, Path]:
    """The name and folder of the package that contains the application."""
    package_name = type(app).__module__.split(".")[0]
    package = sys.modules.get(package_name)
    paths = list(getattr(package, "__path__", []) or [])
    if not paths:
        raise RuntimeError(
            f"The application class is in the module {package_name!r}, which is "
            "not a package. Packaging copies the application's package (the "
            "folder with its controllers and templates), so put the class in one, "
            "for example app/__init__.py."
        )
    return package_name, Path(paths[0]).resolve()


def patera_data_packages(app: Any) -> list[str]:
    """
    The Patera packages whose files (templates, static files) the
    application needs: the core and the extensions it uses.
    """
    packages = {"patera"}
    for extension in app.extensions.values():
        for cls in type(extension).__mro__:
            parts = cls.__module__.split(".")
            if parts[0] == "patera" and len(parts) > 1:
                name = f"patera.{parts[1]}"
                spec = importlib.util.find_spec(name)
                if spec is not None and spec.submodule_search_locations:
                    packages.add(name)
    return sorted(packages)


def _application_class(app: Any) -> type:
    app_class = type(app)
    if "." in app_class.__qualname__:
        raise RuntimeError(
            f"{app_class.__qualname__} is not defined at module level; "
            "the entry script cannot import it."
        )
    return app_class


def _relative(target: Path, start: Path) -> str:
    """``target`` relative to ``start`` with "/" separators, or absolute
    when there is no relative path (another drive on Windows)."""
    try:
        return Path(os.path.relpath(target, start)).as_posix()
    except ValueError:
        return target.as_posix()


def desktop_contributions(app: Any, spec_file: Path) -> list[dict]:
    """Optional desktop-only asset builders contributed by extensions."""
    return [
        extension.desktop_packaging(spec_file)
        for extension in app.extensions.values()
        if callable(getattr(extension, "desktop_packaging", None))
    ]


def prepare_desktop_assets(
    contributions: list[dict], base_dir: str
) -> list[tuple[str, str]]:
    """Prepare extension assets when a generated or custom spec is executed.

    Builder references are application-authored Python import paths, just like
    the spec itself. No application instance is constructed by this helper.
    """
    datas = []
    for contribution in contributions:
        module, attribute = contribution["builder"].split(":")
        builder = getattr(importlib.import_module(module), attribute)
        datas.extend(builder(base_dir=base_dir, **contribution["options"]))
    return datas


def validate_desktop_assets(app: Any, spec_file: Path) -> None:
    """Catch stale specs, including ones with an empty contribution list.

    Only the literal DESKTOP_ASSETS setting is inspected; spec code is never
    executed here. Custom specs keep this setting and the preparation call.
    """
    expected = desktop_contributions(app, spec_file)
    if not expected:
        return
    tree = ast.parse(spec_file.read_text(encoding="utf-8"))
    declared: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "DESKTOP_ASSETS"
            for target in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
                if isinstance(value, list):
                    declared = value
            except (ValueError, TypeError):
                pass
    builders = {item.get("builder") for item in declared if isinstance(item, dict)}
    prepared = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "prepare_desktop_assets"
        for node in ast.walk(tree)
    )
    if not prepared or any(item["builder"] not in builders for item in expected):
        raise RuntimeError(
            "This desktop spec is missing extension asset builds. Generate a new spec "
            "with 'desktop:spec' or copy DESKTOP_ASSETS and the prepare_desktop_assets "
            "call from a freshly generated spec before packaging."
        )


_SPEC_TEMPLATE = '''\
# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build file of {name}, made by "patera cli desktop:spec".

"patera cli desktop:package" builds with it; so does "pyinstaller {spec_name}".
Change the settings below for what the program needs beyond the defaults.
Paths are relative to the folder of this file.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

from patera.desktop.packaging import HOOKS_FOLDER, package_files, prepare_desktop_assets

# The program's name: the name of its executable and folder.
NAME = {name}
# The application class the program runs, and the module it is in.
APP_MODULE = {app_module}
APP_CLASS = {app_class}
# The application's package and the folder it is in. The package is copied
# next to the executable: Patera finds controllers, middleware and templates
# by looking at its files.
PACKAGE = {package}
PACKAGE_PARENT = {package_parent}
# Files and folders of the package that are not copied: what running or
# developing the application leaves there. A name pattern matches anywhere in
# the package; a pattern with "/" matches the path from the package folder,
# such as "static/uploads". Remove "*.db" to ship a database with the program.
PACKAGE_EXCLUDES = {package_excludes}

# Modules PyInstaller does not find by itself, such as ones imported by name.
HIDDEN_IMPORTS = []
# Packages included with every module they have (uvicorn imports some by name).
COLLECT_SUBMODULES = [PACKAGE, "uvicorn"]
# Packages whose data files are included: the Patera core and the extensions
# the application uses. Add an extension here when the application starts
# using one, and any other package that needs its data files.
COLLECT_DATA = {collect_data}
# More files and folders for the program: (source, folder in the program).
DATAS = []
# Optional extension builds. Executed by standalone PyInstaller builds too.
DESKTOP_ASSETS = {desktop_assets}
# More binaries, such as DLLs: (source, folder in the program).
BINARIES = []
# Modules left out: development tools that dependencies import optionally.
EXCLUDES = {excludes}
# The program's icon (.ico on Windows, .icns on macOS), or None.
ICON = {icon}
# True shows a console window with the program's output, handy when debugging.
CONSOLE = False
# True makes one executable file instead of a folder. It is unpacked again at
# every start, so it starts slower.
ONE_FILE = False
# Your own entry script instead of the generated one, which only calls
# run_in_window(APP_CLASS); for example to prepare something first.
ENTRY_SCRIPT = None
# The program's settings file (see "patera cli desktop:env"). It is bundled
# with the program when it exists, which loads it at every start.
ENV_FILE = {env_file}


def _path(path):
    return os.path.normpath(os.path.join(SPECPATH, path))


if ENTRY_SCRIPT:
    entry = _path(ENTRY_SCRIPT)
else:
    os.makedirs(workpath, exist_ok=True)
    entry = os.path.join(workpath, "desktop_main.py")
    with open(entry, "w", encoding="utf-8") as file:
        file.write(
            f"from {{APP_MODULE}} import {{APP_CLASS}}\\n"
            "from patera.desktop import run_in_window\\n\\n"
            'if __name__ == "__main__":\\n'
            f"    run_in_window({{APP_CLASS}})\\n"
        )

hiddenimports = list(HIDDEN_IMPORTS)
for package in COLLECT_SUBMODULES:
    hiddenimports += collect_submodules(package)
datas = package_files(_path(PACKAGE_PARENT), PACKAGE, PACKAGE_EXCLUDES)
for package in COLLECT_DATA:
    datas += collect_data_files(package)
datas += [(_path(source), target) for source, target in DATAS]
datas += prepare_desktop_assets(DESKTOP_ASSETS, SPECPATH)
if ENV_FILE and os.path.isfile(_path(ENV_FILE)):
    datas.append((_path(ENV_FILE), "."))
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
    app = BUNDLE(program, name=f"{{NAME}}.app", icon=icon)
'''


def _literal(value: Any) -> str:
    """A string or a list of strings as Python source (JSON strings are
    Python strings too); long lists get one item per line."""
    if value is None:
        return "None"
    one_line = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, list) or len(one_line) <= 60:
        return one_line
    items = "".join(f"    {json.dumps(item, ensure_ascii=False)},\n" for item in value)
    return f"[\n{items}]"


def _spec_icon(app: Any, spec_file: Path) -> Optional[str]:
    """DESKTOP.ICON relative to the spec file's folder, or None."""
    from .desktop import icon_path

    icon = icon_path(app)
    return None if icon is None else _relative(icon, spec_file.resolve().parent)


def spec_text(app: Any, spec_file: Path, root: Optional[Path] = None) -> str:
    """
    A spec file for ``app``, with paths relative to the folder of
    ``spec_file``; ``root`` is the project folder (the current one by default).
    """
    from .envfile import DEFAULT_ENV_FILE

    env_file = (root or Path.cwd()).resolve() / DEFAULT_ENV_FILE
    app_class = _application_class(app)
    package_name, package_folder = application_package(app)
    values = {
        "name": program_name(app),
        "app_module": app_class.__module__,
        "app_class": app_class.__qualname__,
        "package": package_name,
        "package_parent": _relative(package_folder.parent, spec_file.resolve().parent),
        "collect_data": patera_data_packages(app),
        "excludes": list(EXCLUDED_MODULES),
        "package_excludes": package_excludes(app, package_folder),
        "icon": _spec_icon(app, spec_file),
        "env_file": _relative(env_file, spec_file.resolve().parent),
    }
    literals = {key: _literal(value) for key, value in values.items()}
    literals["desktop_assets"] = pprint.pformat(desktop_contributions(app, spec_file))
    return _SPEC_TEMPLATE.format(spec_name=spec_file.name, **literals)


def write_spec(
    app: Any, spec_file: Path, *, overwrite: bool = False, root: Optional[Path] = None
) -> Path:
    """Writes a spec file for ``app`` and returns its path."""
    if spec_file.exists() and not overwrite:
        raise FileExistsError(
            f"{spec_file} already exists. Delete it (or give another path) to "
            "make a new one."
        )
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.write_text(spec_text(app, spec_file, root), encoding="utf-8")
    return spec_file


def pyinstaller_command(spec_file: Path, output: Path, build: Path) -> list[str]:
    """The PyInstaller command line that builds ``spec_file`` into ``output``."""
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_file),
        "--noconfirm",
        "--distpath",
        str(output),
        "--workpath",
        str(build / "work"),
    ]


def check_env_file(app: Any, root: Path) -> None:
    """
    Stops packaging when a required setting has no value for the program,
    and warns about values in desktop.env that look like secrets.
    """
    from .envfile import DEFAULT_ENV_FILE, missing_required, secret_like

    env_file = root / DEFAULT_ENV_FILE
    missing = missing_required(app, env_file)
    if missing:
        where = (
            f"Set them in {DEFAULT_ENV_FILE}"
            if env_file.is_file()
            else f"Write {DEFAULT_ENV_FILE} with 'patera cli desktop:env' and set them there"
        )
        raise RuntimeError(
            "The program would not start: these required settings have no value: "
            f"{', '.join(missing)}. {where}."
        )
    for name in secret_like(env_file):
        print(
            f"Warning: {DEFAULT_ENV_FILE} sets {name}, which looks like a secret. "
            "Anyone with a copy of the program can read it.",
            file=sys.stderr,
        )


def pyinstaller_installed() -> bool:
    return importlib.util.find_spec("PyInstaller") is not None


def package(
    app: Any,
    output: Path,
    spec_file: Path = Path(DEFAULT_SPEC_FILE),
    cwd: Path | None = None,
) -> Path:
    """
    Packages ``app`` into ``output`` with ``spec_file`` (both relative to
    ``cwd``, by default the current folder) and returns ``output``. Without
    the default spec file, a generated one is used.
    """
    if not pyinstaller_installed():
        raise RuntimeError(MISSING_PYINSTALLER)
    root = (cwd or Path.cwd()).resolve()
    output = output if output.is_absolute() else root / output
    build = root / BUILD_FOLDER
    spec = spec_file if spec_file.is_absolute() else root / spec_file
    if not spec.is_file():
        if spec_file != Path(DEFAULT_SPEC_FILE):
            raise FileNotFoundError(f"There is no spec file {spec}.")
        spec = write_spec(app, build / DEFAULT_SPEC_FILE, overwrite=True, root=root)
    check_env_file(app, root)

    validate_desktop_assets(app, spec)

    result = subprocess.run(
        pyinstaller_command(spec, output, build), cwd=root, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"PyInstaller failed with exit code {result.returncode}.")
    return output
