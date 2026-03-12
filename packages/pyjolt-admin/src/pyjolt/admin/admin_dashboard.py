"""Admin dashboard extension"""

from __future__ import annotations
from datetime import datetime
import os
from typing import TYPE_CHECKING, Optional, Type, Any, cast, TypedDict, NotRequired
from pydantic import BaseModel, Field
from wtforms_sqlalchemy.orm import model_form
from pyjolt.exceptions.runtime_exceptions import CustomException
from .utilities import FormType
from pyjolt.base_extension import BaseExtension
from .admin_controller import AdminController
from .database_controller import AdminDatabaseController
from .email_clients_controller import AdminEmailClientsController
from .task_managers_controller import AdminTaskManagersController
from .file_controller import AdminFileController
from pyjolt.database.sql.declarative_base import DeclarativeBaseModel
from pyjolt.database.sql import SqlDatabase, AsyncSession
from pyjolt.controller import path
from pyjolt import Request
from pyjolt.email import EmailClient
from pyjolt.taskmanager import TaskManager
from pyjolt.utilities import to_kebab_case
from pyjolt.caching import Cache

if TYPE_CHECKING:
    from pyjolt import PyJolt


class _AdminDashboardConfig(BaseModel):
    """Admin dashboard configuration model."""

    model_config = {"strict": True}

    DASHBOARD_URL: Optional[str] = Field(
        "/admin/dashboard", description="URL path for accessing the admin dashboard."
    )
    LOGO_URL: Optional[str] = Field(
        None,
        description="URL for the logo of the admin dashboard displayed on the login page and dashboard menu.",
    )
    URL_FOR_FOR_LOGIN: str = Field(
        description="The url_for string for your login endpoint"
    )
    URL_FOR_FOR_LOGOUT: str = Field(
        description="The url_for string for your logout endpoint"
    )
    URL_FOR_FOR_PASSWORD_RESET: Optional[str] = Field(
        None, description="The url_for string for your password reset endpoint."
    )
    USE_REMEMBER_ME: Optional[bool] = Field(
        False,
        description="If a 'Remember me' field should be provided in the lgin form for permanent/long-running cookies/sessions",
    )


class AdminConfig(TypedDict):
    """Admin configurations typed dictionary"""

    DASHBOARD_URL: NotRequired[str]
    LOGO_URL: NotRequired[str]
    URL_FOR_FOR_LOGIN: str
    URL_FOR_FOR_LOGOUT: str
    URL_FOR_FOR_PASSWORD_RESET: NotRequired[str]
    USE_REMEMBER_ME: NotRequired[bool]


class AdminMissingDatabaseExtension(CustomException):
    def __init__(self, db_name: str):
        self.message = f"Failed to load database extension with {db_name=}"


