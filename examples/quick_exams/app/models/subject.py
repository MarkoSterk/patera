from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, service


class Subject(Base):
    """An instructor's subject; it groups categories, questions and exams."""

    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("owner_id", "name"),
        UniqueConstraint("id", "owner_id"),
    )

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_subject(
            self, values, creating
        )

    async def admin_check_delete(self):
        from ..services.authoring import AuthoringService

        await service(AuthoringService).ensure_subject_unused(self)
