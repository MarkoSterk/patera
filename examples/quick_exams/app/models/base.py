from __future__ import annotations

import secrets
from typing import Any

from patera.admin.form_values import AdminFormError
from patera.ctx import current_request
from patera.database.sql import DeclarativeBaseModel
from patera.database.sql.declarative_base import ModelMeta
from pydantic import ValidationError
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..errors import ExamError


def new_id() -> str:
    """Unpredictable identifier; exam and attempt ids double as capabilities."""
    return secrets.token_urlsafe(24)


def service(service_type: type) -> Any:
    return current_request.app.get_extension(service_type)


def _form_error(exc: ExamError) -> AdminFormError:
    return AdminFormError(
        [{"loc": ["record"], "msg": exc.message, "type": "value_error"}]
    )


class Base(DeclarativeBaseModel):
    """
    Base model of the exams database. Admin forms pass through
    ``admin_clean`` and deletions through ``admin_check_delete``, which models
    override to apply the same service rules as the API.
    """

    __abstract__ = True
    __db_name__ = "exams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)

    class Meta(ModelMeta):
        exclude_from_create_form = ["id"]

    async def admin_create(self, new_data: dict[str, Any]) -> None:
        await self._admin_apply(new_data, creating=True)

    async def admin_update(self, new_data: dict[str, Any]) -> None:
        await self._admin_apply(new_data, creating=False)

    async def admin_delete(self) -> None:
        try:
            await self.admin_check_delete()
        except ExamError as exc:
            raise _form_error(exc) from exc

    async def _admin_apply(self, new_data: dict[str, Any], creating: bool) -> None:
        values = {**self._current_values(creating), **new_data}
        try:
            values = await self.admin_clean(values, creating)
        except ExamError as exc:
            raise _form_error(exc) from exc
        except ValidationError as exc:
            raise AdminFormError(
                exc.errors(
                    include_url=False, include_input=False, include_context=False
                )
            ) from exc
        columns = self.__table__.columns.keys()
        for key, value in values.items():
            if key in columns and key != "id":
                setattr(self, key, value)

    def _current_values(self, creating: bool) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for column in self.__table__.columns:
            if creating:
                default = column.default
                values[column.key] = (
                    default.arg if default is not None and default.is_scalar else None
                )
            else:
                values[column.key] = getattr(self, column.key)
        return values

    async def admin_clean(
        self, values: dict[str, Any], creating: bool
    ) -> dict[str, Any]:
        return values

    async def admin_check_delete(self) -> None:
        pass
