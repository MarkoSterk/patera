"""Transactional SQLite storage. Attempt snapshots are independent of live content."""

import json
import os
import random
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def database_path():
    return os.environ.get(
        "QUICK_EXAMS_DB", str(Path(__file__).parents[1] / "exams.sqlite3")
    )


@contextmanager
def database():
    path = database_path()
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.execute(
            "CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, body TEXT, PRIMARY KEY(kind,id))"
        )
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def all_records(db, kind):
    return [
        json.loads(r[0])
        for r in db.execute("SELECT body FROM records WHERE kind=?", (kind,))
    ]


def get(db, kind, key):
    row = db.execute(
        "SELECT body FROM records WHERE kind=? AND id=?", (kind, key)
    ).fetchone()
    require(row is not None, "Record not found")
    return json.loads(row[0])


def save(db, kind, value):
    value.setdefault("id", secrets.token_urlsafe(24))
    db.execute(
        "INSERT OR REPLACE INTO records VALUES (?,?,?)",
        (kind, value["id"], json.dumps(value)),
    )
    return value


def remove(db, kind, key):
    db.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, key))


def user_save(db, data):
    email = email_value(data.get("email", ""))
    roles = data.get("roles", [])
    require(
        isinstance(roles, list) and set(roles) <= {"ADMIN", "INSTRUCTOR"},
        "Invalid roles",
    )
    old = get(db, "user", data["id"]) if data.get("id") else {}
    require(
        not any(
            u["email"] == email and u["id"] != old.get("id")
            for u in all_records(db, "user")
        ),
        "Email already exists",
    )
    if "ADMIN" in old.get("roles", []) and "ADMIN" not in roles:
        require(
            sum("ADMIN" in u["roles"] for u in all_records(db, "user")) > 1,
            "Keep at least one admin",
        )
    password = data.get("password", "")
    require(old or len(password) >= 12, "Use a password of at least 12 characters")
    if password:
        require(len(password) >= 12, "Use a password of at least 12 characters")
        old["password"] = generate_password_hash(password)
        for session in all_records(db, "session"):
            if session["user"] == old.get("id"):
                remove(db, "session", session["id"])
    old.update(email=email, roles=roles)
    return save(db, "user", old)


def email_value(value):
    require(
        isinstance(value, str)
        and len(value) <= 254
        and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()),
        "Enter a valid email address",
    )
    return value.strip().lower()


def login(db, data):
    user = next(
        (
            u
            for u in all_records(db, "user")
            if u["email"] == str(data.get("email", "")).strip().lower()
        ),
        None,
    )
    require(
        user and check_password_hash(user["password"], data.get("password", "")),
        "Invalid credentials",
    )
    return save(db, "session", {"user": user["id"], "created": now()})["id"]


def question_save(db, data, owner):
    title = str(data.get("question", "")).strip()
    answers = data.get("answers")
    require(
        title and len(title) <= 5000,
        "Question text is required (maximum 5000 characters)",
    )
    require(
        isinstance(answers, list)
        and len(answers) == 4
        and all(isinstance(a, str) and a.strip() and len(a) <= 2000 for a in answers),
        "Provide exactly four answers",
    )
    correct = data.get("correct")
    require(type(correct) is int and 0 <= correct < 4, "Select one correct answer")
    points = data.get("points", 1)
    require(
        type(points) in (int, float) and 0 < points <= 100000,
        "Points must be positive and at most 100000",
    )
    category = get(db, "category", data.get("category", ""))
    require(category["owner"] == owner, "Invalid category")
    image = data.get("image", "")
    require(
        isinstance(image, str)
        and (
            not image
            or (
                len(image) <= 2800000
                and re.fullmatch(
                    r"data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+", image
                )
            )
        ),
        "Use a PNG, JPEG, GIF or WebP image under 2 MB",
    )
    return save(
        db,
        "question",
        {
            **({"id": data["id"]} if data.get("id") else {}),
            "owner": owner,
            "question": title,
            "answers": answers,
            "correct": correct,
            "points": points,
            "category": category["id"],
            "image": image,
        },
    )


