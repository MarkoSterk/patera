from __future__ import annotations

from patera.admin.custom_elements import DateInput
from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, service


class Exam(Base):
    """Availability timestamps are ISO 8601 strings in UTC."""

    __tablename__ = "exams"
    __table_args__ = (CheckConstraint("pass_percentage BETWEEN 0 AND 100"),)

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    available_from: Mapped[str] = mapped_column(String(40))
    available_until: Mapped[str] = mapped_column(String(40))
    pass_percentage: Mapped[float] = mapped_column(Float, default=50)

    class Meta(Base.Meta):
        custom_form_fields = [
            DateInput(name="available_from", include_time=True, utc=True),
            DateInput(name="available_until", include_time=True, utc=True),
        ]
        custom_labels = {
            "available_from": "Available from (your local time)",
            "available_until": "Available until (your local time)",
        }

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_exam(self, values, creating)


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (
        UniqueConstraint("exam_id", "question_id"),
        UniqueConstraint("exam_id", "position"),
        CheckConstraint("position >= 0"),
    )

    exam_id: Mapped[str] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_exam_question(values)
