from datetime import datetime, timedelta, timezone

import jwt
import pytest
from conftest import PASSWORD, SECRET
from patera.testing import PateraTestClient
from werkzeug.security import generate_password_hash


def window(hours_from: float = -1, hours_until: float = 1) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "available_from": (now + timedelta(hours=hours_from)).isoformat(),
        "available_until": (now + timedelta(hours=hours_until)).isoformat(),
    }


def question_body(category_id: str, **changes) -> dict:
    return {
        "category_id": category_id,
        "question_text": "2 + 2?",
        "answers": ["3", "4", "5", "6"],
        "correct_answer": 1,
        "points": 3,
        **changes,
    }


async def login(client, email="teacher@example.com", password=PASSWORD) -> dict:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


class Api:
    def __init__(self, client, headers):
        self.client, self.headers = client, headers

    async def __call__(self, method, path, expected=200, **kwargs):
        response = await self.client.request(
            method, path, headers=self.headers, **kwargs
        )
        assert response.status_code == expected, response.text
        return response.json() if response.content else None


async def bank(api) -> tuple[dict, dict]:
    category = await api("POST", "/api/categories/", 201, json={"name": "Arithmetic"})
    question = await api(
        "POST", "/api/questions/", 201, json=question_body(category["id"])
    )
    return category, question


async def test_login_issues_jwt_in_body_and_strict_cookie(exams_app):
    async with PateraTestClient(exams_app) as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": " Teacher@Example.com ", "password": PASSWORD},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["token_type"] == "Bearer"
        assert body["user"]["roles"] == ["INSTRUCTOR", "ADMIN"]
        claims = jwt.decode(body["token"], SECRET, algorithms=["HS256"])
        assert claims["ver"] == 0 and "exp" in claims
        cookie = response.headers["set-cookie"]
        assert "quick_exams_token=" in cookie
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
        assert response.headers["cache-control"] == "no-store"

        assert (await client.get("/api/auth/me")).json()[
            "email"
        ] == "teacher@example.com"
        client.client.cookies.clear()
        assert (await client.get("/api/auth/me")).status_code == 401
        bearer = {"Authorization": "Bearer " + body["token"]}
        assert (await client.get("/api/auth/me", headers=bearer)).status_code == 200


async def test_rejected_credentials_and_tokens(exams_app):
    async with PateraTestClient(exams_app) as client:
        for credentials in (
            {"email": "teacher@example.com", "password": "wrong-password-123"},
            {"email": "nobody@example.com", "password": PASSWORD},
        ):
            response = await client.post("/api/auth/login", json=credentials)
            assert response.status_code == 401
            assert response.json()["message"] == "Invalid email or password"

        headers = await login(client)
        user_id = (await client.get("/api/auth/me", headers=headers)).json()["id"]
        client.client.cookies.clear()
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
            {"sub": user_id, "ver": 0}, "another-secret-" * 4, algorithm="HS256"
        )
        for token in (expired, forged, "not-a-jwt"):
            response = await client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401
            assert response.json() == {
                "status": "error",
                "message": "Login required",
                "data": None,
            }


async def test_logout_clears_cookie(exams_app):
    async with PateraTestClient(exams_app) as client:
        await login(client)
        response = await client.get("/api/auth/logout")
        assert response.status_code == 204
        assert "Max-Age=0" in response.headers["set-cookie"]
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_password_change_and_role_removal_invalidate_tokens(exams_app):
    async with PateraTestClient(exams_app) as client:
        admin = Api(client, await login(client))
        other_headers = await login(client, "other@example.com")
        client.client.cookies.clear()
        users = (await admin("GET", "/api/admin/overview"))["users"]
        other = next(u for u in users if u["email"] == "other@example.com")

        await admin(
            "PUT",
            f"/api/admin/users/{other['id']}",
            json={
                "email": other["email"],
                "password": "brand-new-password",
                "roles": ["INSTRUCTOR"],
            },
        )
        assert (
            await client.get("/api/auth/me", headers=other_headers)
        ).status_code == 401
        other_headers = await login(client, "other@example.com", "brand-new-password")
        client.client.cookies.clear()
        assert (
            await client.get("/api/auth/me", headers=other_headers)
        ).status_code == 200

        await admin(
            "PUT",
            f"/api/admin/users/{other['id']}",
            json={"email": other["email"], "roles": []},
        )
        assert (
            await client.get("/api/categories/", headers=other_headers)
        ).status_code == 401
        response = await client.post(
            "/api/auth/login",
            json={"email": "other@example.com", "password": "brand-new-password"},
        )
        assert response.status_code == 403


