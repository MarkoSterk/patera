"""
Admin extension
"""

from enum import StrEnum
import os
from typing import Generic, Optional, Type, TypeVar, Any
from pydantic import BaseModel, Field

from patera import Patera, BaseExtension, MediaType
from patera.controller import path

from .translations import TRANSLATIONS_MAP


class Permissions(StrEnum):
    ADMIN_CAN_ENTER = "admin_can_enter"
    ADMIN_CAN_VIEW = "admin_can_view"
    ADMIN_CAN_EDIT = "admin_can_edit"
    ADMIN_CAN_DELETE = "admin_can_delete"


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
    _databases_menu: list[dict[str, str]] = []
    _models_map: dict[str, Type] = {}
    _supported_languages: list[str] = ["en", "de", "si"]
    _supported_extensions: list[str] = ["sqldatabase"]

    def init(self):
        """
        Initilizer method for extension
        """
        self._admin_root_path: str = os.path.dirname(__file__)
        templates_path = os.path.join(self._admin_root_path, "templates")
        self._app.add_template_path(templates_path)
        self._construct_menu()
        self._create_models_map()
        self._register_admin_exception_handler()
        self._register_admin_controller()
        self._register_models_controller()

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
        pass

    def _register_models_controller(self) -> None:
        if self.managed_models is None or len(self.managed_models) == 0:
            return

    def _construct_menu(self) -> None:
        """
        Constructs the admin menu based on the managed models and injected extensions
        """
        menu = [
            {
                "name": "dashboard",
                "url_for": "_AdminController.dashboard",
            }
        ]
        databases = []
        for ext in self.app.app_extensions:
            extMro = [cl.__name__.lower() for cl in ext.mro()]
            if "admininterface" in extMro or "sqldatabase" not in extMro:
                continue
            if len(set(extMro).intersection(self.__class__._supported_extensions)) > 0:
                extInst = self.app.extensions[ext.__name__]
                databases.append(
                    {
                        "name": extInst.nice_name,  # type: ignore, # type: ignore
                        "url_for": "_AdminDbController.dashboard",
                    }
                )
        if len(databases) > 0:
            self._register_db_controller()

        menu.append(
            {
                "name": "logout",
                "url_for": self.configs.URL_FOR_FOR_LOGOUT,
            }
        )
        self._admin_menu = menu
        self._databases_menu = databases

    def _find_injected_extensions(self) -> dict[str, list[BaseExtension]]:
        """
        Finds injected extensions available for use in the dashboard
        """
        return {}

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

    def translate(self, key: str, lang: Optional[str] = None) -> str:
        """
        Translates a given key based on the provided language
        """
        if lang is None:
            lang = self.current_language
        return (
            self.__class__.TRANSLATIONS_MAP[key][lang]
            if key in self.__class__.TRANSLATIONS_MAP
            else key
        )

    def _create_models_map(self) -> None:
        for model in self.managed_models:
            self._models_map[model.__name__] = model

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

    def url_for(self, target: str, **kwargs) -> str:
        return self.app.url_for(target, **{"lang": self.current_language, **kwargs})
