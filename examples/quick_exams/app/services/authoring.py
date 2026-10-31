from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, Optional

from patera.database.sql import Repository

from patera import Service, UploadedFile
from patera.injectable import Inject

from ..errors import Conflict, ExamError, NotFound, require
from ..models import Base, Category, Exam, Question, Subject
from ..repository import (
    Categories,
    ExamQuestions,
    Exams,
    Questions,
    Subjects,
    Users,
)
from ..schemas import (
    CategoryIn,
    ExamIn,
    ExamSettingsIn,
    QuestionIn,
    SubjectIn,
    image_data_url,
    to_utc_iso,
)

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


class AuthoringService(Service["App"]):
    """
    An instructor's subjects and their content. A category belongs to one
    subject, a question to one subject and one of its categories, and an
    exam to one subject, from which it selects its questions.
    """

    users: Inject[Users]
    subjects: Inject[Subjects]
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

    async def list_subjects(self, owner_id: str) -> list[Subject]:
        return await self.subjects.owned_by(owner_id)

    async def _check_subject_name(
        self, owner_id: str, name: str, subject_id: Optional[str] = None
    ) -> None:
        existing = await self.subjects.first_by(owner_id=owner_id, name=name)
        require(
            existing is None or existing.id == subject_id,
            "You already have a subject with this name",
            Conflict,
        )

    async def create_subject(self, owner_id: str, data: SubjectIn) -> Subject:
        await self._check_subject_name(owner_id, data.name)
        return await self.subjects.create_and_flush(
            owner_id=owner_id, name=data.name, description=data.description
        )

    async def update_subject(
        self, owner_id: str, subject_id: str, data: SubjectIn
    ) -> Subject:
        subject: Subject = await self._owned(
            self.subjects, subject_id, owner_id, "Subject"
        )
        await self._check_subject_name(owner_id, data.name, subject.id)
        subject.name = data.name
        subject.description = data.description
        await self.subjects.flush()
        return subject

    async def ensure_subject_unused(self, subject: Subject) -> None:
        require(
            not await self.categories.exists(subject_id=subject.id)
            and not await self.exams.exists(subject_id=subject.id),
            "Delete the subject's categories and exams first",
            Conflict,
        )

    async def delete_subject(self, owner_id: str, subject_id: str) -> None:
        subject: Subject = await self._owned(
            self.subjects, subject_id, owner_id, "Subject"
        )
        await self.ensure_subject_unused(subject)
        await self.subjects.delete(subject)

    async def _check_subject(self, owner_id: str, subject_id: str) -> None:
        subject = await self.subjects.get(subject_id)
        require(
            subject is not None and subject.owner_id == owner_id,
            "Choose one of your subjects",
        )

    async def list_categories(self, owner_id: str) -> list[Category]:
        return await self.categories.owned_by(owner_id)

    async def create_category(self, owner_id: str, data: CategoryIn) -> Category:
        await self._check_subject(owner_id, data.subject_id)
        return await self.categories.create_and_flush(
            owner_id=owner_id, subject_id=data.subject_id, name=data.name
        )

    async def _check_category_move(self, category: Category, subject_id: str) -> None:
        require(
            subject_id == category.subject_id
            or not await self.questions.exists(category_id=category.id),
            "A category with questions cannot move to another subject",
            Conflict,
        )

    async def update_category(
        self, owner_id: str, category_id: str, data: CategoryIn
    ) -> Category:
        category: Category = await self._owned(
            self.categories, category_id, owner_id, "Category"
        )
        await self._check_subject(owner_id, data.subject_id)
        await self._check_category_move(category, data.subject_id)
        category.subject_id = data.subject_id
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

    async def _check_placement(
        self, owner_id: str, subject_id: str, category_id: str
    ) -> None:
        """The subject is the owner's, and the category belongs to it."""
        await self._check_subject(owner_id, subject_id)
        category = await self.categories.get(category_id)
        require(
            category is not None and category.subject_id == subject_id,
            "Choose a category of the selected subject",
        )

    async def _check_question_move(self, question: Question, subject_id: str) -> None:
        require(
            subject_id == question.subject_id
            or not await self.exam_questions.exists(question_id=question.id),
            "Remove this question from exams before moving it to another subject",
            Conflict,
        )

    @staticmethod
    def _fill_question(question: Question, data: QuestionIn) -> Question:
        question.subject_id = data.subject_id
        question.category_id = data.category_id
        question.question_text = data.question_text
        question.answers = data.answers
        question.correct_answer = data.correct_answer
        question.points = data.points
        question.image = data.image
        return question

    async def create_question(self, owner_id: str, data: QuestionIn) -> Question:
        await self._check_placement(owner_id, data.subject_id, data.category_id)
        return await self.questions.save(
            self._fill_question(Question(owner_id=owner_id), data)
        )

    async def update_question(
        self, owner_id: str, question_id: str, data: QuestionIn
    ) -> Question:
        question: Question = await self._owned(
            self.questions, question_id, owner_id, "Question"
        )
        await self._check_placement(owner_id, data.subject_id, data.category_id)
        await self._check_question_move(question, data.subject_id)
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
        await self._check_subject(owner_id, data.subject_id)
        question_ids = await self._select_questions(owner_id, data)
        exam = await self.exams.save(self._fill_exam(Exam(owner_id=owner_id), data))
        await self.exam_questions.add_selection(exam.id, exam.subject_id, question_ids)
        return self._exam_out(exam, question_ids)

    async def update_exam(
        self, owner_id: str, exam_id: str, data: ExamIn
    ) -> dict[str, Any]:
        exam = await self.get_exam(owner_id, exam_id)
        await self._check_subject(owner_id, data.subject_id)
        question_ids = await self._select_questions(owner_id, data)
        # The old selection refers to the exam's current subject, so it goes
        # before the subject can change.
        await self.exam_questions.clear(exam.id)
        await self.exams.save(self._fill_exam(exam, data))
        await self.exam_questions.add_selection(exam.id, exam.subject_id, question_ids)
        return self._exam_out(exam, question_ids)

    async def delete_exam(self, owner_id: str, exam_id: str) -> None:
        await self.exams.delete(await self.get_exam(owner_id, exam_id))

    async def _select_questions(self, owner_id: str, data: ExamIn) -> list[str]:
        if data.random is not None:
            category_ids = set(data.random.category_ids)
            in_subject = await self.categories.query.where(
                Category.id.in_(category_ids),
                Category.subject_id == data.subject_id,
            ).count()
            require(
                in_subject == len(category_ids),
                "Choose categories of the exam's subject",
            )
            pool = await self.questions.ids_in_categories(
                owner_id, data.subject_id, list(category_ids)
            )
            require(
                data.random.count <= len(pool),
                "Not enough questions in the selected categories",
            )
            return random.SystemRandom().sample(pool, data.random.count)
        owned = await self.questions.query.where(
            Question.id.in_(data.question_ids),
            Question.owner_id == owner_id,
            Question.subject_id == data.subject_id,
        ).count()
        require(
            owned == len(data.question_ids),
            "Select only questions of the exam's subject",
        )
        return data.question_ids

    @staticmethod
    def _fill_exam(exam: Exam, data: ExamSettingsIn) -> Exam:
        exam.subject_id = data.subject_id
        exam.title = data.title
        exam.available_from = to_utc_iso(data.available_from)
        exam.available_until = to_utc_iso(data.available_until)
        exam.pass_percentage = data.pass_percentage
        return exam

    @staticmethod
    def _exam_out(exam: Exam, question_ids: list[str]) -> dict[str, Any]:
        return {
            "id": exam.id,
            "subject_id": exam.subject_id,
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

    async def admin_clean_subject(self, record, values, creating):
        owner_id = await self._admin_owner(record, values, creating)
        data = SubjectIn(
            name=values.get("name") or "",
            description=values.get("description") or "",
        )
        await self._check_subject_name(owner_id, data.name, record.id)
        values.update(name=data.name, description=data.description)
        return values

    async def admin_clean_category(self, record, values, creating):
        owner_id = await self._admin_owner(record, values, creating)
        data = CategoryIn(
            subject_id=values.get("subject_id") or "", name=values.get("name") or ""
        )
        await self._check_subject(owner_id, data.subject_id)
        if not creating:
            await self._check_category_move(record, data.subject_id)
        values.update(subject_id=data.subject_id, name=data.name)
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
            subject_id=values.get("subject_id") or "",
            category_id=values.get("category_id") or "",
            question_text=values.get("question_text") or "",
            answers=[values.get(f"answer_{n}") or "" for n in range(1, 5)],
            correct_answer=values.get("correct_answer"),
            points=values.get("points"),
            image=image,
        )
        await self._check_placement(owner_id, data.subject_id, data.category_id)
        if not creating:
            await self._check_question_move(record, data.subject_id)
        values.update(
            subject_id=data.subject_id,
            category_id=data.category_id,
            question_text=data.question_text,
            image=data.image,
            correct_answer=data.correct_answer,
            points=data.points,
            **{f"answer_{n}": answer for n, answer in enumerate(data.answers, start=1)},
        )
        return values

    async def admin_clean_exam(self, record, values, creating):
        owner_id = await self._admin_owner(record, values, creating)
        data = ExamSettingsIn(
            subject_id=values.get("subject_id") or "",
            title=values.get("title") or "",
            available_from=values.get("available_from"),
            available_until=values.get("available_until"),
            pass_percentage=values.get("pass_percentage"),
        )
        await self._check_subject(owner_id, data.subject_id)
        require(
            creating
            or data.subject_id == record.subject_id
            or not await self.exam_questions.exists(exam_id=record.id),
            "Remove the exam's questions before changing its subject",
            Conflict,
        )
        values.update(
            subject_id=data.subject_id,
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
            exam.subject_id == question.subject_id,
            "The question must belong to the exam's subject",
        )
        values["subject_id"] = exam.subject_id
        position = values.get("position")
        if not isinstance(position, int) or position < 0:
            raise ExamError("Position must be a non-negative number")
        return values