async def test_role_requirements(exams_app):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        await teacher(
            "POST",
            "/api/admin/users",
            201,
            json={
                "email": "admin-only@example.com",
                "password": PASSWORD,
                "roles": ["ADMIN"],
            },
        )
        client.client.cookies.clear()
        assert (await client.get("/api/categories/")).status_code == 401
        assert (await client.get("/api/admin/overview")).status_code == 401
        instructor = Api(client, await login(client, "other@example.com"))
        await instructor("GET", "/api/categories/")
        await instructor("GET", "/api/admin/overview", 403)
        administrator = Api(client, await login(client, "admin-only@example.com"))
        await administrator("GET", "/api/admin/overview")
        await administrator("GET", "/api/exams/", 403)


async def test_browser_protections(exams_app):
    async with PateraTestClient(exams_app) as client:
        api = Api(client, await login(client))
        response = await client.post(
            "/api/categories/",
            json={"name": "X"},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403
        response = await client.post(
            "/api/categories/",
            content='{"name": "X"}',
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 415
        assert await api("GET", "/api/categories/") == []
        page = await client.get("/")
        assert page.status_code == 200
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]


async def test_exam_workflow_and_privacy(exams_app):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        other = Api(client, await login(client, "other@example.com"))
        client.client.cookies.clear()

        category, question = await bank(teacher)
        assert [c["name"] for c in await teacher("GET", "/api/categories/")] == [
            "Arithmetic"
        ]
        listed = await teacher("GET", "/api/questions/")
        assert listed == [question] and question["answers"] == ["3", "4", "5", "6"]
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json={
                "title": "Quiz",
                **window(),
                "random": {"category_ids": [category["id"]], "count": 1},
            },
        )
        assert exam["question_ids"] == [question["id"]]
        assert await teacher("GET", "/api/exams/") == [exam]
        assert (await client.get("/exam/" + exam["id"])).status_code == 200
        qr = await client.get(f"/api/exams/{exam['id']}/qr", headers=teacher.headers)
        assert qr.status_code == 200
        assert "image/svg+xml" in qr.headers["content-type"] and "<svg" in qr.text

        assert await other("GET", "/api/exams/") == []
        await other("DELETE", f"/api/exams/{exam['id']}", 404)
        await other("GET", f"/api/exams/{exam['id']}/qr", 404)
        await other("POST", "/api/questions/", 400, json=question_body(category["id"]))

        response = await client.post(
            "/api/attempts/",
            json={"exam_id": exam["id"], "email": "Student@Example.com"},
        )
        assert response.status_code == 201, response.text
        attempt = response.json()
        assert "correct" not in response.text and "owner" not in response.text
        assert attempt["questions"][0]["id"] == question["id"]
        submit = f"/api/attempts/{attempt['id']}/submit"
        response = await client.post(submit, json={"answers": {question["id"]: [1, 2]}})
        assert response.status_code == 422
        result = (
            await client.post(submit, json={"answers": {question["id"]: 1}})
        ).json()
        assert result == {"points": 3, "maximum": 3, "percentage": 100, "passed": True}
        assert (
            await client.post(submit, json={"answers": {question["id"]: 0}})
        ).json() == result
        response = await client.post(
            "/api/attempts/guessed/submit", json={"answers": {}}
        )
        assert response.status_code == 404

        await teacher("DELETE", f"/api/questions/{question['id']}", 409)
        await teacher("DELETE", f"/api/categories/{category['id']}", 409)
        await teacher("DELETE", f"/api/exams/{exam['id']}", 204)
        await teacher("DELETE", f"/api/questions/{question['id']}", 204)
        await teacher("DELETE", f"/api/categories/{category['id']}", 204)
        reports = await teacher("GET", "/api/reports/")
        assert reports[0]["count"] == 1 and reports[0]["exam_title"] == "Quiz"
        archived = reports[0]["attempts"][0]
        assert archived["student_email"] == "student@example.com"
        assert archived["questions"][0]["correct_answer"] == 1
        assert archived["questions"][0]["selected_answer"] == 1
        assert await other("GET", "/api/reports/") == []
        overview = await teacher("GET", "/api/admin/overview")
        assert overview["counts"] == {"questions": 0, "exams": 0, "attempts": 1}
        assert len(overview["reports"]) == 1


