"""
Base class of the parts the Patera application object is built from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..patera import Patera


class AppPart:
    """A part of one Patera application. Holds the application it belongs to."""

    __slots__ = ("_app",)

    def __init__(self, app: "Patera[Any]") -> None:
        self._app = app
