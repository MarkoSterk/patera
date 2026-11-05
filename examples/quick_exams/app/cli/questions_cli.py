import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.configs import APP_DIR
from app.errors import require
from app.schemas import (
    CategoryIn,
    QuestionIn,
    SubjectIn,
    image_data_url,
    normalize_email,
)
from app.services.authoring import AuthoringService
from patera.database.sql import cli_session

from patera.cli import CLIController, cli_controller, command
from patera.injectable import Inject

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases

DEFAULT_BANK = APP_DIR.parent / "data" / "biomehanika" / "questions.json"


@dataclass
class QuestionBank:
    """A question bank file: one subject, its categories and questions."""

    subject_name: str
    subject_description: str
    categories: dict[str, str]  # key -> category name
    questions: list[dict[str, Any]]  # each with an "image" data URL or ""

    @classmethod
    def load(cls, path: Path) -> "QuestionBank":
        """
        Reads and checks the file before the database is touched. Image paths
        are relative to the file and become data URLs, as uploads do.
        """
        require(path.is_file(), f"Question bank not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        subject = data.get("subject") or {}
        categories = {c["key"]: c["name"] for c in data.get("categories", [])}
        require(subject.get("name"), "The bank must name its subject")
        require(categories, "The bank must declare at least one category")
        questions = []
        for number, question in enumerate(data.get("questions", []), start=1):
            require(
                question.get("category") in categories,
                f"Question {number} uses an undeclared category "
                f"{question.get('category')!r}",
            )
            image = question.get("image") or ""
            if image:
                image_path = path.parent / image
                require(image_path.is_file(), f"Question {number}: missing {image}")
                image = image_data_url(image_path.read_bytes())
            questions.append({**question, "image": image})
        require(questions, "The bank contains no questions")
        return cls(
            subject_name=subject["name"],
            subject_description=subject.get("description", ""),
            categories=categories,
            questions=questions,
        )


@cli_controller(name="questions")
class QuestionsCLI(CLIController["App"]):
    authoring: Inject[AuthoringService]

    @command(
        "import",
        help=(
            "Import a question bank for an instructor: EMAIL [PATH]; "
            "PATH defaults to data/biomehanika/questions.json"
        ),
    )
    @cli_session("exams")
    async def import_questions(self, email: str, path: str = "") -> None:
        bank = QuestionBank.load(Path(path) if path else DEFAULT_BANK)
        authoring = self.authoring

        user = await authoring.users.first_by(email=normalize_email(email))
        require(user is not None, f"No user with email {email}")
        require(user.is_instructor, f"{user.email} is not an instructor")

        subject = await authoring.subjects.first_by(
            owner_id=user.id, name=bank.subject_name
        )
        if subject is None:
            subject = await authoring.create_subject(
                user.id,
                SubjectIn(name=bank.subject_name, description=bank.subject_description),
            )

        category_ids: dict[str, str] = {}
        new_categories = 0
        for key, name in bank.categories.items():
            category = await authoring.categories.first_by(
                owner_id=user.id, subject_id=subject.id, name=name
            )
            if category is None:
                category = await authoring.create_category(
                    user.id, CategoryIn(subject_id=subject.id, name=name)
                )
                new_categories += 1
            category_ids[key] = category.id

        # Questions already in the subject (same text) are skipped, so the
        # import can be repeated after the bank grows.
        created = skipped = 0
        for question in bank.questions:
            data = QuestionIn(
                subject_id=subject.id,
                category_id=category_ids[question["category"]],
                question_text=question["question_text"],
                answers=question["answers"],
                correct_answer=question["correct_answer"],
                points=float(question.get("points", 1)),
                image=question["image"],
            )
            if await authoring.questions.exists(
                owner_id=user.id,
                subject_id=subject.id,
                question_text=data.question_text,
            ):
                skipped += 1
                continue
            await authoring.create_question(user.id, data)
            created += 1

        print(
            f"Imported into {subject.name!r} for {user.email}: "
            f"{created} questions created, {skipped} already present, "
            f"{new_categories} new categories ({len(category_ids)} in the bank)"
        )
