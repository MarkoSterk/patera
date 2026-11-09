from __future__ import annotations

from patera.admin.custom_elements import DateInput
from sqlalchemy import (
    Boolean,
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
    """
    Availability timestamps are ISO 8601 strings in UTC. An exam either has a
    fixed question selection (ExamQuestion) or, when ``random_per_attempt``
    is set, draws ``random_count`` questions from its categories
    (ExamCategory) separately for every attempt.
    """

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
    random_per_attempt: Mapped[bool] = mapped_column(Boolean, default=False)
    random_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    class Meta(Base.Meta):
        custom_form_fields = [
            DateInput(name="available_from", include_time=True, utc=True),
            DateInput(name="available_until", include_time=True, utc=True),
        ]
        custom_labels = {
            "available_from": "Available from (your local time)",
            "available_until": "Available until (your local time)",
            "random_per_attempt": "Different random questions for every attempt",
            "random_count": "Questions per attempt (random per attempt only)",
        }
        form_fields_order = [
            "owner_id",
            "subject_id",
            "title",
            "available_from",
            "available_until",
            "pass_percentage",
            "random_per_attempt",
            "random_count",
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


class ExamCategory(Base):
    """A category that a random-per-attempt exam draws its questions from."""

    __tablename__ = "exam_categories"
    __table_args__ = (
        UniqueConstraint("exam_id", "category_id"),
        ForeignKeyConstraint(
            ["exam_id", "subject_id"],
            ["exams.id", "exams.subject_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["category_id", "subject_id"],
            ["categories.id", "categories.subject_id"],
            ondelete="RESTRICT",
        ),
    )

    exam_id: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(32))
    category_id: Mapped[str] = mapped_column(String(32))

    class Meta(Base.Meta):
        exclude_from_create_form = ["id", "subject_id"]
        exclude_from_update_form = ["subject_id"]

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_exam_category(values)
