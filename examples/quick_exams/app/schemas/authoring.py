from __future__ import annotations

from typing import Annotated, Optional

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    Field,
    StrictInt,
    model_validator,
)

from .common import (
    Answer,
    AnswerIndex,
    Description,
    Input,
    Name,
    Percentage,
    Points,
    QuestionText,
    Title,
    validate_image,
)


class SubjectIn(Input):
    name: Name
    description: Description = ""


class SubjectOut(BaseModel):
    id: str
    name: str
    description: str


class CategoryIn(Input):
    subject_id: str
    name: Name


class CategoryOut(BaseModel):
    id: str
    subject_id: str
    name: str


class QuestionIn(Input):
    subject_id: str
    category_id: str
    question_text: QuestionText
    answers: Annotated[list[Answer], Field(min_length=4, max_length=4)]
    correct_answer: AnswerIndex
    points: Points = 1
    image: Annotated[str, AfterValidator(validate_image)] = ""


class QuestionOut(BaseModel):
    id: str
    subject_id: str
    category_id: str
    question_text: str
    answers: list[str]
    correct_answer: int
    points: float
    image: str


class RandomSelection(Input):
    """
    Sample ``count`` distinct questions from the categories, which belong to
    the exam's subject, once, at save time.
    """

    category_ids: Annotated[list[str], Field(min_length=1)]
    count: Annotated[StrictInt, Field(ge=1)] = 10


class ExamSettingsIn(Input):
    subject_id: str
    title: Title
    available_from: AwareDatetime
    available_until: AwareDatetime
    pass_percentage: Percentage = 50

    @model_validator(mode="after")
    def _window(self):
        if self.available_until <= self.available_from:
            raise ValueError("The exam must close after it opens")
        return self


class ExamIn(ExamSettingsIn):
    question_ids: list[str] = []
    random: Optional[RandomSelection] = None

    @model_validator(mode="after")
    def _selection(self):
        if self.random is None:
            if not self.question_ids:
                raise ValueError("Select at least one question")
            if len(set(self.question_ids)) != len(self.question_ids):
                raise ValueError("Select distinct questions")
        return self


class ExamOut(BaseModel):
    id: str
    subject_id: str
    title: str
    available_from: str
    available_until: str
    pass_percentage: float
    question_ids: list[str]
