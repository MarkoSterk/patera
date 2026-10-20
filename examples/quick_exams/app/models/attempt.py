from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..errors import ExamError
from .base import Base, service


class Attempt(Base):
    """
    A student's attempt, with a copy of the exam settings. The source exam id
    has no foreign key, so the archive survives deletion of the live exam.
    """

    __tablename__ = "attempts"

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    source_exam_id: Mapped[str] = mapped_column(String(32), index=True)
    student_email: Mapped[str] = mapped_column(String(254))
    started_at: Mapped[str] = mapped_column(String(40))
    submitted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exam_title: Mapped[str] = mapped_column(String(200))
    available_from: Mapped[str] = mapped_column(String(40))
    available_until: Mapped[str] = mapped_column(String(40))
    pass_percentage: Mapped[float] = mapped_column(Float)
    earned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    class Meta(Base.Meta):
        exclude_from_update_form = [
            "owner_id",
            "source_exam_id",
            "started_at",
            "submitted_at",
            "exam_title",
            "available_from",
            "available_until",
            "pass_percentage",
            "earned_points",
            "maximum_points",
            "score_percentage",
            "passed",
        ]

    async def admin_clean(self, values, creating):
        from ..services.attempts import AttemptService

        return service(AttemptService).admin_clean_attempt(self, values, creating)

    async def admin_check_delete(self):
        raise ExamError("Archived exam evidence must be retained")


class AttemptQuestion(Base):
    __tablename__ = "attempt_questions"
    __table_args__ = (
        UniqueConstraint("attempt_id", "position"),
        UniqueConstraint("attempt_id", "source_question_id"),
        CheckConstraint("correct_answer BETWEEN 0 AND 3"),
        CheckConstraint("selected_answer IS NULL OR selected_answer BETWEEN 0 AND 3"),
        CheckConstraint("points > 0"),
    )

    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("attempts.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    source_question_id: Mapped[str] = mapped_column(String(32))
    source_category_id: Mapped[str] = mapped_column(String(32))
    question_text: Mapped[str] = mapped_column(Text)
    image: Mapped[str] = mapped_column(Text, default="")
    answer_1: Mapped[str] = mapped_column(Text)
    answer_2: Mapped[str] = mapped_column(Text)
    answer_3: Mapped[str] = mapped_column(Text)
    answer_4: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float)
    selected_answer: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def answers(self) -> list[str]:
        return [self.answer_1, self.answer_2, self.answer_3, self.answer_4]

    async def admin_clean(self, values, creating):
        raise ExamError("Archived questions and answers are immutable")

    async def admin_check_delete(self):
        raise ExamError("Archived exam evidence must be retained")
