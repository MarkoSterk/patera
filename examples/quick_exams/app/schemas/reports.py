from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .accounts import UserOut
from .attempts import ResultOut


class ArchivedQuestionOut(BaseModel):
    id: str = Field(validation_alias="source_question_id")
    question_text: str
    image: str
    answers: list[str]
    points: float
    correct_answer: int
    selected_answer: Optional[int]


class ArchivedAttemptOut(BaseModel):
    id: str
    student_email: str
    started_at: str
    submitted_at: str
    pass_percentage: float
    result: ResultOut
    questions: list[ArchivedQuestionOut]


class ReportOut(BaseModel):
    exam_id: str
    exam_title: str
    count: int
    pass_rate: float
    average: float
    lowest: float
    highest: float
    attempts: list[ArchivedAttemptOut]


class CountsOut(BaseModel):
    questions: int
    exams: int
    attempts: int


class AdminOverviewOut(BaseModel):
    users: list[UserOut]
    counts: CountsOut
    reports: list[ReportOut]
