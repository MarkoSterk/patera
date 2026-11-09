from conftest import PASSWORD
from patera.testing import PateraTestClient
from test_quick_exams import login

NEW_PASSWORD = "an-even-longer-password-456"


async def test_change_own_password(exams_app):
    async with PateraTestClient(exams_app) as client:
        old_headers = await login(client)
        other_session = await login(client)
        client.client.cookies.clear()

        async def change(body, headers=old_headers):
            return await client.post("/api/auth/password", json=body, headers=headers)

        # Signed-in users only; the current password must be right.
        response = await client.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 401
        response = await change(
            {"current_password": "wrong-password-123", "new_password": NEW_PASSWORD}
        )
        assert response.status_code == 400
        assert "current password is incorrect" in response.text
        response = await change(
            {"current_password": PASSWORD, "new_password": PASSWORD}
        )
        assert response.status_code == 400
        response = await change({"current_password": PASSWORD, "new_password": "short"})
        assert response.status_code == 422
        response = await change(
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "x": 1}
        )
        assert response.status_code == 422
        # Failed attempts change nothing.
        assert (
            await client.get("/api/auth/me", headers=other_session)
        ).status_code == 200

        response = await change(
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["user"]["email"] == "teacher@example.com"
        assert "quick_exams_token" in response.headers.get("set-cookie", "")

        # This browser continues with the new token; every earlier token ends.
        new_headers = {"Authorization": "Bearer " + body["token"]}
        client.client.cookies.clear()
        assert (
            await client.get("/api/auth/me", headers=new_headers)
        ).status_code == 200
        assert (
            await client.get("/api/auth/me", headers=old_headers)
        ).status_code == 401
        assert (
            await client.get("/api/auth/me", headers=other_session)
        ).status_code == 401

        # Sign-in uses the new password only.
        response = await client.post(
            "/api/auth/login",
            json={"email": "teacher@example.com", "password": PASSWORD},
        )
        assert response.status_code == 401
        await login(client, password=NEW_PASSWORD)
