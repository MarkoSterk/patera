from __future__ import annotations

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, service


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("id", "subject_id"),
        ForeignKeyConstraint(
            ["subject_id", "owner_id"],
            ["subjects.id", "subjects.owner_id"],
            ondelete="RESTRICT",
        ),
    )

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    subject_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))

    class Meta(Base.Meta):
        form_fields_order = ["owner_id", "subject_id", "name"]

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_category(
            self, values, creating
        )
