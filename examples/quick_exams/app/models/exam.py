from __future__ import annotations

from patera.admin.custom_elements import DateInput
from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, service


class Exam(Base):
    """Availability timestamps are ISO 8601 strings in UTC."""

    __tablename__ = "exams"
    __table_args__ = (
        CheckConstraint("pass_percentage BETWEEN 0 AND 100"),
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
        form_fields_order = [
            "owner_id",
            "subject_id",
            "title",
            "available_from",
            "available_until",
            "pass_percentage",
        ]

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_exam(self, values, creating)


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (
        UniqueConstraint("exam_id", "question_id"),
        UniqueConstraint("exam_id", "position"),
        CheckConstraint("position >= 0"),
        ForeignKeyConstraint(
            ["exam_id", "subject_id"],
            ["exams.id", "exams.subject_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["question_id", "subject_id"],
            ["questions.id", "questions.subject_id"],
            ondelete="RESTRICT",
        ),
    )

    exam_id: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(32))
    question_id: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)

    class Meta(Base.Meta):
        exclude_from_create_form = ["id", "subject_id"]
        exclude_from_update_form = ["subject_id"]

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_exam_question(values)
