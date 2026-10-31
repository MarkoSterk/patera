from __future__ import annotations

from typing import TYPE_CHECKING, Any

from patera import Service
from patera.injectable import Inject

from ..errors import ExamError, NotFound, require
from ..models import Attempt, AttemptQuestion
from ..repository import AttemptQuestions, Attempts, ExamQuestions, Exams, Questions
from ..schemas import (
    StartAttemptIn,
    SubmitIn,
    from_iso,
    normalize_email,
    to_utc_iso,
    utc_now,
)

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


def _require_open(available_from: str, available_until: str) -> None:
    now = utc_now()
    require(
        from_iso(available_from) <= now < from_iso(available_until),
        "This exam is outside its availability window",
    )


class AttemptService(Service["App"]):
    exams: Inject[Exams]
    exam_questions: Inject[ExamQuestions]
    questions: Inject[Questions]
    attempts: Inject[Attempts]
    attempt_questions: Inject[AttemptQuestions]

    async def start(self, data: StartAttemptIn) -> dict[str, Any]:
        exam = await self.exams.get(data.exam_id)
        require(exam, "Exam not found", NotFound)
        _require_open(exam.available_from, exam.available_until)
        question_ids = (await self.exam_questions.for_exams([exam.id]))[exam.id]
        require(question_ids, "This exam has no questions yet")
        questions = {
            question.id: question
            for question in await self.questions.query.where(
                self.questions.model.id.in_(question_ids)
            ).all()
        }
        attempt = await self.attempts.create_and_flush(
            owner_id=exam.owner_id,
            source_exam_id=exam.id,
            student_email=data.email,
            started_at=to_utc_iso(utc_now()),
            exam_title=exam.title,
            available_from=exam.available_from,
            available_until=exam.available_until,
            pass_percentage=exam.pass_percentage,
        )
        copies = self.attempt_questions.add_all(
            [
                AttemptQuestion(
                    attempt_id=attempt.id,
                    position=position,
                    source_question_id=question.id,
                    source_category_id=question.category_id,
                    question_text=question.question_text,
                    image=question.image,
                    answer_1=question.answer_1,
                    answer_2=question.answer_2,
                    answer_3=question.answer_3,
                    answer_4=question.answer_4,
                    correct_answer=question.correct_answer,
                    points=question.points,
                )
                for position, question in enumerate(
                    questions[key] for key in question_ids
                )
            ]
        )
        await self.attempt_questions.flush()
        return {
            "id": attempt.id,
            "exam_title": attempt.exam_title,
            "available_until": attempt.available_until,
            "questions": copies,
        }

    async def submit(self, attempt_id: str, data: SubmitIn) -> dict[str, Any]:
        """
        Grades an attempt. The attempt id is the student's capability; a
        repeated submission returns the stored result.
        """
        attempt = await self.attempts.get(attempt_id)
        require(attempt, "Attempt not found", NotFound)
        if attempt.submitted_at is not None:
            return self.result_of(attempt)
        _require_open(attempt.available_from, attempt.available_until)
        questions = await self.attempt_questions.for_attempt(attempt.id)
        require(
            set(data.answers) == {q.source_question_id for q in questions},
            "Answer every question",
        )
        maximum = sum(q.points for q in questions)
        earned = 0.0
        for question in questions:
            question.selected_answer = data.answers[question.source_question_id]
            if question.selected_answer == question.correct_answer:
                earned += question.points
        percentage = earned / maximum * 100
        attempt.submitted_at = to_utc_iso(utc_now())
        attempt.earned_points = earned
        attempt.maximum_points = maximum
        attempt.score_percentage = percentage
        attempt.passed = percentage >= attempt.pass_percentage
        await self.attempts.flush()
        return self.result_of(attempt)

    @staticmethod
    def result_of(attempt: Attempt) -> dict[str, Any]:
        return {
            "points": attempt.earned_points or 0,
            "maximum": attempt.maximum_points or 0,
            "percentage": attempt.score_percentage or 0,
            "passed": bool(attempt.passed),
        }

    def admin_clean_attempt(
        self, record: Attempt, values: dict[str, Any], creating: bool
    ) -> dict[str, Any]:
        if creating:
            raise ExamError("Students create attempts by starting exams")
        try:
            email = normalize_email(values.get("student_email") or "")
        except ValueError as exc:
            raise ExamError(str(exc)) from exc
        return {"student_email": email}
