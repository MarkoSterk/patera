"""
Desktop applications with Patera and pywebview (experimental).
"""

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