async def test_validation_window_and_snapshot(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        category, question = await bank(teacher)
        for invalid in (
            {"correct_answer": [0, 1]},
            {"correct_answer": 4},
            {"points": 0},
            {"answers": ["a"]},
            {"answers": ["a", "b", " ", "d"]},
            {"image": "javascript:alert(1)"},
        ):
            await teacher(
                "POST",
                "/api/questions/",
                422,
                json=question_body(category["id"], **invalid),
            )
        await teacher(
            "POST",
            "/api/exams/",
            400,
            json={
                "title": "Too many",
                **window(),
                "random": {"category_ids": [category["id"]], "count": 2},
            },
        )
        await teacher(
            "POST",
            "/api/exams/",
            422,
            json={
                "title": "Backwards",
                **window(1, -1),
                "question_ids": [question["id"]],
            },
        )
        await teacher("POST", "/api/exams/", 422, json={"title": "Empty", **window()})
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json={"title": "Test", **window(), "question_ids": [question["id"]]},
        )

        attempt = (
            await client.post(
                "/api/attempts/", json={"exam_id": exam["id"], "email": "s@example.com"}
            )
        ).json()
        await teacher(
            "PUT",
            f"/api/questions/{question['id']}",
            json=question_body(
                category["id"], question_text="Changed", correct_answer=0
            ),
        )
        result = await client.post(
            f"/api/attempts/{attempt['id']}/submit",
            json={"answers": {question["id"]: 1}},
        )
        assert result.json()["passed"] is True
        reports = await teacher("GET", "/api/reports/")
        assert reports[0]["attempts"][0]["questions"][0]["question_text"] == "2 + 2?"

        closed = await teacher(
            "POST",
            "/api/exams/",
            201,
            json={
                "title": "Closed",
                **window(-2, -1),
                "question_ids": [question["id"]],
            },
        )
        response = await client.post(
            "/api/attempts/", json={"exam_id": closed["id"], "email": "s@example.com"}
        )
        assert response.status_code == 400

        late = (
            await client.post(
                "/api/attempts/",
                json={"exam_id": exam["id"], "email": "late@example.com"},
            )
        ).json()
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with db:
            db.execute(
                "UPDATE attempts SET available_until=? WHERE id=?", (past, late["id"])
            )
        response = await client.post(
            f"/api/attempts/{late['id']}/submit", json={"answers": {question["id"]: 1}}
        )
        assert response.status_code == 400
        assert "availability window" in response.json()["message"]


