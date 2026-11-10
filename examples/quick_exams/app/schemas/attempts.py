from __future__ import annotations

from typing import Optional

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


class ReviewedQuestionOut(BaseModel):
    """A submitted question with its answer key and the selected answer."""

    id: str = Field(validation_alias="source_question_id")
    question_text: str
    image: str
    answers: list[str]
    points: float
    correct_answer: int
    selected_answer: Optional[int]


class SubmissionOut(ResultOut):
    """
    The result of a submission. ``questions`` (the review with answer keys)
    is present only in the response to the submission itself; a repeated
    submit returns the result without it.
    """

    questions: Optional[list[ReviewedQuestionOut]] = None
