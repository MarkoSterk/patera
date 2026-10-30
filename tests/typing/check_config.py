"""Run Pyright against the merged namespace layout used by wheel installs."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="patera-typing-") as temporary:
    target = Path(temporary)
    # Pyright does not resolve the editable namespace-package layout.
    shutil.copytree(root / "src/patera", target / "patera")
    for package in (root / "packages").glob("*/src/patera"):
        shutil.copytree(package, target / "patera", dirs_exist_ok=True)
    for name in ("admin_database_config.py", "pyrightconfig.json"):
        shutil.copyfile(Path(__file__).with_name(name), target / name)
    result = subprocess.run(
        [
            "uvx",
            "--from",
            "pyright",
            "pyright",
            "--project",
            str(target),
            "--pythonpath",
            sys.executable,
        ],
        cwd=root,
        check=False,
    )
    sys.exit(result.returncode)