async def test_weighted_grades_and_admin_safeguards(exams_app):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        category = await teacher(
            "POST", "/api/categories/", 201, json={"name": "Weighted"}
        )
        questions = [
            await teacher(
                "POST",
                "/api/questions/",
                201,
                json=question_body(
                    category["id"],
                    question_text=str(points),
                    correct_answer=0,
                    points=points,
                ),
            )
            for points in (1, 3)
        ]
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json={
                "title": "Weighted",
                **window(),
                "question_ids": [q["id"] for q in questions],
            },
        )
        attempt = (
            await client.post(
                "/api/attempts/", json={"exam_id": exam["id"], "email": "s@example.com"}
            )
        ).json()
        response = await client.post(
            f"/api/attempts/{attempt['id']}/submit",
            json={"answers": {questions[0]["id"]: 0, questions[1]["id"]: 1}},
        )
        assert response.json() == {
            "points": 1,
            "maximum": 4,
            "percentage": 25,
            "passed": False,
        }

        me = await teacher("GET", "/api/auth/me")
        await teacher(
            "PUT",
            f"/api/admin/users/{me['id']}",
            409,
            json={"email": me["email"], "roles": ["INSTRUCTOR"]},
        )
        await teacher(
            "POST",
            "/api/admin/users",
            409,
            json={"email": "other@example.com", "password": PASSWORD},
        )
        await teacher(
            "POST",
            "/api/admin/users",
            422,
            json={"email": "new@example.com", "password": "short"},
        )
        created = await teacher(
            "POST",
            "/api/admin/users",
            201,
            json={"email": "new@example.com", "password": PASSWORD, "roles": ["ADMIN"]},
        )
        assert created["roles"] == ["ADMIN"]


async def test_admin_access_follows_current_roles(exams_app):
    async with PateraTestClient(exams_app) as client:
        response = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert (await client.get("/admin/en/")).status_code == 200
        assert (await client.get("/admin", follow_redirects=False)).headers[
            "location"
        ] == "/admin/en/dashboard"

        teacher = Api(client, await login(client))
        dashboard = await client.get("/admin/en/dashboard")
        assert dashboard.status_code == 200
        assert "Users &amp; reports" in dashboard.text

        me = await teacher("GET", "/api/auth/me")
        await teacher(
            "POST",
            "/api/admin/users",
            201,
            json={
                "email": "second-admin@example.com",
                "password": PASSWORD,
                "roles": ["ADMIN"],
            },
        )
        await teacher(
            "PUT",
            f"/api/admin/users/{me['id']}",
            json={"email": me["email"], "roles": ["INSTRUCTOR"]},
        )
        response = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert response.headers["location"] == "/admin/en/unauthorized"

        await client.get("/api/auth/logout")
        response = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/en/"


