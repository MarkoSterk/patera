# repository.py

from __future__ import annotations

from functools import wraps
from inspect import signature
from types import NoneType, UnionType
from typing import (
    Any,
    Callable,
    Generic,
    Sequence,
    TypeGuard,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from sqlalchemy import select, text
from sqlalchemy.engine import Row, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from .sql_database import SqlDatabase
from .sqlalchemy_async_query import AsyncQuery, Page
from .declarative_base import DeclarativeBaseModel

from patera.ctx import current_request
from patera import Patera
from patera.base_extension import BaseExtension

T = TypeVar("T", bound=DeclarativeBaseModel)
M = TypeVar("M", bound=DeclarativeBaseModel)
F = TypeVar("F", bound=Callable[..., Any])
AppT = TypeVar("AppT", bound=Patera)


def query(sql_query: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        setattr(func, "__custom_query__", sql_query)
        return func

    return decorator


class Repository(BaseExtension[AppT], Generic[T, AppT]):
    model: type[T]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        if cls is not Repository and "model" not in cls.__dict__:
            raise TypeError(f"{cls.__name__} must define a 'model' class attribute")

        for name, value in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue

            if callable(value) and hasattr(value, "__custom_query__"):
                setattr(cls, name, cls._wrap_method(value))

    def __init__(self) -> None:
        super().__init__()
        self._database: SqlDatabase | None = None

    def init_app(self, app: AppT) -> None:
        self._app = app

    def get_database(self) -> SqlDatabase:
        if self._database is not None:
            self._database
        database = cast(
            SqlDatabase,
            cast(AppT, self._app).extensions.get(self.model.db_name(), None),
        )
        if database is None:
            raise ValueError(f"No database found for model {self.model.__name__}")
        self._database = database
        return self._database

    @property
    def session(self) -> AsyncSession:
        database = self.get_database()
        session: AsyncSession = current_request.session(database.session_name)
        return session

    @property
    def db_name(self) -> str:
        return self.model.db_name()

    @classmethod
    def _wrap_method(cls, func: F) -> F:
        @wraps(func)
        async def inner(self, *args, **kwargs):
            return await self._wrapper(func, *args, **kwargs)

        return cast(F, inner)

    async def _wrapper(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        sql_string = cast(str, getattr(func, "__custom_query__"))
        return_type: Any = get_type_hints(func).get("return")

        params = self._build_query_params(func, *args, **kwargs)

        if return_type is None:
            result = await self.session.execute(text(sql_string), params)
            return result.all()

        normalized_type, is_optional = self._unwrap_optional(return_type)
        origin = get_origin(normalized_type)
        type_args = get_args(normalized_type)

        if origin is list:
            item_type = type_args[0] if type_args else Any

            if self._is_model_type(item_type):
                return await self._execute_custom_orm_query(
                    item_type, sql_string, params
                )

            result = await self.session.execute(text(sql_string), params)
            rows = result.mappings().all()
            return self._convert_many(rows, item_type)

        if self._is_model_type(normalized_type):
            items = await self._execute_custom_orm_query(
                normalized_type, sql_string, params
            )

            if not items:
                if is_optional:
                    return None
                raise ValueError(
                    f"Query for {func.__name__} returned no rows, "
                    f"but return type {return_type!r} is not optional."
                )

            if len(items) > 1:
                raise ValueError(
                    f"Query for {func.__name__} returned {len(items)} rows, "
                    f"but return type {return_type!r} expects a single result."
                )

            return items[0]

        result = await self.session.execute(text(sql_string), params)
        rows = result.mappings().all()

        if not rows:
            if is_optional:
                return None
            raise ValueError(
                f"Query for {func.__name__} returned no rows, "
                f"but return type {return_type!r} is not optional."
            )

        if len(rows) > 1:
            raise ValueError(
                f"Query for {func.__name__} returned {len(rows)} rows, "
                f"but return type {return_type!r} expects a single result."
            )

        return self._convert_one(rows[0], normalized_type)

    def _build_query_params(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        bound = signature(func).bind_partial(None, *args, **kwargs)
        bound.apply_defaults()

        params: dict[str, Any] = {}
        for name, value in bound.arguments.items():
            if name == "self":
                continue
            params[name] = value
        return params

    async def _execute_custom_orm_query(
        self,
        model_type: type[M],
        sql_string: str,
        params: dict[str, Any],
    ) -> list[M]:
        stmt = select(model_type).from_statement(text(sql_string))
        result = await self.session.execute(stmt, params)
        return list(result.scalars().all())

    def _unwrap_optional(self, tp: Any) -> tuple[Any, bool]:
        origin = get_origin(tp)

        if origin in (Union, UnionType):
            args_ = get_args(tp)
            non_none = [arg for arg in args_ if arg is not NoneType]
            if len(non_none) == 1 and len(non_none) != len(args_):
                return non_none[0], True

        return tp, False

    def _convert_many(self, rows: Sequence[RowMapping], item_type: Any) -> Any:
        origin = get_origin(item_type)

        if item_type is dict or origin is dict:
            return [dict(row) for row in rows]

        if item_type is Any:
            return rows

        if self._is_scalar_type(item_type):
            converted: list[Any] = []
            for row in rows:
                values = list(dict(row).values())
                if len(values) != 1:
                    raise ValueError(
                        f"Cannot map multi-column row {dict(row)!r} to scalar {item_type!r}."
                    )
                converted.append(item_type(values[0]))
            return converted

        return [item_type(**dict(row)) for row in rows]

    def _convert_one(self, row: RowMapping, target_type: Any) -> Any:
        origin = get_origin(target_type)

        if target_type is dict or origin is dict:
            return dict(row)

        if self._is_scalar_type(target_type):
            values = list(dict(row).values())
            if len(values) != 1:
                raise ValueError(
                    f"Cannot map multi-column row {dict(row)!r} to scalar {target_type!r}."
                )
            return target_type(values[0])

        if target_type is Row:
            return row

        return target_type(**dict(row))

    def _is_model_type(self, tp: Any) -> TypeGuard[type[DeclarativeBaseModel]]:
        return isinstance(tp, type) and issubclass(tp, DeclarativeBaseModel)

    def _is_scalar_type(self, tp: Any) -> bool:
        return tp in (int, str, float, bool)

    @property
    def query(self) -> AsyncQuery[T]:
        return AsyncQuery(
            session=self.session,
            model=self.model,
        )

    async def get(self, entity_id: Any) -> T | None:
        return await self.session.get(self.model, entity_id)

    async def get_one_by(self, **filters: Any) -> T | None:
        return await self.query.filter_by(**filters).one_or_none()

    async def first_by(self, **filters: Any) -> T | None:
        return await self.query.filter_by(**filters).first()

    async def list_all(self) -> list[T]:
        return await self.query.all()

    async def list_by(self, **filters: Any) -> list[T]:
        return await self.query.filter_by(**filters).all()

    async def count(self, **filters: Any) -> int:
        return await self.query.filter_by(**filters).count()

    async def exists(self, **filters: Any) -> bool:
        return await self.query.filter_by(**filters).exists()

    def create(self, **kwargs: Any) -> T:
        entity = self.model(**kwargs)
        self.session.add(entity)
        return entity

    def add(self, entity: T) -> T:
        self.session.add(entity)
        return entity

    def add_all(self, entities: list[T]) -> list[T]:
        self.session.add_all(entities)
        return entities

    async def delete(self, entity: T) -> None:
        await self.session.delete(entity)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(
        self, entity: T, attribute_names: list[str] | None = None
    ) -> None:
        await self.session.refresh(entity, attribute_names=attribute_names)

    async def save(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def create_and_flush(self, **kwargs: Any) -> T:
        entity = self.create(**kwargs)
        await self.session.flush()
        return entity

    async def paginate(
        self,
        *,
        page: int = 1,
        per_page: int = 10,
        **filters: Any,
    ) -> Page[T]:
        return await self.query.filter_by(**filters).paginate(
            page=page, per_page=per_page
        )

    async def execute(self, stmt: Select[Any]) -> list[Any]:
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
