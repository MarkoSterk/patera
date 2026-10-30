"""Pyright regression: explicit class configuration overrides must agree.

Run with: .venv/Scripts/python.exe tests/typing/check_config.py
"""

from typing import Any, ClassVar

from patera import Patera
from patera.base_extension import BaseExtension
from patera.admin import AdminInterface
from patera.admin.custom_elements import BaseHtmlInput, TagsInput
from patera.auth.authentication import AuthUtils
from patera.caching import BaseCacheBackend, Caching, MemoryCacheBackend
from patera.database.sql import DeclarativeBaseModel, SqlDatabase, SqlDatabaseManager
from patera.taskmanager import TaskManager
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel


class App(Patera):
    pass


class SiteDb(SqlDatabase[App]):
    __db_name__: ClassVar[str] = "site"


class Databases(SqlDatabaseManager[App]):
    databases: ClassVar[list[type[SqlDatabase[Any]]]] = [SiteDb]


class SiteAdmin(AdminInterface):
    managed_models: ClassVar[list[type[DeclarativeBaseModel]]] = []


class ConfiguredApp(Patera):
    app_extensions: ClassVar[list[type[BaseExtension[Any, Any]]]] = [
        Databases,
        SiteAdmin,
    ]


class Jobs(TaskManager):
    scheduler_cls: ClassVar[type[BaseScheduler]] = AsyncIOScheduler
    job_defaults: ClassVar[dict[str, bool | int]] = {"coalesce": True}


class CustomInput(BaseHtmlInput):
    tag_name: ClassVar[str] = "custom-input"
    converts_value: ClassVar[bool] = True


class PasswordUtils(AuthUtils):
    PASSWORD_HASH_PREFIX: ClassVar[str] = "bcrypt-sha256$"


class Cache(Caching):
    backend_class: ClassVar[type[BaseCacheBackend]] = MemoryCacheBackend


class Article(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__: ClassVar[str] = "site"

    class Meta(DeclarativeBaseModel.Meta):
        exclude_from_create_form: ClassVar[list[str]] = ["id"]
        exclude_from_update_form: ClassVar[list[str]] = ["id"]
        exclude_from_table: ClassVar[list[str]] = ["body"]
        custom_labels: ClassVar[dict[str, str]] = {"body": "Content"}
        add_to_form: ClassVar[dict[str, type[Any]]] = {"confirm": bool}
        custom_form_fields: ClassVar[list[Any]] = [TagsInput(name="tags")]
        form_fields_order: ClassVar[list[str]] = ["body"]
        table_fields_order: ClassVar[list[str]] = ["id"]
        order_table_by: ClassVar[list[str]] = ["id"]
        create_validation_schema: ClassVar[type[BaseModel] | None] = None
        update_validation_schema: ClassVar[type[BaseModel] | None] = None


class DerivedArticle(Article):
    __abstract__ = True

    class Meta(Article.Meta):
        custom_labels: ClassVar[dict[str, str]] = {"body": "Article text"}
