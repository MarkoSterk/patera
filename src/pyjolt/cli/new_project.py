"""
New project initilizer
"""

import shutil
import os
from pathlib import Path
from typing import Optional


def new_project(cwd: str, name: Optional[str] = None) -> None:
    if name is None:
        name = input("Project name: ")
    templates_path: Path = Path(
        os.path.join(os.path.dirname(__file__), "templates", "new_project")
    )
    destination_path: Path = Path(os.path.join(cwd, name))
    print(f"Creating new project in {destination_path}")

    destination_path.mkdir(parents=True, exist_ok=True)

    for item in templates_path.iterdir():
        target = destination_path / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
