"""
Admin extension
"""

from datetime import datetime
from enum import StrEnum
import importlib.metadata
import importlib.util
import os
from typing import Generic, Iterator, Optional, Type, TypeVar, Any
from pydantic import BaseModel, Field, field_validator

from patera import Patera, BaseExtension, MediaType
from patera.controller import path
from patera.injectable import Injectable

from .translations import TRANSLATIONS_MAP


class Permissions(StrEnum):
    ADMIN_CAN_ENTER = "admin_can_enter"
    ADMIN_CAN_VIEW = "admin_can_view"
    ADMIN_CAN_EDIT = "admin_can_edit"
    ADMIN_CAN_DELETE = "admin_can_delete"
    ADMIN_CAN_CREATE = "admin_can_create"


def _package_version() -> str:
    try:
        return importlib.metadata.version("patera-admin")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover
        return "unknown"


# Version of the installed patera-admin package, shown in the footer.
ADMIN_INTERFACE_VERSION: str = _package_version()

# Cookie holding the time of the newest notification an admin has seen.
NOTIFICATIONS_SEEN_COOKIE: str = "patera_admin_notifications_seen"


def admin_ignore(cls: Type[Injectable]):
    """
    Mark an injectable type as ignored by the admin interface
    """
    setattr(cls, "_admin_ignore", True)
    return cls


class AdminConfig(BaseModel):
    """
    Admin configuration model
    """

    ADMIN_BASE_URL: str = Field(
        "/admin", description="Base URL for the admin interface"
    )
    DEFAULT_LANGUAGE: str = Field(
        "en",
        description="Default language of the interface (en, de, sl or es)",
    )

    @field_validator("DEFAULT_LANGUAGE", mode="after")
    @classmethod
    def _language_code(cls, value: str) -> str:
        return value.strip().lower()

    URL_FOR_FOR_LOGIN: str = Field(
        description="URL_FOR string for the application login"
    )
    LOGIN_MEDIA_TYPE: str = Field(
        MediaType.APPLICATION_JSON, description="Media type for the login page response"
    )
    URL_FOR_FOR_LOGOUT: str = Field(
        description="URL_FOR string for the application logout"
    )
    LOGO_URL: Optional[str] = Field(
        None, description="URL for the logo to be displayed in the admin interface"
    )
    SHOW_REMEMBER_ME: bool = Field(
        False, description="Show remember me option at login"
    )
    SHOW_FORGOT_PASSWORD: bool = Field(
        False, description="Show forgot password option at login"
    )


AppT = TypeVar("AppT", bound="Patera[Any]")


