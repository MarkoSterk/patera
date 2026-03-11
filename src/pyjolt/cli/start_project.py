"""
Start project in dev or prod mode
"""

import os
import sys
import inspect
from pathlib import Path
import importlib
from typing import Optional, Type

from dotenv import load_dotenv


def load_env_file(cwd: str, env_file: Optional[str] = None) -> Optional[Path]:
    """
    Load environment variables from a .env file.

    Rules:
    - If env_file is provided, load that file relative to cwd unless absolute.
    - If env_file is not provided, try '.env' and then '.env.dev'.
    - Only check inside cwd for implicit lookup.
    - Returns the loaded file path, or None if no file was loaded.
    """
    root = Path(cwd).resolve()

    if env_file:
        env_path = Path(env_file)
        if not env_path.is_absolute():
            env_path = root / env_path

        if not env_path.is_file():
            raise RuntimeError(f"Environment file not found: {env_path}")

        load_dotenv(dotenv_path=env_path, override=False)
        return env_path

    for name in [".env", ".env.dev", ".env.prod"]:
        env_path = root / name
        if env_path.is_file():
            load_dotenv(dotenv_path=env_path, override=False)
            return env_path

    return None


def path_to_module(file_path: Path, root: Path) -> str:
    """
    Convert a Python file path to an importable module path.

    Example:
        /project/app.py -> app
        /project/api/server.py -> api.server
        /project/app/__init__.py -> app
        /project/app/main.py -> app.main
    """
    rel = file_path.relative_to(root)

    if rel.name == "__init__.py":
        rel = rel.parent
    else:
        rel = rel.with_suffix("")

    return ".".join(rel.parts)


def has_python_files(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(path.glob("*.py"))


def iter_candidate_files(root: Path):
    """
    Yield candidate Python files in priority order.

    Priority:
    1. Common entrypoint names in root/app
    2. Common entrypoint names in root
    3. Common entrypoint names anywhere below root
    4. All remaining Python files
    """
    common_names = [
        "__init__.py",
        "app.py",
        "main.py",
        "server.py",
        "run.py",
        "application.py",
    ]

    yielded: set[Path] = set()
    app_dir = root / "app"

    def add_file(file_path: Path) -> bool:
        resolved = file_path.resolve()
        if resolved in yielded:
            return False
        if "__pycache__" in file_path.parts:
            return False
        yielded.add(resolved)
        return True

    # root/app/* search
    if app_dir.is_dir():
        for name in common_names:
            file_path = app_dir / name
            if file_path.is_file() and add_file(file_path):
                yield file_path

    # Root-level search
    for name in common_names:
        file_path = root / name
        if file_path.is_file() and add_file(file_path):
            yield file_path

    # Searches common file names anywhere below root
    for name in common_names:
        for file_path in root.rglob(name):
            if add_file(file_path):
                yield file_path

    # Fallback for searching everything else
    for file_path in root.rglob("*.py"):
        if add_file(file_path):
            yield file_path


def find_pyjolt_app_import(
    pyjolt_class: Type,
    root: Optional[Path] = None,
) -> Optional[str]:
    """
    Find the first class that subclasses `pyjolt_class` and return its import string.

    Example return values:
        "app:App"
        "app.main:App"
        "main:App"
    """
    root = (root or Path.cwd()).resolve()
    app_dir = root / "app"

    if not has_python_files(root) and not has_python_files(app_dir):
        raise RuntimeError(
            f"{root} does not appear to contain Python modules in the root or in ./app"
        )

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    importlib.invalidate_caches()

    for file_path in iter_candidate_files(root):
        try:
            module_name = path_to_module(file_path, root)
            if not module_name:
                continue
        except ValueError:
            continue

        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            print(f"Failed to import module '{module_name}': {exc}")
            continue

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue

            try:
                if issubclass(obj, pyjolt_class) and obj is not pyjolt_class:
                    return f"{module_name}:{name}"
            except TypeError:
                continue

    return None


def start(
    cwd: str, debug: bool, app: Optional[str] = None, env_file: Optional[str] = None
):
    """
    Starts application in dev mode.
    """
    from granian import Granian
    from granian.constants import Interfaces, Loops
    from ..pyjolt import PyJolt

    loaded_env = load_env_file(cwd, env_file)
    if loaded_env is not None:
        print(f"Loaded environment from: {loaded_env}")

    app_path = app
    if app_path is None:
        app_path = find_pyjolt_app_import(PyJolt, Path(cwd))

    if app_path is None:
        print(
            "Failed to locate PyJolt implementation. Please specify a correct import string "
            "(example: 'app:App')"
        )
        return
    address: str = os.environ.get("HOST", "127.0.0.1")
    if address == "localhost":
        address = "127.0.0.1"
    _port: int = int(os.environ.get("PORT", 3000))
    _loop = Loops(os.environ.get("PORT", "auto"))

    DEFAULT_IGNORE_DIRS = [
        "__dist__",
        "__pycache__",
        "logs",
        "logging",
        ".mypy_cache",
        ".venv",
        ".git",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "node_modules",
    ]
    DECLARED_IGNORE_DIRS = [
        d for d in os.environ.get("GRANIAN_RELOAD_IGNORE_DIRS", "").split(",") if d
    ]
    DEFAULT_IGNORE_DIRS.extend(DECLARED_IGNORE_DIRS)

    DEFAULT_IGNORE_PATTERNS = ["*.log", "*.sqlite", "*.db", "*.tmp", "*.swp"]
    DECLARED_IGNORE_PATTERNS = [
        p for p in os.environ.get("GRANIAN_RELOAD_IGNORE_PATTERNS", "").split(",") if p
    ]
    DEFAULT_IGNORE_PATTERNS.extend(DECLARED_IGNORE_PATTERNS)

    Granian(
        app_path,
        address=address,
        port=_port,
        interface=Interfaces.ASGI,
        loop=_loop,
        factory=True,
        reload=debug,
        reload_ignore_dirs=DEFAULT_IGNORE_DIRS,
        reload_ignore_patterns=DEFAULT_IGNORE_PATTERNS,
    ).serve()


def start_dev(cwd: str, app: Optional[str] = None, env_file: Optional[str] = None):
    start(cwd, True, app, env_file)


def start_prod(cwd: str, app: Optional[str] = None, env_file: Optional[str] = None):
    start(cwd, False, app, env_file)
