from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from .declarative_base import DeclarativeBaseModel


T = TypeVar("T", bound=DeclarativeBaseModel)


@dataclass(slots=True)
class Page(Generic[T]):
    items: list[T]
    total: int
    page: int
    pages: int
    per_page: int
    has_next: bool
    has_prev: bool


@dataclass(slots=True)
class AsyncQuery(Generic[T]):
    """
    Typed async query builder for ORM model queries.
    """

    session: AsyncSession
    model: type[T]
    statement: Select[tuple[T]] | None = None

    def __post_init__(self) -> None:
        if self.statement is None:
            self.statement = select(self.model)

    def _stmt(self) -> Select[tuple[T]]:
        if self.statement is None:
            raise RuntimeError("AsyncQuery.statement was not initialized")
        return self.statement

    def _clone(self, statement: Select[tuple[T]]) -> AsyncQuery[T]:
        return AsyncQuery(
            session=self.session,
            model=self.model,
            statement=statement,
        )

    def where(self, *conditions: Any) -> AsyncQuery[T]:
        return self._clone(self._stmt().where(*conditions))

    def filter(self, *conditions: Any) -> AsyncQuery[T]:
        return self.where(*conditions)

    def filter_by(self, **kwargs: Any) -> AsyncQuery[T]:
        return self._clone(self._stmt().filter_by(**kwargs))

    def join(self, target: Any, *props: Any, isouter: bool = False) -> AsyncQuery[T]:
        return self._clone(self._stmt().join(target, *props, isouter=isouter))

    def outerjoin(self, target: Any, *props: Any) -> AsyncQuery[T]:
        return self._clone(self._stmt().outerjoin(target, *props))

    def limit(self, num: int) -> AsyncQuery[T]:
        return self._clone(self._stmt().limit(num))

    def offset(self, num: int) -> AsyncQuery[T]:
        return self._clone(self._stmt().offset(num))

    def order_by(self, *columns: Any) -> AsyncQuery[T]:
        return self._clone(self._stmt().order_by(*columns))

    def order_by_strings(self, *args: str) -> AsyncQuery[T]:
        ordering: list[Any] = []

        for order_str in args:
            parts = order_str.strip().split()
            if not parts:
                continue

            col_name = parts[0]
            direction = parts[1].upper() if len(parts) > 1 else "ASC"
            column = getattr(self.model, col_name)

            if direction == "DESC":
                ordering.append(column.desc())
            else:
                ordering.append(column.asc())

        return self.order_by(*ordering)

    def like(
        self, column: Any, pattern: str, escape: str | None = None
    ) -> AsyncQuery[T]:
        return self.where(column.like(pattern, escape=escape))

    def ilike(
        self, column: Any, pattern: str, escape: str | None = None
    ) -> AsyncQuery[T]:
        return self.where(column.ilike(pattern, escape=escape))

    async def count(self) -> int:
        base = self._stmt().order_by(None).subquery()
        count_stmt = select(func.count()).select_from(base)
        result = await self.session.execute(count_stmt)
        return int(result.scalar_one() or 0)

    async def exists(self) -> bool:
        result = await self.session.execute(self._stmt().limit(1))
        return result.scalars().first() is not None

    async def all(self) -> list[T]:
        result = await self.session.execute(self._stmt())
        return list(result.scalars().all())

    async def first(self) -> T | None:
        result = await self.session.execute(self._stmt().limit(1))
        return result.scalars().first()

    async def one(self) -> T:
        result = await self.session.execute(self._stmt())
        return result.scalars().one()

    async def one_or_none(self) -> T | None:
        result = await self.session.execute(self._stmt())
        return result.scalars().one_or_none()

    async def paginate(self, page: int = 1, per_page: int = 10) -> Page[T]:
        page = max(page, 1)
        per_page = max(per_page, 1)

        total = await self.count()
        pages = ceil(total / per_page) if total > 0 else 0

        stmt = self._stmt().limit(per_page).offset((page - 1) * per_page)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return Page(
            items=items,
            total=total,
            page=page,
            pages=pages,
            per_page=per_page,
            has_next=page < pages,
            has_prev=page > 1,
        )
