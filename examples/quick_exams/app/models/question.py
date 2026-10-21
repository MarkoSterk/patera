from __future__ import annotations

from patera.admin.custom_elements import FileInput, LatexInput
from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..schemas import IMAGE_TYPES, MAX_IMAGE_BYTES
from .base import Base, service


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("correct_answer BETWEEN 0 AND 3"),
        CheckConstraint("points > 0 AND points <= 100000"),
        UniqueConstraint("id", "subject_id"),
        ForeignKeyConstraint(
            ["subject_id", "owner_id"],
            ["subjects.id", "subjects.owner_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["category_id", "subject_id"],
            ["categories.id", "categories.subject_id"],
            ondelete="RESTRICT",
        ),
    )

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    subject_id: Mapped[str] = mapped_column(String(32))
    category_id: Mapped[str] = mapped_column(String(32))
    question_text: Mapped[str] = mapped_column(Text)
    image: Mapped[str] = mapped_column(Text, default="")
    answer_1: Mapped[str] = mapped_column(Text)
    answer_2: Mapped[str] = mapped_column(Text)
    answer_3: Mapped[str] = mapped_column(Text)
    answer_4: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float, default=1)

    class Meta(Base.Meta):
        exclude_from_table = ["image"]
        custom_form_fields = [
            LatexInput(name="question_text", maxlength=5000),
            *(
                LatexInput(name=f"answer_{n}", multiline=False, maxlength=2000)
                for n in range(1, 5)
            ),
            FileInput(name="image", accept=IMAGE_TYPES, max_size=MAX_IMAGE_BYTES),
        ]
        add_to_form = {"remove_image": bool}
        custom_labels = {
            "question_text": "Question (LaTeX math between $…$ or $$…$$)",
            "correct_answer": "Correct answer index (0–3)",
            "image": "Image (PNG, JPEG, GIF or WebP; up to 2 MB)",
            "remove_image": "Remove the current image",
        }
        form_fields_order = [
            "owner_id",
            "subject_id",
            "category_id",
            "question_text",
            "answer_1",
            "answer_2",
            "answer_3",
            "answer_4",
            "correct_answer",
            "points",
            "image",
            "remove_image",
        ]

    @property
    def answers(self) -> list[str]:
        return [self.answer_1, self.answer_2, self.answer_3, self.answer_4]

    @answers.setter
    def answers(self, values: list[str]) -> None:
        self.answer_1, self.answer_2, self.answer_3, self.answer_4 = values

    async def admin_clean(self, values, creating):
        from ..services.authoring import AuthoringService

        return await service(AuthoringService).admin_clean_question(
            self, values, creating
        )
