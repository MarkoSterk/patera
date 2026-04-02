"""
Chat history provider
"""

from uuid import UUID
from typing import Any, Type, Generic, TypeVar
from patera.database.sql import SqlDatabase, DeclarativeBaseModel
from patera.ctx import current_request

ModelT = TypeVar("ModelT", bound=DeclarativeBaseModel)


class BaseHistoryProvider(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(
        self,
        *,
        id_column: str = "session_id",
        message_column: str = "content",
        role_column: str = "role",
        order_column: str = "order_number",
    ) -> None:
        self._id_column = id_column
        self._message_column = message_column
        self._role_column = role_column
        self._order_column = order_column

    @property
    def id_column(self) -> str:
        return self._id_column

    @property
    def message_column(self) -> str:
        return self._message_column

    @property
    def role_column(self) -> str:
        return self._role_column

    @property
    def order_column(self) -> str:
        return self._order_column

    def order_by(self, history: list[ModelT]) -> list[ModelT]:
        return history

    async def _get_history(self, session_id: str | int | UUID) -> list[ModelT]:
        if session_id is None:
            raise ValueError("Missing session id for chat history loader.")
        database: SqlDatabase = current_request.app.extensions.get(
            self.model.db_name(), None
        )
        if database is None:
            raise ValueError(f"No database found for model {self.model.__name__}")
        session = current_request.session(database.session_name)
        history_query = self.model.query(session).filter(
            getattr(self.model, self.id_column) == session_id
        )
        if hasattr(self.model, self.order_column):
            history_query = history_query.order_by_strings(self.order_column)

        history: list[ModelT] = await history_query.all()
        return self.order_by(history)

    async def _get_history_messages(
        self, session_id: str | int | UUID
    ) -> list[dict[str, str]]:
        history = await self._get_history(session_id)
        return [
            {
                "role": getattr(m, self.role_column),
                "content": getattr(m, self.message_column),
            }
            for m in history
        ]

    def _save_message(
        self, message: dict[str, Any], memory_id: str | int | UUID, order_number: int
    ) -> None:
        database: SqlDatabase = current_request.app.extensions.get(
            self.model.db_name(), None
        )
        if database is None:
            raise ValueError(f"No database found for model {self.model.__name__}")
        session = current_request.session(database.session_name)
        message_obj = self.model()
        setattr(message_obj, self.id_column, memory_id)
        setattr(message_obj, self.message_column, message["content"])
        setattr(message_obj, self.role_column, message["role"])
        setattr(message_obj, self.order_column, order_number)
        session.add(message_obj)
