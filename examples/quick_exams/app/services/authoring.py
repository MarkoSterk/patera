from __future__ import annotations

import random
from typing import Any, Optional

from patera import Service, UploadedFile
from patera.database.sql import Repository
from patera.injectable import Inject

from ..errors import Conflict, ExamError, NotFound, require
from ..models import Base, Category, Exam, Question
from ..repository import Categories, ExamQuestions, Exams, Questions, Users
from ..schemas import (
    CategoryIn,
    ExamIn,
    ExamSettingsIn,
    QuestionIn,
    image_data_url,
    to_utc_iso,
)


class AuthoringService(Service):
    users: Inject[Users]
    categories: Inject[Categories]
    questions: Inject[Questions]
    exams: Inject[Exams]
    exam_questions: Inject[ExamQuestions]

    async def _owned(
        self, repository: Repository[Any], record_id: str, owner_id: str, label: str
    ) -> Any:
        """The owner's record; another instructor's record is reported as missing."""
        record = await repository.get(record_id)
        require(
            record is not None and getattr(record, "owner_id", None) == owner_id,
            f"{label} not found",
            NotFound,
        )
        return record

    async def list_categories(self, owner_id: str) -> list[Category]:
        return await self.categories.owned_by(owner_id)

    async def create_category(self, owner_id: str, data: CategoryIn) -> Category:
        return await self.categories.create_and_flush(owner_id=owner_id, name=data.name)

    async def update_category(
        self, owner_id: str, category_id: str, data: CategoryIn
    ) -> Category:
        category: Category = await self._owned(
            self.categories, category_id, owner_id, "Category"
        )
        category.name = data.name
        await self.categories.flush()
        return category

    async def delete_category(self, owner_id: str, category_id: str) -> None:
        category: Category = await self._owned(
            self.categories, category_id, owner_id, "Category"
        )
        require(
            not await self.questions.exists(category_id=category.id),
            "Move or delete the category's questions first",
            Conflict,
        )
        await self.categories.delete(category)

    async def list_questions(self, owner_id: str) -> list[Question]:
        return await self.questions.owned_by(owner_id)

    async def _check_category(self, owner_id: str, category_id: str) -> None:
        category = await self.categories.get(category_id)
        require(
            category is not None and category.owner_id == owner_id,
            "Choose one of your categories",
        )

    @staticmethod
    def _fill_question(question: Question, data: QuestionIn) -> Question:
        question.category_id = data.category_id
        question.question_text = data.question_text
        question.answers = data.answers
        question.correct_answer = data.correct_answer
        question.points = data.points
        question.image = data.image
        return question

    async def create_question(self, owner_id: str, data: QuestionIn) -> Question:
        await self._check_category(owner_id, data.category_id)
        return await self.questions.save(
            self._fill_question(Question(owner_id=owner_id), data)
        )

    async def update_question(
        self, owner_id: str, question_id: str, data: QuestionIn
    ) -> Question:
        question: Question = await self._owned(
            self.questions, question_id, owner_id, "Question"
        )
        await self._check_category(owner_id, data.category_id)
        return await self.questions.save(self._fill_question(question, data))

    async def delete_question(self, owner_id: str, question_id: str) -> None:
        question: Question = await self._owned(
            self.questions, question_id, owner_id, "Question"
        )
        require(
            not await self.exam_questions.exists(question_id=question.id),
            "Remove this question from live exams first",
            Conflict,
        )
        await self.questions.delete(question)

    async def list_exams(self, owner_id: str) -> list[dict[str, Any]]:
        exams = await self.exams.owned_by(owner_id)
        selected = await self.exam_questions.for_exams([exam.id for exam in exams])
        return [self._exam_out(exam, selected[exam.id]) for exam in exams]

    async def get_exam(self, owner_id: str, exam_id: str) -> Exam:
        exam: Exam = await self._owned(self.exams, exam_id, owner_id, "Exam")
        return exam

    async def create_exam(self, owner_id: str, data: ExamIn) -> dict[str, Any]:
        question_ids = await self._select_questions(owner_id, data)
        exam = await self.exams.save(self._fill_exam(Exam(owner_id=owner_id), data))
        await self.exam_questions.replace(exam.id, question_ids)
        return self._exam_out(exam, question_ids)

    async def update_exam(
        self, owner_id: str, exam_id: str, data: ExamIn
    ) -> dict[str, Any]:
        exam = await self.get_exam(owner_id, exam_id)
        question_ids = await self._select_questions(owner_id, data)
        await self.exams.save(self._fill_exam(exam, data))
        await self.exam_questions.replace(exam.id, question_ids)
        return self._exam_out(exam, question_ids)

    async def delete_exam(self, owner_id: str, exam_id: str) -> None:
        await self.exams.delete(await self.get_exam(owner_id, exam_id))

    async def _select_questions(self, owner_id: str, data: ExamIn) -> list[str]:
        if data.random is not None:
            pool = await self.questions.ids_in_categories(
                owner_id, data.random.category_ids
            )
            require(
                data.random.count <= len(pool),
                "Not enough questions in the selected categories",
            )
            return random.SystemRandom().sample(pool, data.random.count)
        owned = await self.questions.query.where(
            Question.id.in_(data.question_ids), Question.owner_id == owner_id
        ).count()
        require(owned == len(data.question_ids), "Select only your own questions")
        return data.question_ids

    @staticmethod
    def _fill_exam(exam: Exam, data: ExamSettingsIn) -> Exam:
        exam.title = data.title
        exam.available_from = to_utc_iso(data.available_from)
        exam.available_until = to_utc_iso(data.available_until)
        exam.pass_percentage = data.pass_percentage
        return exam

    @staticmethod
    def _exam_out(exam: Exam, question_ids: list[str]) -> dict[str, Any]:
        return {
            "id": exam.id,
            "title": exam.title,
            "available_from": exam.available_from,
            "available_until": exam.available_until,
            "pass_percentage": exam.pass_percentage,
            "question_ids": question_ids,
        }

    async def _admin_owner(
        self, record: Base, values: dict[str, Any], creating: bool
    ) -> str:
        owner_id: Optional[str] = values.get("owner_id")
        require(owner_id and await self.users.get(owner_id), "Choose an existing owner")
        require(
            creating or owner_id == record.owner_id,
            "The owner cannot change",
        )
        return owner_id  # type: ignore[return-value]

    async def admin_clean_category(self, record, values, creating):
        await self._admin_owner(record, values, creating)
        values["name"] = CategoryIn(name=values.get("name") or "").name
        return values

    async def admin_clean_question(self, record, values, creating):
        owner_id = await self._admin_owner(record, values, creating)
        image = values.get("image") or ""
        if isinstance(image, UploadedFile):
            try:
                image = image_data_url(image.read())
            except ValueError as exc:
                raise ExamError(str(exc)) from exc
        if values.pop("remove_image", False):
            image = ""
        data = QuestionIn(
            category_id=values.get("category_id") or "",
            question_text=values.get("question_text") or "",
            answers=[values.get(f"answer_{n}") or "" for n in range(1, 5)],
            correct_answer=values.get("correct_answer"),
            points=values.get("points"),
            image=image,
        )
        await self._check_category(owner_id, data.category_id)
        values.update(
            question_text=data.question_text,
            image=data.image,
            correct_answer=data.correct_answer,
            points=data.points,
            **{f"answer_{n}": answer for n, answer in enumerate(data.answers, start=1)},
        )
        return values

    async def admin_clean_exam(self, record, values, creating):
        await self._admin_owner(record, values, creating)
        data = ExamSettingsIn(
            title=values.get("title") or "",
            available_from=values.get("available_from"),
            available_until=values.get("available_until"),
            pass_percentage=values.get("pass_percentage"),
        )
        values.update(
            title=data.title,
            available_from=to_utc_iso(data.available_from),
            available_until=to_utc_iso(data.available_until),
            pass_percentage=data.pass_percentage,
        )
        return values

    async def admin_clean_exam_question(self, values):
        exam = await self.exams.get(values.get("exam_id") or "")
        question = await self.questions.get(values.get("question_id") or "")
        require(exam and question, "Choose an existing exam and question")
        require(
            exam.owner_id == question.owner_id,
            "Exam and question must belong to the same instructor",
        )
        position = values.get("position")
        if not isinstance(position, int) or position < 0:
            raise ExamError("Position must be a non-negative number")
        return values
