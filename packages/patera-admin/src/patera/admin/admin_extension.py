"""
Admin extension
"""

import os
from typing import TypeVar, Any
from pydantic import BaseModel, Field

from patera import Patera, BaseExtension, MediaType
from patera.controller import path
from patera.auth import roles_required

from .admin_controller import AdminController
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
    LANGUAGE_AWARE: bool = Field(
        False, description="Whether the admin interface should be language aware"
    )
    ADMIN_STATIC_URL: str = Field(
        "/_admin/static/", description="URL for admin static files"
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
        "AdminController.login",
        description="URL_FOR string for the application logout redirect",
    )
    LOGO_URL: str = Field(
        "/", description="URL for the logo to be displayed in the admin interface"
    )


AppT = TypeVar("AppT", bound="Patera[Any]")


class AdminInterface(
    BaseExtension[AppT, AdminConfig],
):
    """
    Main Admin class
    """

    MANAGE_MODELS: list[Any] = []

    _admin_menu: list[dict[str, str]] = []

    def init(self):
        """
        Initilizer method for extension
        """
        self._admin_root_path: str = os.path.dirname(__file__)
        templates_path = os.path.join(self._admin_root_path, "templates")
        self._app.add_template_path(templates_path)
        self._construct_menu()
        self._register_admin_controller()

    def _register_admin_controller(self) -> None:
        """
        Registers the admin controller
        """
        base_url = self.configs.ADMIN_BASE_URL
        if self.configs.LANGUAGE_AWARE:
            base_url = f"{base_url}/<string:lang>"

        # Decorators to be applied to the admin controller
        admin_controller_dec = path(base_url, open_api_spec=False)  # path decorator
        admin_roles_required_dec = roles_required(
            *self.configs.ROLES_REQUIRED
        )  # auth decorator

        # decorated admin controller
        admin_controller = admin_controller_dec(
            admin_roles_required_dec(AdminController)
        )
        self._app.register_controller(admin_controller)

    def _construct_menu(self) -> None:
        """
        Constructs the admin menu based on the managed models and injected extensions
        """
        menu = [
            {
                "name": self.translate("dashboard"),
                "url": self._app.url_for("AdminController.dashboard"),
            }
        ]
        # other menu items based on managed models and injected extensions
        menu.append(
            {
                "name": self.translate("logout"),
                "url": self._app.url_for(self.configs.URL_FOR_FOR_LOGOUT),
            }
        )
        self._admin_menu = menu

    def _find_injected_extension(self) -> dict[str, list[BaseExtension]]:
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
        if not self.configs.LANGUAGE_AWARE:
            return TRANSLATIONS_MAP[key]["en"] if key in TRANSLATIONS_MAP else key
        lang = self._app.current_request.req.route_parameters.get("lang", "en")
        return TRANSLATIONS_MAP[key][lang] if key in TRANSLATIONS_MAP else key

    @property
    def managed_models(self) -> list[Any]:
        """
        Get the models to be managed by the admin interface
        """
        return self.__class__.MANAGE_MODELS