class AdminDashboard(BaseExtension):
    """Admin dashboard extension class."""

    def __init__(self) -> None:
        self._databases_models: dict[str, list[Type[DeclarativeBaseModel]]] = {}
        self._configs: dict[str, Any] = {}
        self._configs_name: str = "ADMIN_DASHBOARD"
        self._root_path = os.path.dirname(__file__)
        self._databases: dict[str, SqlDatabase] = {}
        self._email_clients: Optional[dict[str, EmailClient]]
        self._task_managers: Optional[dict[str, TaskManager]]

    def init_app(self, app: "PyJolt") -> None:
        self._app = app
        self._configs = app.get_conf(self._configs_name, {})
        self._configs = self.validate_configs(self._configs, _AdminDashboardConfig)
        # pylint: disable-next=W0212
        self._databases_models = self.get_registered_models()
        self._databases = self._get_all_databases()
        self._email_clients = self.get_email_clients()
        self._task_managers = self.get_task_managers()
        self._app.add_template_path(self._root_path)

        for ctrl in [
            AdminController,
            AdminDatabaseController,
            AdminEmailClientsController,
            AdminTaskManagersController,
            AdminFileController,
        ]:
            ctrl = path(url_path=self._configs["DASHBOARD_URL"], open_api_spec=False)(
                ctrl
            )
            setattr(ctrl, "_dashboard", self)
            self._app.register_controller(ctrl)

    def get_model(
        self, db_name: str, model_name: str
    ) -> Type[DeclarativeBaseModel] | None:
        """Get a model class by database name and model name."""
        models = self._databases_models.get(db_name, [])
        for model in models:
            if model.__name__ == model_name:
                return model
        return None

    def get_model_form(
        self,
        model: Type[DeclarativeBaseModel],
        form_type: str = FormType.UPDATE,
        exclude_pk: bool = False,
        exclude_fk: bool = True,
        only: Any | None = None,
        exclude: Any | None = None,
        field_args: Any | None = None,
        converter: Any | None = None,
        type_name: Any | None = None,
    ) -> dict[str, Any]:  # Type:
        """
        Get a WTForms-SQLAlchemy form for a given model.

        Args:
            only (Iterable[str], optional):
                Property names that should be included in the form.
                Only these properties will have fields.

            exclude (Iterable[str], optional):
                Property names that should be excluded from the form.
                All other properties will have fields.

            field_args (dict[str, dict], optional):
                A mapping of field names to keyword arguments used to construct
                each field object.

            converter (Type[ModelConverter], optional):
                A converter class used to generate fields based on the model
                properties. If not provided, ``ModelConverter`` is used.

            exclude_pk (bool, optional):
                Whether to force exclusion of primary key fields. Defaults to ``False``.

            exclude_fk (bool, optional):
                Whether to force exclusion of foreign key fields. Defaults to ``False``.

            type_name (str, optional):
                Custom name for the generated form class.

        Returns:
            Type[Form]: A dynamically generated WTForms form class.
        """
        if hasattr(model, f"__{form_type}_form__"):
            return getattr(model, f"__{form_type}_form__")
        form_class = model_form(
            model,
            exclude_pk=exclude_pk,
            only=only,
            exclude=exclude,
            field_args=field_args,
            converter=converter,
            exclude_fk=exclude_fk,
            type_name=type_name,
        )
        setattr(model, f"__{form_type}_form__", form_class)
        return form_class

    def get_database(self, db_name: str) -> "SqlDatabase":
        for _, ext in self._databases.items():
            if ext.db_name == db_name:
                return ext
        raise AdminMissingDatabaseExtension(db_name)

    def _get_all_databases(self) -> dict[str, SqlDatabase]:
        """Gets all database extensions from app extensions"""
        databases: dict[str, SqlDatabase] = {}
        for _, ext in self.app.extensions.items():
            if (
                isinstance(ext, SqlDatabase)
                and self._databases_models.get(ext.configs_name, None) is not None
            ):
                databases[ext.db_name] = ext
        return databases

    def get_registered_models(self) -> dict[str, list[Type[DeclarativeBaseModel]]]:
        """Gets all registered models for admin dashboard"""
        # get_registered_models()#self._app._db_models
        databases_and_models: dict[str, list[Type[DeclarativeBaseModel]]] = {}
        # pylint: disable-next=W0212
        for db_name, models in cast("PyJolt", self._app)._db_models.items():
            registered_models: list[Type[DeclarativeBaseModel]] = []
            for m in models:
                if (
                    hasattr(m, "__use_in_dashboard__")
                    and getattr(m, "__use_in_dashboard__", False) is True
                ):
                    registered_models.append(m)
            if len(registered_models) > 0:
                # pylint: disable-next=W0212
                databases_and_models[self.app._db_name_configs_map[db_name]] = (
                    registered_models
                )
        return databases_and_models

    def get_session(self, database: "SqlDatabase") -> "AsyncSession":
        return database.create_session()

    async def number_of_tables(self) -> int:
        """Number of all tables in all databases"""
        num: int = 0
        for _, db in self._databases.items():
            num = num + await db.count_tables()
        return num

    async def number_of_rows(self) -> int:
        """Number of all rows in all databases"""
        num: int = 0
        for _, db in self._databases.items():
            _, rows = await db.count_rows_exact()
            num = num + rows
        return num

    async def databases_overviews(self, with_extras=False) -> dict[str, Any]:
        """Collects database overviews for dashboard"""
        overviews: dict[str, Any] = {
            "db_count": 0,
            "schemas_count": 0,
            "tables_count": 0,
            "views_count": 0,
            "columns_count": 0,
            "rows_count": 0,
        }
        overviews["db_count"] = self.number_of_dbs
        for _, db in self._databases.items():
            overview = await db.collect_db_overview(with_extras=with_extras)
            _, rows_count = await db.count_rows_exact()
            overview["rows_count"] = rows_count
            overviews["schemas_count"] += overview["schemas_count"]
            overviews["tables_count"] += overview["tables_count"]
            overviews["views_count"] += overview["views_count"]
            overviews["columns_count"] += overview["columns_count"]
            overviews["rows_count"] += overview["rows_count"]
        return overviews

    async def database_overview(
        self, db_name: str, with_extras: bool = False
    ) -> dict[str, Any]:
        """Returns overview for selected db"""
        db: SqlDatabase = cast(SqlDatabase, self._databases.get(db_name))
        if db is None:
            # pylint: disable-next=W0719
            raise Exception(f"Unknown database: {db_name}")
        overview: dict[str, Any] = await db.collect_db_overview(with_extras=with_extras)
        _, rows_count = await db.count_rows_exact()
        overview["rows_count"] = rows_count
        return overview

    def get_email_clients(self) -> Optional[dict[str, EmailClient]]:
        """Finds all registered email client extensions"""
        clients: dict[str, EmailClient] = {}
        for _, ext in self.app.extensions.items():
            if isinstance(ext, EmailClient):
                clients[to_kebab_case(ext.configs_name)] = ext
        if len(clients.keys()) == 0:
            return None
        return clients

    def get_task_managers(self) -> Optional[dict[str, TaskManager]]:
        """Finds all registered task managers"""
        task_managers: dict[str, TaskManager] = {}
        for _, ext in self.app.extensions.items():
            if isinstance(ext, TaskManager):
                task_managers[ext.configs_name] = ext
        if len(task_managers.keys()) == 0:
            return None
        return task_managers

    def get_cache_interfaces(self) -> Optional[dict[str, Cache]]:
        """Cache extensions"""
        caches: dict[str, Cache] = {}
        for _, ext in self.app.extensions.items():
            if isinstance(ext, Cache):
                caches[ext.configs_name] = ext
        if len(caches.keys()) == 0:
            return None
        return caches

    async def email_recipient_query(
        self, req: Request, query: str, client: EmailClient
    ) -> list[tuple[str, str]]:
        """
        Email recipients query method. Should return a list of tuples
        containing name-value pairs. Example: [("John Doe", "john.doe@email.com)]
        If you wish you can also simply return an empty list

        Example:
        return [
            ("John Doe", "john.doe@email.com"),
            ("Jane Doe", "jane.doe@email.com"),
            ("John Smith", "john.smith@email.com"),
            ("Alexander The Great", "alexander.great@email.com"),
            ("Julius Cesar", "julius.cesar@email.com"),
            ("Marcus Antonius", "marcus.antonius@email.com")
        ]
        """
        raise NotImplementedError(
            "Please override the 'email_recipient_query' "
            "method in your AdminDashboard implementation "
            "for this functionality to work."
        )

    @property
    def root_path(self) -> str:
        return self._root_path

    @property
    def email_clients(self) -> Optional[dict[str, EmailClient]]:
        """Dictionary of email clients"""
        return self._email_clients

    @property
    def task_managers(self) -> Optional[dict[str, TaskManager]]:
        """Dictionary of task managers"""
        return self._task_managers

    @property
    def number_of_dbs(self) -> int:
        """Number of databases"""
        return len(self._databases)

    @property
    def all_dbs(self) -> list[SqlDatabase]:
        """List of all databases"""
        return [db for db in self._databases.values()]

    async def has_enter_permission(self, req: Request) -> bool:
        """If a user can enter the dashboard"""
        raise NotImplementedError(
            "Please implement 'has_enter_permission' method "
            "before using the admin dashboard"
        )

    async def has_view_permission(
        self, req: Request, model: Type[DeclarativeBaseModel]
    ) -> bool:
        """If the logged in user has permission to view model data"""
        raise NotImplementedError(
            "Please implement 'has_view_permission' method "
            "for viewing database data/models before "
            "using the admin dashboard."
        )

    async def has_update_permission(
        self, req: Request, model: Type[DeclarativeBaseModel]
    ) -> bool:
        """If the logged in user has permission to edit model data"""
        raise NotImplementedError(
            "Please implement 'has_update_permission' method "
            "for updating database data/models before "
            "using the admin dashboard."
        )

    async def has_create_permission(
        self, req: Request, model: Type[DeclarativeBaseModel]
    ) -> bool:
        """If the logged in user has permission to create model data"""
        raise NotImplementedError(
            "Please implement 'has_create_permission' method "
            "for creating database model records before "
            "using the admin dashboard."
        )

    async def has_delete_permission(
        self, req: Request, model: Type[DeclarativeBaseModel]
    ) -> bool:
        """If the logged in user has permission to delete model data"""
        raise NotImplementedError(
            "Please implement 'has_delete_permission' method "
            "for deleting database before "
            "using the admin dashboard."
        )

    async def has_email_permission(self, req: Request, client: EmailClient) -> bool:
        """If the logged in user has permission to use email clients"""
        raise NotImplementedError(
            "Please implement the 'has_email_permission' "
            "method before using the email client extension "
            "in the admin dashboard."
        )

    async def has_task_manager_permission(
        self, req: Request, manager: TaskManager
    ) -> bool:
        """If the logged in user has permission to use task managers"""
        raise NotImplementedError(
            "Please implement the 'has_task_manager_permission'"
            " method before using the task manager client extensions"
            " in the admin dashboard"
        )

    async def has_cache_permission(self, req: Request, cache: Cache) -> bool:
        """If the logged in user has permission to reset the cache"""
        raise NotImplementedError(
            "Please implement the 'has_cache_permission'"
            " method before using the cache interface extensions"
            " in the admin dashboard"
        )

    async def has_files_permission(self, req: Request) -> bool:
        """If user can edit/upload files to static assets"""
        raise NotImplementedError(
            "Please implement 'has_files_permission' method "
            "before using the admin dashboard"
        )

    async def get_all_permissions(self, req: Request) -> dict[str, Any]:
        """Returns a map of"""
        permissions: dict[str, Any] = {}
        for db in self.all_dbs:
            permissions[db.configs_name] = {}
            for model in self.get_registered_models()[db.configs_name]:
                permissions[db.configs_name][model.__name__] = {
                    "CREATE": await self.has_create_permission(req, model),
                    "UPDATE": await self.has_update_permission(req, model),
                    "DELETE": await self.has_delete_permission(req, model),
                    "VIEW": await self.has_view_permission(req, model),
                }
        email_clients = self.get_email_clients()
        if email_clients is not None:
            for name, client in email_clients.items():
                permissions[name] = await self.has_email_permission(req, client)

        task_managers = self.get_task_managers()
        if task_managers is not None:
            for name, manager in task_managers.items():
                permissions[name] = await self.has_task_manager_permission(req, manager)

        cache_interfaces = self.get_cache_interfaces()
        if cache_interfaces is not None:
            for name, interface in cache_interfaces.items():
                permissions[name] = await self.has_cache_permission(req, interface)

        permissions["files"] = await self.has_files_permission(req)

        return permissions

    @staticmethod
    def format_datetime(value):
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return value  # fallback if parsing fails
