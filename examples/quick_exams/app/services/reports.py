from __future__ import annotations

from typing import Any, Optional

from patera import Service
from patera.injectable import Inject

from ..repository import AttemptQuestions, Attempts, Exams, Questions
from .attempts import AttemptService


class ReportService(Service):
    attempts: Inject[Attempts]
    attempt_questions: Inject[AttemptQuestions]
    questions: Inject[Questions]
    exams: Inject[Exams]

    async def reports(self, owner_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Submitted attempts grouped by exam: the owner's, or all for administrators."""
        attempts = await self.attempts.submitted(owner_id)
        questions = await self.attempt_questions.for_attempts([a.id for a in attempts])
        grouped: dict[str, list[dict[str, Any]]] = {}
        titles: dict[str, str] = {}
        for attempt in attempts:
            titles.setdefault(attempt.source_exam_id, attempt.exam_title)
            grouped.setdefault(attempt.source_exam_id, []).append(
                {
                    "id": attempt.id,
                    "student_email": attempt.student_email,
                    "started_at": attempt.started_at,
                    "submitted_at": attempt.submitted_at,
                    "pass_percentage": attempt.pass_percentage,
                    "result": AttemptService.result_of(attempt),
                    "questions": questions[attempt.id],
                }
            )
        reports = []
        for exam_id, archived in grouped.items():
            results = [a["result"] for a in archived]
            scores = [r["percentage"] for r in results]
            reports.append(
                {
                    "exam_id": exam_id,
                    "exam_title": titles[exam_id],
                    "count": len(archived),
                    "pass_rate": 100 * sum(r["passed"] for r in results) / len(results),
                    "average": sum(scores) / len(scores),
                    "lowest": min(scores),
                    "highest": max(scores),
                    "attempts": archived,
                }
            )
        return reports

    async def counts(self) -> dict[str, int]:
        return {
            "questions": await self.questions.count(),
            "exams": await self.exams.count(),
            "attempts": await self.attempts.count(),
        }
