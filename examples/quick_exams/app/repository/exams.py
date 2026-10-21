from patera.database.sql import Repository
from sqlalchemy import delete

from ..models import Exam, ExamQuestion


class Exams(Repository[Exam]):
    model = Exam

    async def owned_by(self, owner_id: str) -> list[Exam]:
        return (
            await self.query.filter_by(owner_id=owner_id)
            .order_by(Exam.available_from.desc())
            .all()
        )


class ExamQuestions(Repository[ExamQuestion]):
    model = ExamQuestion

    async def for_exams(self, exam_ids: list[str]) -> dict[str, list[str]]:
        selected: dict[str, list[str]] = {exam_id: [] for exam_id in exam_ids}
        if not exam_ids:
            return selected
        rows = (
            await self.query.where(ExamQuestion.exam_id.in_(exam_ids))
            .order_by(ExamQuestion.exam_id, ExamQuestion.position)
            .all()
        )
        for row in rows:
            selected[row.exam_id].append(row.question_id)
        return selected

    async def clear(self, exam_id: str) -> None:
        await self.session.execute(
            delete(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
        )
        await self.flush()

    async def add_selection(
        self, exam_id: str, subject_id: str, question_ids: list[str]
    ) -> None:
        self.add_all(
            [
                ExamQuestion(
                    exam_id=exam_id,
                    subject_id=subject_id,
                    question_id=question_id,
                    position=position,
                )
                for position, question_id in enumerate(question_ids)
            ]
        )
        await self.flush()
