from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, service

INSTRUCTOR = "INSTRUCTOR"
ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_instructor: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)

    class Meta(Base.Meta):
        exclude_from_create_form = ["id", "password_hash", "token_version"]
        exclude_from_update_form = ["password_hash", "token_version"]
        exclude_from_table = ["password_hash"]
        add_to_form = {"password": str}
        custom_labels = {
            "password": "New password (12+ characters; blank keeps current)",
            "token_version": "Token version (increase to sign the user out)",
        }

    @property
    def roles(self) -> list[str]:
        return [
            role
            for role, enabled in (
                (INSTRUCTOR, self.is_instructor),
                (ADMIN, self.is_admin),
            )
            if enabled
        ]

    async def admin_clean(self, values, creating):
        from ..services.accounts import AccountService

        return await service(AccountService).admin_clean_user(self, values, creating)

    async def admin_check_delete(self):
        from ..services.accounts import AccountService

        await service(AccountService).ensure_admin_remains(self)
