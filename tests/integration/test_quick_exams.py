"""
Runs the Quick Exams example (examples/quick_exams) as a real application:
patera-auth with JWT access tokens, patera-database repositories and
@transactional request sessions, patera-migrate, patera-admin and the CLI.

The example has its own, more detailed suite in examples/quick_exams/tests;
this module checks the framework integration points it relies on.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

from patera.testing import PateraTestClient

pytestmark = pytest.mark.integration

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "quick_exams"
SECRET = "integration-test-secret-key-long-enough-for-hs256"
PASSWORD = "long-password-123"


def _forget_example_modules() -> None:
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]


@pytest.fixture(scope="module", autouse=True)
def example_package():
    """
    Imports the example's ``app`` package once for this module: its ORM
    models register in the shared declarative metadata, which allows each
    table to be defined once. Settings are read per App instance, so every
    test still gets its own database.
    """
    sys.path.insert(0, str(EXAMPLE_DIR))
    _forget_example_modules()
    yield
    _forget_example_modules()
    sys.path.remove(str(EXAMPLE_DIR))


@pytest.fixture
def database(monkeypatch, tmp_path) -> Path:
    path = tmp_path / "exams.sqlite3"
    monkeypatch.setenv("PATERA_SECRET_KEY", SECRET)
    monkeypatch.setenv(
        "PATERA_EXAMS_DB__DATABASE_URI", f"sqlite+aiosqlite:///{path.as_posix()}"
    )
    monkeypatch.setenv("PATERA_LOG_FILES__PATH", str(tmp_path / "logs" / "app.jsonl"))
    monkeypatch.setenv("PATERA_STARTUP_BANNER", "false")
    return path


@pytest.fixture
def cli_app(database):
    from app import App  # type: ignore[import-not-found]

    application = App(cli_mode=True)
    yield application
    application._remove_logger_sinks()


@pytest.fixture
def create_user(cli_app, monkeypatch):
    from app.cli import users_cli  # type: ignore[import-not-found]

    def create(email: str, role: str = "instructor", password: str = PASSWORD) -> None:
        monkeypatch.setattr(users_cli, "getpass", lambda _prompt: password)
        cli_app.run_cli("users:create", command_args=[email, role])

    return create


@pytest.fixture
def exams_app(cli_app, create_user):
    cli_app.run_cli("migrate:migrate")
    cli_app.run_cli("migrate:validate")
    create_user("teacher@example.com", "both")
    create_user("other@example.com", "instructor")

    from app import App  # type: ignore[import-not-found]

    application = App()
    yield application
    application._remove_logger_sinks()


@pytest.fixture
def db(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def window(hours_from: float = -1, hours_until: float = 1) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "available_from": (now + timedelta(hours=hours_from)).isoformat(),
        "available_until": (now + timedelta(hours=hours_until)).isoformat(),
    }


def question_body(category: dict, **changes) -> dict:
    return {
        "subject_id": category["subject_id"],
        "category_id": category["id"],
        "question_text": "2 + 2?",
        "answers": ["3", "4", "5", "6"],
        "correct_answer": 1,
        "points": 3,
        **changes,
    }


async def login(
    client, email: str = "teacher@example.com", password: str = PASSWORD
) -> dict:
    res = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": "Bearer " + res.json()["token"]}


async def call(client, headers, method, path, expected=200, **kwargs):
    res = await client.request(method, path, headers=headers, **kwargs)
    assert res.status_code == expected, res.text
    return res.json() if res.content else None


async def test_jwt_authentication_and_role_decorators(exams_app):
    async with PateraTestClient(exams_app) as client:
        res = await client.post(
            "/api/auth/login",
            json={"email": "teacher@example.com", "password": PASSWORD},
        )
        token = res.json()["token"]
        assert jwt.decode(token, SECRET, algorithms=["HS256"])["ver"] == 0
        cookie = res.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie

        # Cookie for the browser, bearer token for API clients.
        assert (await client.get("/api/auth/me")).json()["roles"] == [
            "INSTRUCTOR",
            "ADMIN",
        ]
        client.client.cookies.clear()
        assert (await client.get("/api/auth/me")).status_code == 401
        bearer = {"Authorization": f"Bearer {token}"}
        assert (await client.get("/api/auth/me", headers=bearer)).status_code == 200

        user_id = jwt.decode(token, SECRET, algorithms=["HS256"])["sub"]
        expired = jwt.encode(
            {
                "sub": user_id,
                "ver": 0,
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            SECRET,
            algorithm="HS256",
        )
        forged = jwt.encode(
            {"sub": user_id, "ver": 0}, "wrong-secret-" * 4, algorithm="HS256"
        )
        for bad in (expired, forged):
            res = await client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {bad}"}
            )
            assert res.status_code == 401

        # @role_required on controllers: 401 without a token, 403 without the role.
        assert (await client.get("/api/categories/")).status_code == 401
        other = await login(client, "other@example.com")
        client.client.cookies.clear()
        await call(client, other, "GET", "/api/categories/")
        await call(client, other, "GET", "/api/admin/overview", 403)

        # A new password increments the token version: earlier tokens stop working.
        users = (await call(client, bearer, "GET", "/api/admin/overview"))["users"]
        other_id = next(u["id"] for u in users if u["email"] == "other@example.com")
        await call(
            client,
            bearer,
            "PUT",
            f"/api/admin/users/{other_id}",
            json={
                "email": "other@example.com",
                "password": "brand-new-password",
                "roles": ["INSTRUCTOR"],
            },
        )
        assert (await client.get("/api/auth/me", headers=other)).status_code == 401


async def test_transactional_writes_and_listings(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        teacher = await login(client)
        other = await login(client, "other@example.com")
        client.client.cookies.clear()

        subject = await call(
            client, teacher, "POST", "/api/subjects/", 201, json={"name": "Maths"}
        )
        category = await call(
            client,
            teacher,
            "POST",
            "/api/categories/",
            201,
            json={"subject_id": subject["id"], "name": "Arithmetic"},
        )
        question = await call(
            client,
            teacher,
            "POST",
            "/api/questions/",
            201,
            json=question_body(category),
        )

        # Records loaded in a request that ends with the defensive rollback.
        assert await call(client, teacher, "GET", "/api/subjects/") == [subject]
        assert await call(client, teacher, "GET", "/api/categories/") == [category]
        assert await call(client, teacher, "GET", "/api/questions/") == [question]

        # A failing @transactional request leaves nothing behind.
        await call(
            client,
            teacher,
            "POST",
            "/api/exams/",
            400,
            json={
                "subject_id": subject["id"],
                "title": "Too many",
                **window(),
                "random": {"category_ids": [category["id"]], "count": 5},
            },
        )
        assert db.execute("SELECT COUNT(*) FROM exams").fetchone()[0] == 0
        await call(
            client,
            teacher,
            "POST",
            "/api/questions/",
            422,
            json=question_body(category, correct_answer=4),
        )

        exam = await call(
            client,
            teacher,
            "POST",
            "/api/exams/",
            201,
            json={
                "subject_id": subject["id"],
                "title": "Quiz",
                **window(),
                "question_ids": [question["id"]],
            },
        )
        assert await call(client, teacher, "GET", "/api/exams/") == [exam]
        assert (
            db.execute("SELECT question_id FROM exam_questions").fetchone()[0]
            == question["id"]
        )

        # Records are scoped to their owner.
        assert await call(client, other, "GET", "/api/exams/") == []
        await call(client, other, "DELETE", f"/api/exams/{exam['id']}", 404)
        await call(client, teacher, "DELETE", f"/api/categories/{category['id']}", 409)
        await call(client, teacher, "DELETE", f"/api/subjects/{subject['id']}", 409)

        # Cross-site writes and other content types are refused.
        res = await client.post(
            "/api/categories/",
            json={"name": "X"},
            headers={**teacher, "Origin": "https://evil.example"},
        )
        assert res.status_code == 403
        res = await client.post(
            "/api/categories/",
            content='{"name": "X"}',
            headers={**teacher, "Content-Type": "text/plain"},
        )
        assert res.status_code == 415


async def test_student_attempts_keep_an_independent_archive(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        teacher = await login(client)
        client.client.cookies.clear()
        subject = await call(
            client, teacher, "POST", "/api/subjects/", 201, json={"name": "Maths"}
        )
        category = await call(
            client,
            teacher,
            "POST",
            "/api/categories/",
            201,
            json={"subject_id": subject["id"], "name": "Math"},
        )
        question = await call(
            client,
            teacher,
            "POST",
            "/api/questions/",
            201,
            json=question_body(category),
        )
        exam = await call(
            client,
            teacher,
            "POST",
            "/api/exams/",
            201,
            json={
                "subject_id": subject["id"],
                "title": "Quiz",
                **window(),
                "random": {"category_ids": [category["id"]], "count": 1},
            },
        )
        qr = await client.get(f"/api/exams/{exam['id']}/qr", headers=teacher)
        assert qr.status_code == 200 and "<svg" in qr.text

        res = await client.post(
            "/api/attempts/",
            json={"exam_id": exam["id"], "email": "Student@Example.com"},
        )
        assert res.status_code == 201, res.text
        assert "correct" not in res.text and "owner" not in res.text
        attempt = res.json()

        # Edits after the start do not change the started attempt.
        await call(
            client,
            teacher,
            "PUT",
            f"/api/questions/{question['id']}",
            json=question_body(category, question_text="Changed", correct_answer=0),
        )
        submit = f"/api/attempts/{attempt['id']}/submit"
        result = (
            await client.post(submit, json={"answers": {question["id"]: 1}})
        ).json()
        assert result == {"points": 3, "maximum": 3, "percentage": 100, "passed": True}
        assert (
            await client.post(submit, json={"answers": {question["id"]: 0}})
        ).json() == result
        assert (
            await client.post("/api/attempts/guessed/submit", json={"answers": {}})
        ).status_code == 404

        await call(client, teacher, "DELETE", f"/api/exams/{exam['id']}", 204)
        await call(client, teacher, "DELETE", f"/api/questions/{question['id']}", 204)
        reports = await call(client, teacher, "GET", "/api/reports/")
        archived = reports[0]["attempts"][0]
        assert archived["student_email"] == "student@example.com"
        assert archived["questions"][0]["question_text"] == "2 + 2?"
        assert archived["questions"][0]["selected_answer"] == 1

        late = await client.post(
            "/api/attempts/", json={"exam_id": "missing", "email": "s@example.com"}
        )
        assert late.status_code == 404


async def test_admin_uses_the_application_authentication(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        res = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert res.status_code == 303
        assert (await client.get("/admin/en/")).status_code == 200  # Admin sign-in page

        # Admin's sign-in form posts to the configured login endpoint.
        await login(client)
        assert (await client.get("/admin/en/dashboard")).status_code == 200

        async def form(method, path, data):
            return await client.request(
                method, path, files={k: (None, str(v)) for k, v in data.items()}
            )

        base = "/admin/en/databases/exams/model/"
        for model in (
            "User",
            "Subject",
            "Category",
            "Question",
            "Exam",
            "ExamQuestion",
            "Attempt",
            "AttemptQuestion",
        ):
            assert (await client.get(base + model)).status_code == 200, model

        owner = db.execute(
            "SELECT id FROM users WHERE email='teacher@example.com'"
        ).fetchone()[0]
        other = db.execute(
            "SELECT id FROM users WHERE email='other@example.com'"
        ).fetchone()[0]
        assert (
            await form(
                "POST", base + "Subject/create", {"owner_id": owner, "name": "Sky"}
            )
        ).status_code == 303
        subject = db.execute("SELECT id FROM subjects").fetchone()[0]
        assert (
            await form(
                "POST",
                base + "Category/create",
                {"owner_id": owner, "subject_id": subject, "name": " Planets "},
            )
        ).status_code == 303
        category = db.execute("SELECT id, name FROM categories").fetchone()
        assert category["name"] == "Planets"

        # Model hooks apply the application's rules to Admin forms.
        question = {
            "owner_id": other,
            "subject_id": subject,
            "category_id": category["id"],
            "question_text": "Red planet?",
            "answer_1": "Mars",
            "answer_2": "Venus",
            "answer_3": "Earth",
            "answer_4": "Jupiter",
            "correct_answer": "0",
            "points": "2",
            "image": "",
        }
        assert (
            await form("POST", base + "Question/create", question)
        ).status_code == 422
        assert (
            await form(
                "POST", base + "Question/create", {**question, "owner_id": owner}
            )
        ).status_code == 303

        user = {
            "email": "native@example.com",
            "password": "native-password-123",
            "is_instructor": "on",
        }
        assert (await form("POST", base + "User/create", user)).status_code == 303
        stored = db.execute(
            "SELECT password_hash FROM users WHERE email='native@example.com'"
        ).fetchone()[0]
        assert stored.startswith("bcrypt-sha256$")

        # Hooks refuse deletions with a reason Admin shows (422).
        res = await client.delete(base + "User/pk/id/" + owner)
        assert res.status_code == 422
        assert res.json()["message"] == "Keep at least one admin"
        res = await client.get(base + "Session")
        assert res.status_code == 404 and "Unknown database or model" in res.text

        # Admin's logout button fetches the configured logout endpoint.
        assert (await client.get("/api/auth/logout")).status_code == 204
        res = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert res.headers["location"] == "/admin/en/"

        # An instructor without ADMIN is signed in but not allowed in.
        await login(client, "native@example.com", "native-password-123")
        res = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert res.headers["location"] == "/admin/en/unauthorized"


def test_cli_session_and_migrations(exams_app, create_user, db):
    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"users", "subjects", "questions", "attempts", "pyway_migrations"} <= tables
    assert "sessions" not in tables  # removed by V1_1

    create_user("admin@example.com", "admin")
    row = db.execute(
        "SELECT is_instructor, is_admin, token_version FROM users WHERE email='admin@example.com'"
    ).fetchone()
    assert tuple(row) == (0, 1, 0)
    with pytest.raises(SystemExit):
        create_user("admin@example.com", "admin")
    with pytest.raises(SystemExit):
        create_user("someone@example.com", "student")
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
