from __future__ import annotations

import pytest

from patera import Request
from patera.admin import AdminInterface
from patera.admin.admin_interface import AdminConfig, Permissions
from patera.auth import Authentication
from patera.middleware import middleware
from patera.taskmanager import TaskManager

pytestmark = pytest.mark.integration


@middleware
class HeaderAuth(Authentication):
    async def user_loader(self, req: Request):
        return req.headers.get("x-user")

    async def roles_loader(self, user):
        return [Permissions.ADMIN_CAN_ENTER] if user == "admin" else []


class Admin(AdminInterface):
    pass


class Jobs(TaskManager):
    pass


ADMIN_CONFIG = AdminConfig(
    URL_FOR_FOR_LOGIN="OpenAPIController.docs",
    URL_FOR_FOR_LOGOUT="OpenAPIController.docs",
)


@pytest.fixture
def app(make_app):
    return make_app(
        extensions=[Jobs, Admin], middleware=[HeaderAuth], ADMIN=ADMIN_CONFIG
    )


async def test_admin_pages(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/admin/en/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]

        # Not logged in -> redirected to the login page
        res = await client.get("/admin/en/dashboard", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/admin/en/"

        # Logged in without the admin permission
        res = await client.get(
            "/admin/en/dashboard", headers={"x-user": "bob"}, follow_redirects=False
        )
        assert res.headers["location"] == "/admin/en/unauthorized"

        res = await client.get("/admin/en/dashboard", headers={"x-user": "admin"})
        assert res.status_code == 200

        # Unsupported language
        assert (await client.get("/admin/fr/")).status_code != 200


async def test_dashboard_reads_recent_records_from_log_files(app, client_for):
    async with client_for(app) as client:
        try:
            raise ValueError("disk check failed")
        except ValueError:
            app.logger.exception("disk almost full")
        app.logger.info("unrelated message")

        res = await client.get(
            "/admin/en/dashboard",
            params={"query": "disk"},
            headers={"x-user": "admin"},
        )
        assert res.status_code == 200
        assert "disk almost full" in res.text
        assert "unrelated message" not in res.text
        assert "ValueError: disk check failed" in res.text  # exception detail


async def test_dashboard_explains_disabled_log_files(make_app, client_for):
    app = make_app(
        extensions=[Jobs, Admin],
        middleware=[HeaderAuth],
        ADMIN=ADMIN_CONFIG,
        LOG_FILES={"ENABLED": False},
    )
    async with client_for(app) as client:
        res = await client.get("/admin/en/dashboard", headers={"x-user": "admin"})
        assert res.status_code == 200
        assert "LOG_FILES.ENABLED" in res.text


def test_admin_state_is_per_instance(make_app, app):
    other = make_app(extensions=[Admin], middleware=[HeaderAuth], ADMIN=ADMIN_CONFIG)
    assert app.get_extension(Admin).has_task_managers
    assert not other.get_extension(Admin).has_task_managers


def test_translation_fallbacks(app):
    admin = app.get_extension(Admin)
    key = next(iter(admin.TRANSLATIONS_MAP))
    assert admin.translate(key, "en") == admin.TRANSLATIONS_MAP[key]["en"]
    assert admin.translate(key, "xx") == admin.TRANSLATIONS_MAP[key]["en"]
    assert admin.translate("not-a-key", "en") == "not-a-key"


ADMIN = {"x-user": "admin"}
REGULAR_USER = {"x-user": "bob"}


@pytest.fixture
def files_app(make_app):
    return make_app(
        extensions=[Jobs, Admin],
        middleware=[HeaderAuth],
        ADMIN=ADMIN_CONFIG,
        files={"static/existing.txt": "hello", "static/sub/inner.txt": "inner"},
    )


async def test_file_explorer_requires_admin_permission(files_app, client_for):
    async with client_for(files_app) as client:
        # Not logged in
        res = await client.get("/admin/en/files/", follow_redirects=False)
        assert res.status_code == 303
        # Logged in, but not an admin: no access to listing, upload or delete
        res = await client.get(
            "/admin/en/files/", headers=REGULAR_USER, follow_redirects=False
        )
        assert res.status_code in (303, 401)
        res = await client.post(
            "/admin/en/files/folder",
            json={"path": "", "folder_name": "hacked"},
            headers={**REGULAR_USER, "content-type": "application/json"},
            follow_redirects=False,
        )
        assert res.status_code in (303, 401)
    from pathlib import Path

    assert not (Path(files_app.static_files_path) / "hacked").exists()


async def test_file_explorer_operations_and_path_traversal(files_app, client_for):
    from pathlib import Path

    static = Path(files_app.static_files_path)
    async with client_for(files_app) as client:
        res = await client.get("/admin/en/files/", headers=ADMIN)
        assert res.status_code == 200
        names = {item["name"] for item in res.json()["data"]["items"]}
        assert {"existing.txt", "sub"} <= names

        res = await client.post(
            "/admin/en/files/folder",
            json={"path": "", "folder_name": "new"},
            headers=ADMIN,
        )
        assert res.status_code in (200, 201)
        assert (static / "new").is_dir()

        res = await client.post(
            "/admin/en/files/",
            headers=ADMIN,
            data={"path": "new"},
            files={"files": ("up.txt", b"uploaded", "text/plain")},
        )
        assert res.status_code in (200, 201)
        assert (static / "new" / "up.txt").read_bytes() == b"uploaded"

        # Escaping the static folder is rejected
        res = await client.get("/admin/en/files/?path=../..", headers=ADMIN)
        assert res.status_code >= 400
        res = await client.post(
            "/admin/en/files/folder",
            json={"path": "../", "folder_name": "evil"},
            headers=ADMIN,
        )
        assert res.status_code >= 400
        assert not (static.parent / "evil").exists()
        res = await client.post(
            "/admin/en/files/folder",
            json={"path": "", "folder_name": "../evil"},
            headers=ADMIN,
        )
        assert res.status_code >= 400
        assert not (static.parent / "evil").exists()


async def test_task_manager_admin_requires_permission(app, client_for):
    async with client_for(app) as client:
        url = "/admin/en/task-managers/JOBS/"
        res = await client.get(url, headers=REGULAR_USER, follow_redirects=False)
        assert res.status_code in (303, 401)
        res = await client.get(url, headers=ADMIN)
        assert res.status_code == 200
