from __future__ import annotations

from pydantic import BaseModel, Field

from .common import AnswerIndex, Email, Input


class StartAttemptIn(Input):
    exam_id: str
    email: Email


class PublicQuestionOut(BaseModel):
    """A question as a student sees it: no answer key."""

    id: str = Field(validation_alias="source_question_id")
    question_text: str
    image: str
    answers: list[str]
    points: float


class PublicAttemptOut(BaseModel):
    id: str
    exam_title: str
    available_until: str
    questions: list[PublicQuestionOut]


class SubmitIn(Input):
    answers: dict[str, AnswerIndex]


class ResultOut(BaseModel):
    points: float
    maximum: float
    percentage: float
    passed: bool
