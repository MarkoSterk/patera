"""
Admin extension
"""

import os
from typing import Optional, Type, TypeVar, Any
from pydantic import BaseModel, Field

from patera import Patera, BaseExtension, MediaType
from patera.controller import path
from patera.auth import role_required

from .translations import TRANSLATIONS_MAP


class AdminConfig(BaseModel):
    """
    Admin configuration model
    """

    ADMIN_BASE_URL: str = Field(
        "/admin", description="Base URL for the admin interface"
    )
    ROLES_REQUIRED: list[str] = Field(
        ["admin"], description="List of roles required to access the admin interface"
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
    URL_FOR_FOR_LOGOUT_REDIRECT: str = Field(
        "_AdminController.login",
        description="URL_FOR string for the application logout redirect",
    )
    LOGO_URL: Optional[str] = Field(
        None, description="URL for the logo to be displayed in the admin interface"
    )


AppT = TypeVar("AppT", bound="Patera[Any]")


class AdminInterface(
    BaseExtension[AppT, AdminConfig],
):
    """
    Main Admin class
    """

    MANAGED_MODELS: list[Type] = []
    TRANSLATIONS_MAP = TRANSLATIONS_MAP

    _admin_menu: list[dict[str, str]] = []
    _models_map: dict[str, Type] = {}
    _supported_languages: list[str] = ["en", "de", "si"]

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

    def _register_admin_controller(self) -> None:
        """
        Registers the admin controller
        """
        from .admin_controller import _AdminController

        base_url = f"{self.configs.ADMIN_BASE_URL}/<string:lang>"

        # Decorators to be applied to the admin controller
        admin_controller_dec = path(base_url, open_api_spec=False)  # path decorator
        admin_roles_required_dec = role_required(
            *self.configs.ROLES_REQUIRED
        )  # auth decorator

        # decorated admin controller
        admin_controller = admin_controller_dec(
            admin_roles_required_dec(_AdminController)
        )
        self._app.register_controller(admin_controller)

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
                "url_for": "AdminController.dashboard",
            }
        ]
        # other menu items based on managed models and injected extensions
        menu.append(
            {
                "name": "logout",
                "url_for": self.configs.URL_FOR_FOR_LOGOUT,
            }
        )
        self._admin_menu = menu

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

    def translate(self, key: str) -> str:
        """
        Translates a given key based on the provided language
        """
        return (
            self.__class__.TRANSLATIONS_MAP[key][self.current_language]
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
        return f"{self._app._app_base_url}{self.configs.ADMIN_BASE_URL}/{self.configs.DEFAULT_LANGUAGE.lower()}/_static/logo.png"

    def url_for(self, target: str, **kwargs) -> str:
        return self.app.url_for(target, **kwargs)