def exam_save(db, data, owner):
    title = str(data.get("title", "")).strip()
    require(
        title and len(title) <= 200, "Exam title is required (maximum 200 characters)"
    )
    start, end = (datetime.fromisoformat(data.get(k, "")) for k in ("from", "to"))
    require(
        start.tzinfo and end.tzinfo and start < end,
        "Provide an end after the start, including timezone",
    )
    threshold = data.get("pass", 50)
    require(
        type(threshold) in (int, float) and 0 <= threshold <= 100,
        "Pass percentage must be between 0 and 100",
    )
    ids = data.get("questions", [])
    if data.get("random"):
        count = data.get("count", 10)
        pool = [
            q["id"]
            for q in all_records(db, "question")
            if q["owner"] == owner and q["category"] in data.get("categories", [])
        ]
        require(
            type(count) is int and 1 <= count <= len(pool),
            "Not enough questions in the selected categories",
        )
        ids = random.SystemRandom().sample(pool, count)
    require(
        isinstance(ids, list) and ids and len(ids) == len(set(ids)),
        "Select distinct questions",
    )
    for key in ids:
        require(get(db, "question", key)["owner"] == owner, "Invalid question")
    return save(
        db,
        "exam",
        {
            **({"id": data["id"]} if data.get("id") else {}),
            "owner": owner,
            "title": title,
            "from": start.astimezone(timezone.utc).isoformat(),
            "to": end.astimezone(timezone.utc).isoformat(),
            "pass": threshold,
            "questions": ids,
        },
    )


def available(exam):
    require(
        exam["from"] <= now() < exam["to"],
        "This exam is outside its availability window",
    )


def start_attempt(db, exam_id, email):
    exam = get(db, "exam", exam_id)
    available(exam)
    snapshot = {
        **exam,
        "questions": [get(db, "question", key) for key in exam["questions"]],
    }
    return save(
        db,
        "attempt",
        {
            "exam": exam_id,
            "owner": exam["owner"],
            "email": email_value(email),
            "started": now(),
            "snapshot": snapshot,
        },
    )


def public_attempt(attempt):
    exam = attempt["snapshot"]
    return {
        "id": attempt["id"],
        "title": exam["title"],
        "to": exam["to"],
        "questions": [
            {k: q[k] for k in ("id", "question", "image", "answers", "points")}
            for q in exam["questions"]
        ],
    }


def submit(db, token, answers):
    attempt = get(db, "attempt", token)
    if "result" in attempt:
        return attempt["result"]
    exam = attempt["snapshot"]
    available(exam)
    require(
        isinstance(answers, dict)
        and set(answers) == {q["id"] for q in exam["questions"]},
        "Answer every question",
    )
    require(
        all(type(a) is int and 0 <= a < 4 for a in answers.values()),
        "Select exactly one answer per question",
    )
    maximum = sum(q["points"] for q in exam["questions"])
    points = sum(
        q["points"] for q in exam["questions"] if answers[q["id"]] == q["correct"]
    )
    percentage = points / maximum * 100
    attempt.update(
        answers=answers,
        submitted=now(),
        result={
            "points": points,
            "maximum": maximum,
            "percentage": percentage,
            "passed": percentage >= exam["pass"],
        },
    )
    save(db, "attempt", attempt)
    return attempt["result"]


def reports(db, owner=None):
    attempts = [
        a
        for a in all_records(db, "attempt")
        if "result" in a and (owner is None or a["owner"] == owner)
    ]
    grouped = {}
    for attempt in attempts:
        report = grouped.setdefault(
            attempt["exam"],
            {
                "exam": attempt["exam"],
                "title": attempt["snapshot"]["title"],
                "attempts": [],
            },
        )
        report["attempts"].append(attempt)
    for report in grouped.values():
        results = [a["result"] for a in report["attempts"]]
        report.update(
            count=len(results),
            pass_rate=100 * sum(r["passed"] for r in results) / len(results),
            average=sum(r["percentage"] for r in results) / len(results),
            lowest=min(r["percentage"] for r in results),
            highest=max(r["percentage"] for r in results),
        )
    return list(grouped.values())
