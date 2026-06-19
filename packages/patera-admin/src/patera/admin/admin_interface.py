"""
Admin extension
"""

from enum import StrEnum
import os
from typing import Generic, Optional, Type, TypeVar, Any
from pydantic import BaseModel, Field

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
        description="Default language of the interface",
    )
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
    """

    MANAGED_MODELS: list[Type] = []
    TRANSLATIONS_MAP = TRANSLATIONS_MAP

    _admin_menu: list[dict[str, str]] = []
    _databases_menu: list[dict[str, str | Any]] = []
    _database_menu_built: bool = False
    _email_services: dict[str, Any] = {}
    _models_map: dict[str, Type] = {}
    _supported_languages: list[str] = ["en", "de", "si", "es"]
    _supported_extensions: list[str] = ["sqldatabase"]

    def init(self):
        """
        Initilizer method for extension
        """
        self._admin_root_path: str = os.path.dirname(__file__)
        templates_path = os.path.join(self._admin_root_path, "templates")
        self._app.add_template_path(templates_path)
        self._create_models_map()
        self._register_admin_exception_handler()
        self._register_admin_controller()
        self._find_injected_extensions()

    def _register_admin_exception_handler(self) -> None:
        """
        Registers the admin exception handler
        """
        from .admin_exception_handler import _AdminExceptionHandler

        self.app.register_exception_handler(_AdminExceptionHandler)
        handler: _AdminExceptionHandler = self.app._exception_handler_instances.get(
            _AdminExceptionHandler.__name__
        )  # type: ignore
        handler.admin_interface = self

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
        ctrl_path = getattr(admin_controller, "_controller_path")
        ctrl_instance: _AdminController = self._app._controllers.get(ctrl_path)  # type: ignore
        ctrl_instance.admin_interface = self

    def _register_db_controller(self) -> None:
        from .admin_db_controller import _AdminDbController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>/databases"
        admin_db_controller_dec = path(base_url, open_api_spec=False)
        admin_db_controller = admin_db_controller_dec(_AdminDbController)
        self._app.register_controller(admin_db_controller)
        ctrl_path = getattr(admin_db_controller, "_controller_path")
        ctrl_instance: _AdminDbController = self._app._controllers.get(ctrl_path)  # type: ignore
        ctrl_instance.admin_interface = self

    def _register_email_controller(self) -> None:
        from .admin_email_controller import _AdminEmailClientController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>/email-clients"
        admin_email_controller_dec = path(base_url, open_api_spec=False)
        admin_email_controller = admin_email_controller_dec(_AdminEmailClientController)
        self._app.register_controller(admin_email_controller)
        ctrl_path = getattr(admin_email_controller, "_controller_path")
        ctrl_instance: _AdminEmailClientController = self._app._controllers.get(
            ctrl_path
        )  # type: ignore
        ctrl_instance.admin_interface = self

    def _register_models_controller(self) -> None:
        if self.managed_models is None or len(self.managed_models) == 0:
            return

    def _find_database_extensions(self) -> list[dict[str, str | Any]]:
        databases = []
        doubled = []
        for extInst in list(self.app.extensions.values()):
            extMro = [cl.__name__.lower() for cl in extInst.__class__.mro()]
            if "admininterface" in extMro or "sqldatabase" not in extMro:
                continue
            if getattr(extInst, "_admin_ignore", False):
                continue
            if (
                len(set(extMro).intersection(self.__class__._supported_extensions)) > 0
                and extInst.__class__.__name__ not in doubled
            ):
                databases.append(
                    {
                        "extension": extInst,
                        "db_name": extInst.__db_name__,  # type: ignore
                        "name": extInst.nice_name,  # type: ignore, # type: ignore
                        "url_for": "_AdminDbController.database_overview",
                    }
                )
                doubled.append(extInst.__class__.__name__)
        if len(databases) > 0:
            self._register_db_controller()
        return databases

    def _find_injected_extensions(self) -> None:
        """
        Finds injected extensions available for use in the dashboard
        """
        # print("Injected extensions: ", self.app.extensions)
        for name, ext in self.app.extensions.items():
            if getattr(ext, "_admin_ignore", False):
                continue
            ext_cls_mro = [ext_cls.__name__ for ext_cls in ext.__class__.mro()]
            if "EmailClient" in ext_cls_mro:
                self._email_services[name] = ext
        if len(self._email_services) > 0:
            self._register_email_controller()

    def _collect_models(self) -> dict[str, list[Any]]:
        """
        Collects models and orders them according to databases
        """
        collected_models: dict[str, list[Any]] = {}
        for model in self.managed_models:
            if model.__db_name__ not in collected_models:
                collected_models[model.__db_name__] = []
            collected_models[model.__db_name__].append(model)
        return collected_models

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
        translated_value = (
            self.__class__.TRANSLATIONS_MAP[key][lang]
            if key in self.__class__.TRANSLATIONS_MAP
            else key
        )
        if values is not None and isinstance(values, list):
            for i, val in enumerate(values):
                translated_value = translated_value.replace(f"%{i}", str(val))
        return translated_value

    def _create_models_map(self) -> None:
        for model in self.managed_models:
            self._models_map[model.__name__] = model
        if len(self._models_map) > 0:
            self._databases_menu = self._find_database_extensions()

    @property
    def admin_menu(self) -> list[dict[str, str]]:
        return self._admin_menu

    @property
    def databases_menu(self) -> list[dict[str, str]]:
        return self._databases_menu

    @property
    def supported_languages(self) -> list[str]:
        return self.__class__._supported_languages

    @property
    def admin_root_path(self) -> str:
        return self._admin_root_path

    @property
    def has_email_services(self) -> bool:
        return len(self._email_services.keys()) > 0

    @property
    def managed_models(self) -> list[Type]:
        """
        Get the models to be managed by the admin interface
        """
        return self.__class__.MANAGED_MODELS

    @property
    def current_language(self) -> str:
        return self._app.current_request.req.route_parameters.get(
            "lang", self.configs.DEFAULT_LANGUAGE
        ).lower()

    @property
    def logo_url(self) -> str:
        if self.configs.LOGO_URL:
            return self.configs.LOGO_URL
        return f"{self._app._app_base_url}{self.configs.ADMIN_BASE_URL}/{self.configs.DEFAULT_LANGUAGE.lower()}/_static/patera_logo.png"

    @property
    def context_variables(self) -> dict[str, Any]:
        return {
            "translate": self.translate,
            "lang": self.current_language,
            "logo_url": self.logo_url,
            "admin_interface": self,
            "admin_url_for": self.url_for,
            "url_for_for_login": self.configs.URL_FOR_FOR_LOGIN,
            "url_for_for_logut": self.configs.URL_FOR_FOR_LOGOUT,
            "show_remember_me": self.configs.SHOW_REMEMBER_ME,
            "show_forgot_password": self.configs.SHOW_FORGOT_PASSWORD,
            "available_langs": self.supported_languages,
        }

    def url_for(self, target: str, **kwargs) -> str:
        return self.app.url_for(target, **{"lang": self.current_language, **kwargs})
