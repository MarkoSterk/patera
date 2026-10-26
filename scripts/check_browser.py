"""Compile the Pyodide bootstrap with the same top-level-await syntax allowance.

Native mypy excludes this browser asset. Other Python UI modules remain covered
by the normal type check. This check does not execute browser APIs.
"""

import ast
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    path = root / "packages/patera-desktop-ui/src/patera/desktop/ui/assets/bootstrap.py"
    compile(
        path.read_text(encoding="utf-8"),
        str(path),
        "exec",
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
    )
    print("Pyodide bootstrap syntax passed")


if __name__ == "__main__":
    main()
