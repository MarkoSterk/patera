"""Discover browser definitions in packages, including zip-imported packages."""

import importlib
import importlib.util
import inspect
import pkgutil
from typing import TypeVar

T = TypeVar("T")


def discover[T](root: str, folders: tuple[str, ...], base: type[T]) -> list[type[T]]:
    result: list[type[T]] = []
    package = importlib.import_module(root)
    if not hasattr(package, "__path__"):
        raise ValueError(f"Discovery root must be a package: {root}")
    for folder in folders:
        name = f"{root}.{folder}"
        # Only missing discovery folders are optional. Import failures inside
        # existing folders must reach the caller with their original traceback.
        if importlib.util.find_spec(name) is None:
            continue
        pending = [name]
        while pending:
            module = importlib.import_module(pending.pop(0))
            for _, cls in inspect.getmembers(module, inspect.isclass):
                if (
                    cls is not base
                    and issubclass(cls, base)
                    and cls.__module__ == module.__name__
                    and not inspect.isabstract(cls)
                    and cls not in result
                ):
                    result.append(cls)
            if hasattr(module, "__path__"):
                pending.extend(
                    sorted(
                        info.name
                        for info in pkgutil.iter_modules(
                            module.__path__, module.__name__ + "."
                        )
                        if not info.name.rsplit(".", 1)[-1].startswith("_")
                    )
                )
    return result
