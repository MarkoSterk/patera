"""
Start project in dev or prod mode
"""

import os
import sys
import inspect
from pathlib import Path
import importlib
from typing import Iterator, Optional, Type

from dotenv import load_dotenv

from ..utilities import import_module


def load_env_file(cwd: str, env_file: Optional[str] = None) -> Optional[Path]:
    """
    Load environment variables from a .env file.

    Rules:
    - If env_file is provided, load that file relative to cwd unless absolute.
    - If env_file is not provided, try '.env', '.env.dev', and then '.env.prod'.
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

        print("Loading environment variables from: ", env_path)
        load_dotenv(dotenv_path=env_path, override=False)
        return env_path

    for name in [".env", ".env.dev", ".env.prod"]:
        env_path = root / name
        if env_path.is_file():
            print("Loading environment variables from: ", env_path)
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
    root = root.resolve()
    file_path = file_path.resolve()

    rel = file_path.relative_to(root)

    if rel.name == "__init__.py":
        rel = rel.parent
    else:
        rel = rel.with_suffix("")

    return ".".join(rel.parts)


def _get_ignore_dirs() -> list[str]:
    DEFAULT_IGNORE_DIRS = [
        "__dist__",
        "__pycache__",
        "logs",
        "logging",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        ".git",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "node_modules",
        "site-packages",
    ]

    DECLARED_IGNORE_DIRS = [
        d.strip()
        for d in os.environ.get("PATERA_RELOAD_IGNORE_DIRS", "").split(",")
        if d.strip()
    ]

    return [*DEFAULT_IGNORE_DIRS, *DECLARED_IGNORE_DIRS]


def _get_ignore_patterns() -> list[str]:
    DEFAULT_IGNORE_PATTERNS = [
        r".*\.log$",
        r".*\.sqlite$",
        r".*\.sqlite-journal",
        r".*\.db$",
        r".*\.db-journal",
        r".*\.tmp$",
        r".*\.swp$",
    ]

    DECLARED_IGNORE_PATTERNS = [
        p.strip()
        for p in os.environ.get("PATERA_RELOAD_IGNORE_PATTERNS", "").split(",")
        if p.strip()
    ]

    return [*DEFAULT_IGNORE_PATTERNS, *DECLARED_IGNORE_PATTERNS]


def _is_ignored_path(path: Path, ignore_dirs: set[str]) -> bool:
    """
    Return True if any part of the path belongs to an ignored directory.

    This protects app auto-discovery from walking into directories like:
        .venv/Lib/site-packages
        node_modules
        __pycache__
        .git
    """
    return any(part in ignore_dirs for part in path.parts)


def _iter_files_pruned(root: Path, filename: Optional[str] = None) -> Iterator[Path]:
    """
    Iterate files below root while pruning ignored directories.

    If filename is provided, only files with that exact name are yielded.
    Otherwise, all Python files are yielded.
    """
    root = root.resolve()
    ignore_dirs = set(_get_ignore_dirs())

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        current_path = Path(current_root)

        for file_name in files:
            if filename is not None:
                if file_name != filename:
                    continue
            elif not file_name.endswith(".py"):
                continue

            yield current_path / file_name


def has_python_files(path: Path) -> bool:
    """
    Return True if path directly contains at least one Python file.
    """
    return path.exists() and path.is_dir() and any(path.glob("*.py"))


def has_project_python_files(root: Path) -> bool:
    """
    Return True if the project contains at least one Python file outside ignored dirs.
    """
    return any(_iter_files_pruned(root))


def iter_candidate_files(root: Path) -> Iterator[Path]:
    """
    Yield candidate Python files in priority order.

    Priority:
    1. Common entrypoint names in root/app
    2. Common entrypoint names in root
    3. Common entrypoint names anywhere below root
    4. All remaining Python files

    Important:
    This must not scan .venv, site-packages, node_modules, etc.
    Otherwise the discovery mechanism tries to import installed dependencies
    as if they were app modules.
    """
    root = root.resolve()

    common_names = [
        "__init__.py",
        "app.py",
        "main.py",
        "server.py",
        "run.py",
        "application.py",
    ]

    ignore_dirs = set(_get_ignore_dirs())
    yielded: set[Path] = set()
    app_dir = root / "app"

    def add_file(file_path: Path) -> bool:
        try:
            resolved = file_path.resolve()
        except OSError:
            return False

        if resolved in yielded:
            return False

        if _is_ignored_path(resolved, ignore_dirs):
            return False

        yielded.add(resolved)
        return True

    # root/app/* search
    if app_dir.is_dir() and not _is_ignored_path(app_dir, ignore_dirs):
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
        for file_path in _iter_files_pruned(root, filename=name):
            if add_file(file_path):
                yield file_path

    # Fallback for searching everything else
    for file_path in _iter_files_pruned(root):
        if add_file(file_path):
            yield file_path


def find_pyjolt_app_import(
    pyjolt_class: Type,
    root: Path,
) -> Optional[str]:
    """
    Find the first class that subclasses `pyjolt_class` and return its import string.

    Example return values:
        "app:App"
        "app.main:App"
        "main:App"
    """
    root = root.resolve()

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if not has_project_python_files(root):
        raise RuntimeError(
            f"{root} does not appear to contain Python modules outside ignored directories"
        )

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


def _resolve_root(cwd: str) -> Path:
    """
    Resolve the project root and ensure it is importable.
    """
    root = Path(cwd).resolve()

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    return root


def _resolve_app_path(
    app: Optional[str], root: Path, patera_class: Type
) -> Optional[str]:
    """
    Resolve the Patera app import path.

    Priority:
    1. Explicit app argument
    2. PATERA_IMPORT environment variable
    3. Auto-discovery
    """
    app_path = app

    if app_path is None:
        app_path = os.environ.get("PATERA_IMPORT", None)

    if app_path is None:
        app_path = find_pyjolt_app_import(patera_class, root)

    return app_path


def _print_app_not_found() -> None:
    print(
        "Failed to locate Patera implementation. Please specify a correct import string "
        "(example: 'app:App')"
    )


def _start_prod(
    cwd: str,
    debug: bool,
    app: Optional[str] = None,
    env_file: Optional[str] = None,
):
    """
    Starts application in production mode.
    """
    from granian import Granian
    from granian.constants import Interfaces, Loops
    from granian.log import LogLevels
    from ..patera import Patera

    load_env_file(cwd, env_file)
    os.environ["PATERA_DEBUG"] = "False"

    root = _resolve_root(cwd)
    app_path = _resolve_app_path(app, root, Patera)

    if app_path is None:
        _print_app_not_found()
        return

    address: str = os.environ.get("PATERA_HOST", "0.0.0.0")
    if address == "localhost":
        address = "0.0.0.0"

    port: int = int(os.environ.get("PATERA_PORT", 80))
    loop = Loops(os.environ.get("PATERA_LOOP", "auto"))

    Granian(
        app_path,
        address=address,
        port=port,
        interface=Interfaces.ASGI,
        loop=loop,
        factory=True,
        reload=False,
        log_level=LogLevels.debug if debug else LogLevels.info,
    ).serve()


def _start_dev(
    cwd: str,
    debug: bool,
    app: Optional[str] = None,
    env_file: Optional[str] = None,
):
    import uvicorn
    from ..patera import Patera

    load_env_file(cwd, env_file)
    os.environ["PATERA_DEBUG"] = "True"

    root = _resolve_root(cwd)
    app_path = _resolve_app_path(app, root, Patera)

    if app_path is None:
        _print_app_not_found()
        return

    address: str = os.environ.get("PATERA_HOST", "localhost")
    port: int = int(os.environ.get("PATERA_PORT", 3000))
    loop = str(os.environ.get("PATERA_LOOP", "auto"))

    if loop not in ["auto", "asyncio", "uvloop"]:
        raise ValueError(
            "Loop configuration for development server must be one of: "
            "'asyncio', 'auto', 'uvloop'"
        )

    ignore_dirs = _get_ignore_dirs()
    ignore_patterns = _get_ignore_patterns()

    uvicorn.run(
        app_path,
        host=address,
        port=port,
        loop=loop,
        lifespan="on",
        reload=debug,
        factory=True,
        reload_dirs=[str(root)],
        reload_excludes=[*ignore_dirs, *ignore_patterns],
        log_level="debug",
    )


def start_dev(
    cwd: str,
    command: str,
    app: Optional[str] = None,
    env_file: Optional[str] = None,
):
    try:
        _start_dev(cwd, True, app, env_file)
    except Exception as e:
        print("ERROR: ", str(e))
        print("Failed to start Uvicorn dev server. Install patera[dev] if not already.")


def start_prod(
    cwd: str,
    command: str,
    app: Optional[str] = None,
    env_file: Optional[str] = None,
):
    try:
        _start_prod(cwd, False, app, env_file)
    except Exception as e:
        print("FAILED TO START PATERA APP: ", str(e))


def start_cli(
    cwd: str,
    command: str,
    *args,
    app: Optional[str] = None,
    env_file: Optional[str] = None,
    **kwargs,
):
    from ..patera import Patera

    load_env_file(cwd, env_file)

    root = _resolve_root(cwd)
    app_path = _resolve_app_path(app, root, Patera)

    if app_path is None:
        _print_app_not_found()
        return

    application: Type[Patera] = import_module(app_path)
    app_instance: Patera = application(cli_mode=True)

    command_name = kwargs.pop("command_name", None)
    app_instance.run_cli(command_name, *args, **kwargs)


def start_testing(
    cwd: str,
    command: str,
    *args,
    app: Optional[str] = None,
    **kwargs,
):
    try:
        import pytest  # type: ignore
    except ImportError:
        print(
            "Failed to import Pytest. Please add dependency for running tests. "
            "Run: 'pip install patera[testing]'"
        )
        return

    pytest_args = kwargs.pop("pytest_args", []) or []

    if not pytest_args:
        pytest_args = [cwd]

    return pytest.main(pytest_args)  # type: ignore
