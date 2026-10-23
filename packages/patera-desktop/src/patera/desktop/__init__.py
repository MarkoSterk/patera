"""
Desktop applications with Patera and pywebview (experimental).
"""

from pkgutil import extend_path

# Optional desktop distributions also work in editable workspace installs.
__path__ = extend_path(__path__, __name__)

from .desktop import (
    Desktop,
    DesktopCLIController,
    DesktopConfig,
    run_in_window,
    settings_file,
    user_data_dir,
)

__all__ = [
    "Desktop",
    "DesktopCLIController",
    "DesktopConfig",
    "run_in_window",
    "settings_file",
    "user_data_dir",
]