async def test_admin_crud_obeys_domain_rules(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        await login(client)

        async def form(method, path, data):
            return await client.request(
                method, path, files={k: (None, str(v)) for k, v in data.items()}
            )

        base = "/admin/en/databases/exams/model/"
        for model in (
            "User",
            "Category",
            "Question",
            "Exam",
            "ExamQuestion",
            "Attempt",
            "AttemptQuestion",
        ):
            response = await client.get(base + model)
            assert response.status_code == 200, (model, response.text)

        owner = db.execute(
            "SELECT id FROM users WHERE email='teacher@example.com'"
        ).fetchone()["id"]
        other = db.execute(
            "SELECT id FROM users WHERE email='other@example.com'"
        ).fetchone()["id"]
        response = await form(
            "POST", base + "Category/create", {"owner_id": owner, "name": " Planets "}
        )
        assert response.status_code == 303, response.text
        category = db.execute("SELECT id, name FROM categories").fetchone()
        assert category["name"] == "Planets"

        question = {
            "owner_id": owner,
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
        ).status_code == 303
        assert (
            await form(
                "POST", base + "Question/create", {**question, "owner_id": other}
            )
        ).status_code == 422
        question_id = db.execute("SELECT id FROM questions").fetchone()["id"]
        url = base + "Question/pk/id/" + question_id
        assert (await form("PUT", url, {**question, "points": "3"})).status_code == 303
        assert (
            await form("PUT", url, {**question, "correct_answer": "4"})
        ).status_code == 422
        assert (
            await form("PUT", url, {**question, "owner_id": other})
        ).status_code == 422

        exam = {
            "owner_id": owner,
            "title": "Planets",
            "pass_percentage": "50",
            **window(),
        }
        assert (await form("POST", base + "Exam/create", exam)).status_code == 303
        assert (
            await form("POST", base + "Exam/create", {**exam, **window(1, -1)})
        ).status_code == 422
        exam_id = db.execute("SELECT id FROM exams").fetchone()["id"]
        response = await form(
            "POST",
            base + "ExamQuestion/create",
            {"exam_id": exam_id, "question_id": question_id, "position": "0"},
        )
        assert response.status_code == 303, response.text

        attempt = (
            await client.post(
                "/api/attempts/",
                json={"exam_id": exam_id, "email": "learner@example.com"},
            )
        ).json()
        result = await client.post(
            f"/api/attempts/{attempt['id']}/submit", json={"answers": {question_id: 0}}
        )
        assert result.json()["points"] == 3

        response = await form(
            "PUT",
            base + "Attempt/pk/id/" + attempt["id"],
            {"student_email": "Corrected@Example.com"},
        )
        assert response.status_code == 303, response.text
        row = db.execute("SELECT student_email, earned_points FROM attempts").fetchone()
        assert tuple(row) == ("corrected@example.com", 3)
        response = await client.delete(base + "Attempt/pk/id/" + attempt["id"])
        assert response.status_code == 422
        assert response.json()["message"] == "Archived exam evidence must be retained"
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
        response = await client.delete(base + "User/pk/id/" + owner)
        assert response.status_code == 422
        assert response.json()["message"] == "Keep at least one admin"
        response = await client.get(base + "Session")
        assert response.status_code == 404
        assert "Unknown database or model" in response.text

        new_user = {
            "email": "native@example.com",
            "password": "native-password-123",
            "is_instructor": "on",
        }
        assert (await form("POST", base + "User/create", new_user)).status_code == 303
        assert (
            await form(
                "POST",
                base + "User/create",
                {**new_user, "email": "short@example.com", "password": "short"},
            )
        ).status_code == 422
        stored = db.execute(
            "SELECT id, password_hash, token_version FROM users WHERE email='native@example.com'"
        ).fetchone()
        assert stored["password_hash"].startswith("bcrypt-sha256$")
        native = await login(client, "native@example.com", "native-password-123")
        await login(client)

        user_url = base + "User/pk/id/" + stored["id"]
        response = await form(
            "PUT",
            user_url,
            {
                "email": "native@example.com",
                "password": "changed-password-123",
                "is_instructor": "on",
            },
        )
        assert response.status_code == 303, response.text
        assert (
            db.execute(
                "SELECT token_version FROM users WHERE id=?", (stored["id"],)
            ).fetchone()[0]
            == 1
        )
        client.client.cookies.clear()
        assert (await client.get("/api/auth/me", headers=native)).status_code == 401
        await login(client, "native@example.com", "changed-password-123")


@pytest.mark.parametrize(
    "role,expected",
    [("instructor", [1, 0]), ("ADMIN", [0, 1]), ("both", [1, 1])],
)
def test_user_cli(exams_app, create_user, db, monkeypatch, role, expected):
    from app.cli import users_cli

    create_user("new@example.com", role)
    row = db.execute(
        "SELECT is_instructor, is_admin, password_hash FROM users WHERE email='new@example.com'"
    ).fetchone()
    assert [row["is_instructor"], row["is_admin"]] == expected
    assert row["password_hash"].startswith("bcrypt-sha256$")
    with pytest.raises(SystemExit):
        create_user("new@example.com", role)
    with pytest.raises(SystemExit):
        create_user("invalid@example.com", "student")
    with pytest.raises(SystemExit):
        create_user("weak@example.com", "instructor", password="short")
    passwords = iter([PASSWORD, "different-password"])
    with pytest.raises(SystemExit):
        monkeypatch.setattr(users_cli, "getpass", lambda _prompt: next(passwords))
        exams_app.run_cli("users:create", command_args=["mismatch@example.com"])
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3


async def test_legacy_werkzeug_hash_is_upgraded_on_login(exams_app, db):
    with db:
        db.execute(
            "UPDATE users SET password_hash=? WHERE email='other@example.com'",
            (generate_password_hash("legacy-password-123"),),
        )
    async with PateraTestClient(exams_app) as client:
        await login(client, "other@example.com", "legacy-password-123")
    stored = db.execute(
        "SELECT password_hash FROM users WHERE email='other@example.com'"
    ).fetchone()[0]
    assert stored.startswith("bcrypt-sha256$")


def test_sqlite_foreign_keys_are_on_by_default(env, monkeypatch):
    from app import App

    application = App(cli_mode=True)
    assert application.configs.EXAMS_DB.SQLITE_FOREIGN_KEYS is True
    application._remove_logger_sinks()

    monkeypatch.setenv("PATERA_EXAMS_DB__SQLITE_FOREIGN_KEYS", "false")
    application = App(cli_mode=True)
    assert application.configs.EXAMS_DB.SQLITE_FOREIGN_KEYS is False
    application._remove_logger_sinks()


async def test_deleting_an_exam_cascades_to_its_question_selection(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        _, question = await bank(teacher)
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json={"title": "Quiz", **window(), "question_ids": [question["id"]]},
        )
        await teacher("DELETE", f"/api/exams/{exam['id']}", 204)
    assert db.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0] == 0


