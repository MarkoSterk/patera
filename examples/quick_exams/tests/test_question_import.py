import json
from pathlib import Path

import pytest

BANK = Path(__file__).resolve().parents[1] / "data" / "biomehanika" / "questions.json"


@pytest.fixture
def migrated(cli_app, create_user):
    cli_app.run_cli("migrate:migrate")
    create_user("teacher@example.com", "instructor")
    create_user("admin@example.com", "admin")
    return cli_app


def test_bank_is_well_formed():
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    keys = {category["key"] for category in bank["categories"]}
    assert bank["subject"]["name"] == "Biomehanika"
    for question in bank["questions"]:
        assert question["category"] in keys
        assert len(question["answers"]) == 4
        assert len(set(question["answers"])) == 4
        assert 0 <= question["correct_answer"] <= 3
        if question["image"]:
            assert (BANK.parent / question["image"]).is_file()


def test_import_creates_subject_categories_and_questions(migrated, db, capsys):
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    migrated.run_cli("questions:import", command_args=["Teacher@Example.com"])

    owner = db.execute(
        "SELECT id FROM users WHERE email = 'teacher@example.com'"
    ).fetchone()["id"]
    subject = db.execute(
        "SELECT id FROM subjects WHERE owner_id = ? AND name = 'Biomehanika'", (owner,)
    ).fetchone()
    assert subject is not None
    categories = db.execute(
        "SELECT COUNT(*) FROM categories WHERE subject_id = ?", (subject["id"],)
    ).fetchone()[0]
    rows = db.execute(
        "SELECT question_text, correct_answer, answer_1, answer_2, answer_3, "
        "answer_4, image FROM questions WHERE subject_id = ?",
        (subject["id"],),
    ).fetchall()
    assert categories == len(bank["categories"])
    assert len(rows) == len(bank["questions"])

    by_text = {row["question_text"]: row for row in rows}
    for question in bank["questions"]:
        row = by_text[question["question_text"]]
        stored = [row[f"answer_{n}"] for n in range(1, 5)]
        assert stored == question["answers"]
        assert row["correct_answer"] == question["correct_answer"]
        assert row["image"].startswith("data:image/png;base64,") == bool(
            question["image"]
        )

    # A repeated import adds nothing.
    migrated.run_cli("questions:import", command_args=["teacher@example.com"])
    assert db.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == len(rows)
    assert "0 questions created" in capsys.readouterr().out


def test_import_requires_an_existing_instructor(migrated, db):
    for email in ("nobody@example.com", "admin@example.com"):
        with pytest.raises(SystemExit):
            migrated.run_cli("questions:import", command_args=[email])
    assert db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 0
