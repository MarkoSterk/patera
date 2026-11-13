"""
Snapshot and restore of an application's registrations.

An extension registers controllers, middleware, handlers and so on while it
is constructed. When construction fails, ``BaseExtension`` restores the
snapshot taken before it started, so a failed extension leaves nothing
behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..patera import Patera

REGISTRATION_COLLECTIONS: tuple[str, ...] = (
    "_extensions",
    "_middleware_classes",
    "_controllers",
    "_cli_controllers",
    "_exception_handlers",
    "_exception_handler_instances",
    "_on_startup_methods",
    "_on_shutdown_methods",
    "_request_observers",
    "_all_templates_paths",
    "_template_prefix_loaders",
    "_url_for_alias",
)

ROUTERS: tuple[str, ...] = ("_router", "_socket_router")


@dataclass(frozen=True)
class RegistrationSnapshot:
    """Copies of the application's registrations at one moment."""

    collections: dict[str, Any]
    routers: dict[str, Any]
    json_spec: Any


def snapshot_registrations(app: "Patera[Any]") -> RegistrationSnapshot:
    """Copies every registration collection, the routers and the OpenAPI spec."""
    return RegistrationSnapshot(
        collections={
            name: value.copy()
            for name in REGISTRATION_COLLECTIONS
            if isinstance(value := getattr(app, name, None), (dict, list))
        },
        routers={name: getattr(app, name).copy() for name in ROUTERS},
        json_spec=app._json_spec,
    )


def restore_registrations(app: "Patera[Any]", snapshot: RegistrationSnapshot) -> None:
    """
    Puts the application's registrations back as they were in ``snapshot``.

    Collections are restored in place, so code holding a reference to one of
    them sees the restored contents.
    """
    for name, saved in snapshot.collections.items():
        current = getattr(app, name)
        current.clear()
        if isinstance(current, dict):
            current.update(saved)
        else:
            current.extend(saved)
    for name, router in snapshot.routers.items():
        setattr(app, name, router)
    app._json_spec = snapshot.json_spec