async def test_openapi_documents_the_api(exams_app):
    async with PateraTestClient(exams_app) as client:
        response = await client.get("/openapi/specs.json")
        assert response.status_code == 200, response.text
        paths = response.json()["paths"]
        assert "/api/auth/login" in paths and "/api/exams/{exam_id}" in paths


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020001e221bc330000000049454e44ae426082"
)


async def test_admin_question_image_upload_and_exam_dates(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        await login(client)

        async def form(method, path, data, image=None):
            files = {k: (None, str(v)) for k, v in data.items()}
            if image is not None:
                files["image"] = image
            return await client.request(method, path, files=files)

        base = "/admin/en/databases/exams/model/"
        page = await client.get(base + "Question")
        assert 'type="file"' in page.text and 'id="update-field-image"' in page.text
        assert 'name="remove_image"' in page.text

        owner = db.execute(
            "SELECT id FROM users WHERE email='teacher@example.com'"
        ).fetchone()[0]
        await form("POST", base + "Category/create", {"owner_id": owner, "name": "Art"})
        category = db.execute("SELECT id FROM categories").fetchone()[0]
        question = {
            "owner_id": owner,
            "category_id": category,
            "question_text": "Which colour?",
            "answer_1": "Red",
            "answer_2": "Green",
            "answer_3": "Blue",
            "answer_4": "Grey",
            "correct_answer": "0",
            "points": "1",
        }
        response = await form(
            "POST", base + "Question/create", question, ("p.png", PNG, "image/png")
        )
        assert response.status_code == 303, response.text
        stored = db.execute("SELECT id, image FROM questions").fetchone()
        assert stored["image"].startswith("data:image/png;base64,")

        response = await form(
            "POST",
            base + "Question/create",
            question,
            ("p.png", b"not an image", "image/png"),
        )
        assert response.status_code == 422
        assert "PNG, JPEG, GIF or WebP" in response.json()["details"][0]["msg"]

        url = base + "Question/pk/id/" + stored["id"]
        assert (await form("PUT", url, {**question, "points": "2"})).status_code == 303
        assert (
            db.execute("SELECT image FROM questions").fetchone()[0] == stored["image"]
        )
        assert (
            await form("PUT", url, {**question, "remove_image": "on"})
        ).status_code == 303
        assert db.execute("SELECT image FROM questions").fetchone()[0] == ""

        page = await client.get(base + "Exam")
        assert 'type="datetime-local"' in page.text and 'data-utc="true"' in page.text
        exam = {
            "owner_id": owner,
            "title": "Colours",
            "pass_percentage": "50",
            "available_from": "2026-10-20T08:00:00.000Z",
            "available_until": "2026-10-20T10:30:00.000Z",
        }
        assert (await form("POST", base + "Exam/create", exam)).status_code == 303
        row = db.execute("SELECT available_from, available_until FROM exams").fetchone()
        assert tuple(row) == ("2026-10-20T08:00:00+00:00", "2026-10-20T10:30:00+00:00")