class AdminInterface(BaseExtension[AppT, AdminConfig], Generic[AppT]):
    """
    Main Admin class

    Extensions are discovered when they are needed, not once at startup:
    menus and panels read the application's current extensions on every
    request, so it does not matter whether a database, email client or task
    manager is created before or after Admin. The panels' routes are
    registered up front, whenever the package they need is installed, and
    show an empty state when nothing is configured.

    Notifications, such as an email from the panel that could not be sent,
    are written to the application's JSON Lines log files and shown in the
    Admin header, so they reach every worker and survive restarts.
    """

    MANAGED_MODELS: list[Type] = []
    TRANSLATIONS_MAP = TRANSLATIONS_MAP

    _supported_languages: list[str] = ["en", "de", "sl", "es"]
    _supported_extensions: list[str] = ["sqldatabase"]

    def init(self):
        """
        Initilizer method for extension
        """
        # Per-instance state (class-level containers would be shared between
        # every AdminInterface instance and every app in the process).
        self._admin_menu: list[dict[str, str]] = []
        self._models_map: dict[str, Type] = {}
        self._translation_maps: dict[str, dict[str, str]] = {}

        self._admin_root_path: str = os.path.dirname(__file__)
        templates_path = os.path.join(self._admin_root_path, "templates")
        self._app.add_template_path(templates_path)
        self._create_models_map()
        self._register_admin_exception_handler()
        self._register_admin_controller()
        self._register_admin_file_explorer()
        self._register_extension_panels()

    def _register_extension_panels(self) -> None:
        """
        Registers the routes of the extension panels whose packages are
        installed. Which extensions the panels show is decided per request.
        """
        self._register_email_controller()
        if _is_installed("patera.taskmanager"):
            self._register_tm_controller()
        if self.managed_models and _is_installed("patera.database"):
            self._register_db_controller()

    def _register_admin_exception_handler(self) -> None:
        """
        Registers the admin exception handler
        """
        from .admin_exception_handler import _AdminExceptionHandler

        self.app.register_exception_handler(_AdminExceptionHandler)
        handler: _AdminExceptionHandler = self.app._exception_handler_instances.get(
            _AdminExceptionHandler.__name__
        )  # type: ignore
        handler.admin_interface = self  # type: ignore

    def _register_admin_controller(self) -> None:
        """
        Registers the admin controller
        """
        from .admin_controller import _AdminController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>"

        # Decorators to be applied to the admin controller
        admin_controller_dec = path(base_url, open_api_spec=False)  # path decorator
        # decorated admin controller
        admin_controller = admin_controller_dec(_AdminController)
        self._app.register_controller(admin_controller)
        ctrl_instance: _AdminController = self._app.get_controller(_AdminController)  # type: ignore
        ctrl_instance.admin_interface = self

    def _register_admin_file_explorer(self) -> None:
        """
        Registers the admin controller
        """
        from .admin_file_controller import _AdminFileController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>/files"

        # Decorators to be applied to the admin controller
        admin_controller_dec = path(base_url, open_api_spec=False)  # path decorator
        # decorated admin controller
        admin_controller = admin_controller_dec(_AdminFileController)
        self._app.register_controller(admin_controller)
        ctrl_instance: _AdminFileController = self._app.get_controller(
            _AdminFileController
        )  # type: ignore
        ctrl_instance.admin_interface = self

    def _register_db_controller(self) -> None:
        from .admin_db_controller import _AdminDbController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>/databases"
        admin_db_controller_dec = path(base_url, open_api_spec=False)
        admin_db_controller = admin_db_controller_dec(_AdminDbController)
        self._app.register_controller(admin_db_controller)
        ctrl_instance: _AdminDbController = self._app.get_controller(_AdminDbController)  # type: ignore
        ctrl_instance.admin_interface = self

    def _register_email_controller(self) -> None:
        from .admin_email_controller import _AdminEmailClientController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>/email-clients"
        admin_email_controller_dec = path(base_url, open_api_spec=False)
        admin_email_controller = admin_email_controller_dec(_AdminEmailClientController)
        self._app.register_controller(admin_email_controller)
        ctrl_instance: _AdminEmailClientController = self._app.get_controller(
            _AdminEmailClientController
        )  # type: ignore
        ctrl_instance.admin_interface = self

    def _register_tm_controller(self) -> None:
        from .admin_tm_controller import _AdminTMController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>/task-managers/<string:manager>"
        admin_email_controller_dec = path(base_url, open_api_spec=False)
        admin_email_controller = admin_email_controller_dec(_AdminTMController)
        self._app.register_controller(admin_email_controller)
        ctrl_instance: _AdminTMController = self._app.get_controller(_AdminTMController)  # type: ignore
        ctrl_instance.admin_interface = self

    def _extensions(self) -> Iterator[tuple[str, Any]]:
        """
        Yields each registered extension once, with its registry name, in
        registration order. Extensions marked with @admin_ignore are skipped.
        """
        seen: set[int] = set()
        for name, ext in list(self.app.extensions.items()):
            if id(ext) in seen or ext is self:
                continue
            seen.add(id(ext))
            if getattr(ext, "_admin_ignore", False):
                continue
            yield getattr(ext, "configs_name", name), ext

    def _extensions_of(self, class_name: str) -> dict[str, Any]:
        """
        Returns the extensions with ``class_name`` in their class hierarchy.
        Names are compared so Admin does not import optional packages.
        """
        return {
            name: ext
            for name, ext in self._extensions()
            if class_name in [cls.__name__ for cls in type(ext).__mro__]
        }

    def _find_database_extensions(self) -> list[dict[str, str | Any]]:
        if not self._models_map:
            return []
        databases = []
        for _, ext in self._extensions():
            ext_mro = [cls.__name__.lower() for cls in type(ext).__mro__]
            if "sqldatabase" not in ext_mro:
                continue
            if not set(ext_mro).intersection(self.__class__._supported_extensions):
                continue
            databases.append(
                {
                    "extension": ext,
                    "db_name": ext.db_name,
                    "name": ext.nice_name,
                    "url_for": "_AdminDbController.database_overview",
                }
            )
        return databases

    # ---- Notifications -------------------------------------------------------

    def notify(
        self, kind: str, message: str, level: str = "ERROR", **data: Any
    ) -> None:
        """
        Records a notification for the Admin header. It is written to the
        application's log files as a log record carrying ``admin_notification``
        (the kind) and ``notification_data``, so every worker sees it.

        Applications can use it for their own events, for example
        ``admin.notify("import_failed", "Nightly import failed", file=name)``.
        """
        self.app.logger.bind(admin_notification=kind, notification_data=data).log(
            level.upper(), message
        )

    async def notifications(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Returns the newest notifications from the log files, newest first.
        Each has ``time``, ``kind``, ``level``, ``message`` and ``data``.
        """
        if not self.app.log_files.enabled:
            return []
        items: list[dict[str, Any]] = []
        for record in await self.app.log_files.read_async():
            extra = record.get("extra") or {}
            kind = extra.get("admin_notification")
            if not kind:
                continue
            items.append(
                {
                    "time": record.get("time"),
                    "kind": kind,
                    "level": record.get("level"),
                    "message": record.get("message"),
                    "data": extra.get("notification_data") or {},
                }
            )
        items.sort(key=lambda item: _timestamp(item["time"]), reverse=True)
        return items[:limit]

    def notifications_seen_at(self, req: Any) -> Optional[datetime]:
        """Time of the newest notification this browser marked as read."""
        return _parse_time(req.cookies.get(NOTIFICATIONS_SEEN_COOKIE))

    @staticmethod
    def count_unread(
        notifications: list[dict[str, Any]], seen_at: Optional[datetime]
    ) -> int:
        """Counts notifications newer than ``seen_at`` (all, if None)."""
        if seen_at is None:
            return len(notifications)
        seen = seen_at.timestamp()
        return sum(1 for item in notifications if _timestamp(item["time"]) > seen)

    def translate(
        self,
        key: str,
        lang: Optional[str] = None,
        values: Optional[list[str | int | float]] = None,
    ) -> str:
        """
        Translates a given key based on the provided language
        """
        if lang is None:
            lang = self.current_language
        translations = self.__class__.TRANSLATIONS_MAP.get(key)
        if translations is None:
            translated_value = key
        else:
            translated_value = (
                translations.get(lang)
                or translations.get(self.configs.DEFAULT_LANGUAGE.lower())
                or translations.get("en")
                or key
            )
        if values is not None and isinstance(values, list):
            for i, val in enumerate(values):
                translated_value = translated_value.replace(f"%{i}", str(val))
        return translated_value

    def _create_models_map(self) -> None:
        for model in self.managed_models:
            self._models_map[model.__name__] = model

    @property
    def admin_menu(self) -> list[dict[str, str]]:
        return self._admin_menu

    @property
    def databases_menu(self) -> list[dict[str, str | Any]]:
        """Databases with managed models, looked up on every access."""
        return self._find_database_extensions()

    @property
    def email_services(self) -> dict[str, Any]:
        """Email clients of the application, looked up on every access."""
        return self._extensions_of("EmailClient")

    @property
    def supported_languages(self) -> list[str]:
        return self.__class__._supported_languages

    @property
    def admin_root_path(self) -> str:
        return self._admin_root_path

    @property
    def has_email_services(self) -> bool:
        return bool(self.email_services)

    @property
    def has_task_managers(self) -> bool:
        return bool(self.task_managers)

    @property
    def task_managers(self) -> dict[str, Any]:
        """Task managers of the application, looked up on every access."""
        return self._extensions_of("TaskManager")

    @property
    def managed_models(self) -> list[Type]:
        """
        Get the models to be managed by the admin interface
        """
        return self.__class__.MANAGED_MODELS

    @property
    def current_language(self) -> str:
        """
        Language from the URL, falling back to DEFAULT_LANGUAGE for languages
        the admin interface does not support.
        """
        lang = (
            self._app.current_request.req.route_parameters.get(
                "lang", self.configs.DEFAULT_LANGUAGE
            )
            or self.configs.DEFAULT_LANGUAGE
        ).lower()
        if lang not in self.supported_languages:
            return self.configs.DEFAULT_LANGUAGE.lower()
        return lang

    @property
    def logo_url(self) -> str:
        if self.configs.LOGO_URL:
            return self.configs.LOGO_URL
        return f"{self._app.url_prefix}{self.configs.ADMIN_BASE_URL}/{self.configs.DEFAULT_LANGUAGE.lower()}/_static/patera_logo.png"

    @property
    def context_variables(self) -> dict[str, Any]:
        return {
            "translate": self.translate,
            "lang": self.current_language,
            "logo_url": self.logo_url,
            "admin_interface": self,
            "admin_url_for": self.url_for,
            "url_for_for_login": self.configs.URL_FOR_FOR_LOGIN,
            "url_for_for_logout": self.configs.URL_FOR_FOR_LOGOUT,
            "show_remember_me": self.configs.SHOW_REMEMBER_ME,
            "show_forgot_password": self.configs.SHOW_FORGOT_PASSWORD,
            "available_langs": self.supported_languages,
            "translation_map": self.get_language_map(),
            "admin_interface_version": ADMIN_INTERFACE_VERSION,
            "application_version": self.app.configs.VERSION,
        }

    def url_for(self, target: str, **kwargs) -> str:
        return self.app.url_for(target, **{"lang": self.current_language, **kwargs})

    def get_language_map(self) -> dict[str, str]:
        language_map: Optional[dict[str, str]] = self._translation_maps.get(
            self.current_language, None
        )
        if language_map is not None:
            return language_map
        language_map = {}
        for key in self.__class__.TRANSLATIONS_MAP:
            language_map[key] = self.translate(key, self.current_language)
        self._translation_maps[self.current_language] = language_map
        return language_map


def _is_installed(module: str) -> bool:
    """True if an optional package can be imported."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _parse_time(value: Any) -> Optional[datetime]:
    """Parses an ISO timestamp as written by the log files."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _timestamp(value: Any) -> float:
    """POSIX timestamp of an ISO time, or 0 when it cannot be parsed."""
    parsed = _parse_time(value)
    return parsed.timestamp() if parsed is not None else 0.0
