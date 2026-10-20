"""Exercise the example through real Patera routing, including privacy boundaries."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from patera.testing import PateraTestClient


@pytest.mark.parametrize(
    "role,expected",
    [
        ("instructor", ["INSTRUCTOR"]),
        ("ADMIN", ["ADMIN"]),
        ("both", ["INSTRUCTOR", "ADMIN"]),
    ],
)
def test_user_cli(exams_app, monkeypatch, role, expected):
    from app import App
    from app.cli import users_cli

    _, store = exams_app
    monkeypatch.setattr(users_cli, "getpass", lambda _: "test-password-123")
    cli_app = App(cli_mode=True)
    try:
        cli_app.run_cli("users:create", command_args=["new@example.com", role])
        with store.database() as db:
            user = next(
                u
                for u in store.all_records(db, "user")
                if u["email"] == "new@example.com"
            )
            assert user["roles"] == expected
            assert user["password"] != "test-password-123"
        with pytest.raises(SystemExit):
            cli_app.run_cli("users:create", command_args=["new@example.com", role])
        with pytest.raises(SystemExit):
            cli_app.run_cli(
                "users:create", command_args=["invalid@example.com", "student"]
            )
        passwords = iter(["test-password-123", "different-password"])
        monkeypatch.setattr(users_cli, "getpass", lambda _: next(passwords))
        with pytest.raises(SystemExit):
            cli_app.run_cli("users:create", command_args=["mismatch@example.com"])
        with store.database() as db:
            assert len(store.all_records(db, "user")) == 3
    finally:
        cli_app._remove_logger_sinks()


async def test_native_admin_access_and_sessions(exams_app):
    app, store = exams_app
    async with PateraTestClient(app) as client:
        response = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert (await client.get("/admin/en/")).status_code == 200
        credentials = {"email": "teacher@example.com", "password": "long-password-123"}
        response = await client.post("/admin/login", json=credentials)
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=Strict" in response.headers["set-cookie"]
        dashboard = await client.get("/admin/en/dashboard")
        assert dashboard.status_code == 200
        assert "Users &amp; reports" in dashboard.text
        assert (await client.post("/api/admin", json={})).status_code == 200
        assert (
            await client.post(
                "/api/admin", json={}, headers={"Origin": "https://other.example"}
            )
        ).status_code == 403
        assert (
            await client.post(
                "/api/admin", content="{}", headers={"Content-Type": "text/plain"}
            )
        ).status_code == 415
        # Current roles, rather than roles cached at login, control extension access.
        with store.database() as db:
            user = next(
                u
                for u in store.all_records(db, "user")
                if u["email"] == credentials["email"]
            )
            user["roles"] = ["INSTRUCTOR"]
            store.save(db, "user", user)
        assert (
            await client.get("/admin/en/dashboard", follow_redirects=False)
        ).headers["location"] == "/admin/en/unauthorized"
        await client.get("/admin/logout", follow_redirects=False)
        assert (await client.post("/api/state", json={})).status_code == 401
        assert (await client.post("/admin/login", json=credentials)).status_code == 401
        response = await client.post("/api/login", json=credentials)
        token = response.json()["token"]
        assert (
            await client.get("/admin/en/dashboard", follow_redirects=False)
        ).headers["location"] == "/admin/en/unauthorized"
        with store.database() as db:
            session = store.get(db, "session", token)
            session["created"] = (
                datetime.now(timezone.utc) - timedelta(hours=9)
            ).isoformat()
            store.save(db, "session", session)
        assert (
            await client.get("/admin/en/dashboard", follow_redirects=False)
        ).status_code == 303


@pytest.fixture
def exams_app(monkeypatch, tmp_path):
    monkeypatch.setenv("QUICK_EXAMS_DB", str(tmp_path / "exam.sqlite3"))
    monkeypatch.setenv("PATERA_LOG_FILES__PATH", str(tmp_path / "app.jsonl"))
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "examples/quick_exams")
    )
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            monkeypatch.delitem(sys.modules, name)
    from app import App, store

    with store.database() as db:
        store.user_save(
            db,
            {
                "email": "teacher@example.com",
                "password": "long-password-123",
                "roles": ["INSTRUCTOR", "ADMIN"],
            },
        )
        store.user_save(
            db,
            {
                "email": "other@example.com",
                "password": "long-password-123",
                "roles": ["INSTRUCTOR"],
            },
        )
    app = App()
    yield app, store
    app._remove_logger_sinks()
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


async def test_exam_workflow_and_privacy(exams_app):
    app, store = exams_app
    async with PateraTestClient(app) as client:
        assert (await client.get("/")).status_code == 200
        response = await client.post(
            "/api/login",
            json={"email": "teacher@example.com", "password": "long-password-123"},
        )
        assert response.status_code == 200, response.text
        headers = {"Authorization": "Bearer " + response.json()["token"]}

        async def call(action, payload):
            response = await client.post(
                "/api/" + action, json=payload, headers=headers
            )
            assert response.status_code == 200, response.text
            return response.json()

        category = await call("save", {"kind": "category", "name": "Arithmetic"})
        question = await call(
            "save",
            {
                "kind": "question",
                "question": "2 + 2?",
                "answers": ["3", "4", "5", "6"],
                "correct": 1,
                "points": 3,
                "category": category["id"],
            },
        )
        now = datetime.now(timezone.utc)
        exam = await call(
            "save",
            {
                "kind": "exam",
                "title": "Quiz",
                "from": (now - timedelta(hours=1)).isoformat(),
                "to": (now + timedelta(hours=1)).isoformat(),
                "random": True,
                "count": 1,
                "categories": [category["id"]],
            },
        )
        assert (await client.get("/exam/" + exam["id"])).status_code == 200
        qr = await client.get("/api/qr/" + exam["id"])
        assert qr.status_code == 200
        assert "image/svg+xml" in qr.headers["content-type"]
        assert "<svg" in qr.text
        client.client.cookies.clear()
        assert (await client.post("/api/state", json={})).status_code == 401
        other = (
            await client.post(
                "/api/login",
                json={"email": "other@example.com", "password": "long-password-123"},
            )
        ).json()
        other_headers = {"Authorization": "Bearer " + other["token"]}
        assert (
            await client.post(
                "/api/delete",
                json={"kind": "exam", "id": exam["id"]},
                headers=other_headers,
            )
        ).status_code == 403
        assert (
            await client.post("/api/admin", json={}, headers=other_headers)
        ).status_code == 403
        attempt = (
            await client.post(
                "/api/start", json={"exam": exam["id"], "email": "student@example.com"}
            )
        ).json()
        assert "correct" not in str(attempt)
        assert "owner" not in str(attempt)
        assert (
            await client.post(
                "/api/submit",
                json={"attempt": attempt["id"], "answers": {question["id"]: [1, 2]}},
            )
        ).status_code == 400
        payload = {"attempt": attempt["id"], "answers": {question["id"]: 1}}
        result = (await client.post("/api/submit", json=payload)).json()
        assert result == {"points": 3, "maximum": 3, "percentage": 100, "passed": True}
        assert (await client.post("/api/submit", json=payload)).json() == result
        assert (
            await client.post("/api/submit", json={**payload, "attempt": "guessed"})
        ).status_code == 400
        await call("delete", {"kind": "exam", "id": exam["id"]})
        await call("delete", {"kind": "question", "id": question["id"]})
        await call("delete", {"kind": "category", "id": category["id"]})
        reports = (await call("state", {}))["reports"]
        assert reports[0]["count"] == 1
        assert reports[0]["attempts"][0]["snapshot"]["questions"][0]["correct"] == 1
        assert (await client.post("/api/state", json={}, headers=other_headers)).json()[
            "reports"
        ] == []


def test_validation_window_and_snapshot(exams_app):
    _, s = exams_app
    with s.database() as db:
        owner = s.all_records(db, "user")[0]["id"]
        category = s.save(db, "category", {"owner": owner, "name": "Science"})
        q = {
            "question": "Original",
            "answers": ["a", "b", "c", "d"],
            "correct": 0,
            "category": category["id"],
        }
        for invalid in (
            {"correct": [0, 1]},
            {"points": 0},
            {"answers": ["a"]},
            {"image": "javascript:alert(1)"},
        ):
            with pytest.raises(ValueError):
                s.question_save(db, {**q, **invalid}, owner)
        question = s.question_save(db, q, owner)
        now = datetime.now(timezone.utc)
        data = {
            "title": "Test",
            "from": (now - timedelta(hours=1)).isoformat(),
            "to": (now + timedelta(hours=1)).isoformat(),
            "questions": [question["id"]],
        }
        with pytest.raises(ValueError):
            s.exam_save(
                db, {**data, "random": True, "categories": [category["id"]]}, owner
            )
        exam = s.exam_save(db, data, owner)
        attempt = s.start_attempt(db, exam["id"], "student@example.com")
        s.question_save(db, {**question, "question": "Changed", "correct": 1}, owner)
        assert (
            s.get(db, "attempt", attempt["id"])["snapshot"]["questions"][0]["question"]
            == "Original"
        )
        assert s.submit(db, attempt["id"], {question["id"]: 0})["passed"]
        closed = s.exam_save(
            db,
            {
                **data,
                "from": (now - timedelta(hours=2)).isoformat(),
                "to": (now - timedelta(hours=1)).isoformat(),
            },
            owner,
        )
        with pytest.raises(ValueError):
            s.start_attempt(db, closed["id"], "student@example.com")
        unfinished = s.start_attempt(db, exam["id"], "late@example.com")
        unfinished["snapshot"]["to"] = (now - timedelta(seconds=1)).isoformat()
        s.save(db, "attempt", unfinished)
        with pytest.raises(ValueError):
            s.submit(db, unfinished["id"], {question["id"]: 0})


def test_weighted_grades_and_admin_safeguard(exams_app):
    _, s = exams_app
    with s.database() as db:
        admin = next(u for u in s.all_records(db, "user") if "ADMIN" in u["roles"])
        with pytest.raises(ValueError):
            s.user_save(db, {"id": admin["id"], "email": admin["email"], "roles": []})
        category = s.save(db, "category", {"owner": admin["id"], "name": "Weighted"})
        questions = [
            s.question_save(
                db,
                {
                    "question": str(points),
                    "answers": ["a", "b", "c", "d"],
                    "correct": 0,
                    "points": points,
                    "category": category["id"],
                },
                admin["id"],
            )
            for points in (1, 3)
        ]
        now = datetime.now(timezone.utc)
        exam = s.exam_save(
            db,
            {
                "title": "Weighted",
                "from": (now - timedelta(hours=1)).isoformat(),
                "to": (now + timedelta(hours=1)).isoformat(),
                "questions": [q["id"] for q in questions],
            },
            admin["id"],
        )
        attempt = s.start_attempt(db, exam["id"], "student@example.com")
        result = s.submit(
            db, attempt["id"], {questions[0]["id"]: 0, questions[1]["id"]: 1}
        )
        assert result == {"points": 1, "maximum": 4, "percentage": 25, "passed": False}
