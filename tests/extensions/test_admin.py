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


# ---- Log severity filter ----------------------------------------------------------


async def test_dashboard_filters_by_minimum_severity(app, client_for):
    async with client_for(app) as client:
        app.logger.debug("debug-level detail")
        app.logger.info("info-level news")
        app.logger.warning("warning-level problem")
        app.logger.error("error-level failure")

        async def visible(**params) -> set[str]:
            res = await client.get(
                "/admin/en/dashboard",
                params={"query": "-level", "count": 100, **params},
                headers=ADMIN,
            )
            assert res.status_code == 200
            return {
                name
                for name in ("debug", "info", "warning", "error")
                if f"{name}-level" in res.text
            }

        # The default is INFO and above.
        assert await visible() == {"info", "warning", "error"}
        assert await visible(severity="WARNING") == {"warning", "error"}
        assert await visible(severity="trace") == {"debug", "info", "warning", "error"}
        # An unknown name falls back to INFO instead of failing.
        assert await visible(severity="LOUD") == {"info", "warning", "error"}

        res = await client.get(
            "/admin/en/dashboard", params={"severity": "ERROR"}, headers=ADMIN
        )
        # The chosen level is kept in sorting and paging links.
        assert "severity=ERROR" in res.text
        assert '<option value="ERROR" selected>' in res.text


def test_level_at_least_keeps_custom_levels():
    from patera.admin.schemas.dashboard_schemas import level_at_least

    assert level_at_least({"level": "ERROR"}, "WARNING")
    assert not level_at_least({"level": "DEBUG"}, "INFO")
    assert level_at_least({"level": "AUDIT"}, "CRITICAL")


# ---- Extension discovery -------------------------------------------------------------


class LateJobs(TaskManager):
    pass


def test_extensions_created_after_admin_are_found(make_app):
    app = make_app(extensions=[Admin], middleware=[HeaderAuth], ADMIN=ADMIN_CONFIG)
    admin = app.get_extension(Admin)
    assert not admin.has_task_managers
    late = LateJobs(app)  # created after Admin, e.g. injected later
    assert admin.has_task_managers
    assert admin.task_managers == {"LATE_JOBS": late}


async def test_late_task_manager_panel_is_served(make_app, client_for):
    app = make_app(extensions=[Admin], middleware=[HeaderAuth], ADMIN=ADMIN_CONFIG)
    LateJobs(app)
    async with client_for(app) as client:
        res = await client.get("/admin/en/task-managers/LATE_JOBS/", headers=ADMIN)
        assert res.status_code == 200
        dashboard = await client.get("/admin/en/dashboard", headers=ADMIN)
        assert "/admin/en/task-managers/LATE_JOBS/" in dashboard.text


def test_admin_ignore_hides_an_extension(make_app):
    from patera.admin.admin_interface import admin_ignore

    @admin_ignore
    class HiddenJobs(TaskManager):
        pass

    app = make_app(extensions=[Admin], middleware=[HeaderAuth], ADMIN=ADMIN_CONFIG)
    HiddenJobs(app)
    assert not app.get_extension(Admin).has_task_managers


# ---- Notifications for failed emails -------------------------------------------------

from patera.email import EmailClient, EmailConfig  # noqa: E402


class PanelMailer(EmailClient):
    pass


MAILER_CONFIG = EmailConfig(
    SENDER_NAME_OR_ADDRESS="admin@example.com",
    SMTP_SERVER="smtp.invalid",
    SMTP_PORT=25,
)


@pytest.fixture
def mail_app(make_app):
    return make_app(
        extensions=[Admin, PanelMailer],
        middleware=[HeaderAuth],
        ADMIN=ADMIN_CONFIG,
        PANEL_MAILER=MAILER_CONFIG,
    )


def _email_controller(app):
    from patera.admin.admin_email_controller import _AdminEmailClientController

    return app.get_controller(_AdminEmailClientController)


async def test_failed_panel_email_becomes_a_notification(
    mail_app, client_for, monkeypatch
):
    mailer = mail_app.get_extension(PanelMailer)

    async def refuse(*args, **kwargs):
        raise ConnectionRefusedError("SMTP server refused the connection")

    monkeypatch.setattr(mailer, "send_email", refuse)
    controller = _email_controller(mail_app)

    async with client_for(mail_app) as client:
        res = await client.get("/admin/en/notifications", headers=ADMIN)
        assert res.json()["data"] == {"enabled": True, "unread": 0, "items": []}

        await controller.deliver_email(
            mailer, to_address=["a@example.com"], subject="Weekly report", body="Hi"
        )

        res = await client.get("/admin/en/notifications", headers=ADMIN)
        data = res.json()["data"]
        assert data["unread"] == 1
        item = data["items"][0]
        assert item["kind"] == "email_failed"
        assert item["level"] == "ERROR"
        assert "Weekly report" in item["message"]
        assert item["data"]["recipients"] == ["a@example.com"]
        assert item["data"]["sender"] == "admin@example.com"
        assert "SMTP server refused" in item["data"]["error"]

        # Marking as read stores the newest notification's time in a cookie.
        seen = await client.post("/admin/en/notifications/seen", headers=ADMIN)
        assert seen.status_code == 200
        assert "patera_admin_notifications_seen" in seen.headers["set-cookie"]
        res = await client.get("/admin/en/notifications", headers=ADMIN)
        assert res.json()["data"]["unread"] == 0
        assert len(res.json()["data"]["items"]) == 1

        # A newer failure is unread again.
        await controller.deliver_email(
            mailer, to_address="b@example.com", subject="Invoice", body="Hi"
        )
        res = await client.get("/admin/en/notifications", headers=ADMIN)
        data = res.json()["data"]
        assert data["unread"] == 1
        assert data["items"][0]["data"]["subject"] == "Invoice"


async def test_successful_panel_email_creates_no_notification(
    mail_app, client_for, monkeypatch
):
    mailer = mail_app.get_extension(PanelMailer)
    sent: list[tuple] = []

    async def accept(*args, **kwargs):
        sent.append((args, kwargs))

    monkeypatch.setattr(mailer, "send_email", accept)
    async with client_for(mail_app) as client:
        await _email_controller(mail_app).deliver_email(
            mailer, to_address=["a@example.com"], subject="Hello", body="Hi"
        )
        assert sent
        res = await client.get("/admin/en/notifications", headers=ADMIN)
        assert res.json()["data"]["items"] == []


async def test_notifications_require_admin_permission(mail_app, client_for):
    async with client_for(mail_app) as client:
        res = await client.get(
            "/admin/en/notifications", headers=REGULAR_USER, follow_redirects=False
        )
        assert res.status_code in (303, 401, 403)


async def test_applications_can_add_notifications(mail_app, client_for):
    admin = mail_app.get_extension(Admin)
    async with client_for(mail_app) as client:
        admin.notify(
            "import_failed", "Nightly import failed", level="warning", file="a.csv"
        )
        res = await client.get("/admin/en/notifications", headers=ADMIN)
    item = res.json()["data"]["items"][0]
    assert item["kind"] == "import_failed"
    assert item["level"] == "WARNING"
    assert item["data"] == {"file": "a.csv"}


async def test_header_renders_the_notification_menu(mail_app, client_for):
    async with client_for(mail_app) as client:
        res = await client.get("/admin/en/dashboard", headers=ADMIN)
    assert 'id="admin-notifications"' in res.text
    assert "/admin/en/notifications" in res.text


def test_default_language_is_lower_cased():
    urls = ADMIN_CONFIG.model_dump(include={"URL_FOR_FOR_LOGIN", "URL_FOR_FOR_LOGOUT"})
    assert AdminConfig(DEFAULT_LANGUAGE="SL", **urls).DEFAULT_LANGUAGE == "sl"


def test_slovenian_uses_the_iso_code(app):
    admin = app.get_extension(Admin)
    assert "sl" in admin.supported_languages and "si" not in admin.supported_languages
    assert admin.translate("dashboard", "sl") != admin.translate("dashboard", "en")


async def test_slovenian_pages_are_served(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/admin/sl/dashboard", headers={"x-user": "admin"})
        assert res.status_code == 200
        res = await client.get("/admin/si/dashboard", headers={"x-user": "admin"})
        assert res.status_code == 400


async def test_footer_shows_application_and_admin_versions(app, client_for):
    from importlib.metadata import version

    async with client_for(app) as client:
        res = await client.get("/admin/en/dashboard", headers={"x-user": "admin"})
        assert f"{app.configs.VERSION} · " in res.text
        assert version("patera-admin") in res.text
        # The logout link resolves through URL_FOR_FOR_LOGOUT
        assert f'data-logout-url="{app.url_for("OpenAPIController.docs")}"' in res.text


def test_every_translated_key_exists_in_every_language():
    import re
    from pathlib import Path

    import patera.admin as admin_package
    from patera.admin.translations import TRANSLATIONS_MAP

    root = Path(admin_package.__file__).parent
    sources = [
        *root.glob("templates/**/*.html"),
        *root.glob("*.py"),
        *(p for p in root.glob("static/js/**/*.js") if "vendors" not in p.parts),
    ]
    pattern = re.compile(r"""translate\(\s*['"]([a-z0-9_]+)['"]""")
    used = {key for path in sources for key in pattern.findall(path.read_text("utf-8"))}
    assert used, "no translate() calls found"
    assert sorted(used - TRANSLATIONS_MAP.keys()) == []
    languages = set(Admin._supported_languages)
    incomplete = [k for k, v in TRANSLATIONS_MAP.items() if set(v) != languages]
    assert incomplete == []


def test_log_records_sort_by_severity_and_type():
    from patera.admin.schemas.dashboard_schemas import LogsQuerySchema, log_sort_key

    records = [
        {"level": "WARNING", "time": "3", "line": 100},
        {"level": "DEBUG", "time": "1", "line": 9},
        {"level": "CRITICAL", "time": "2"},
        {"level": "ERROR", "time": "4", "line": "20"},
        {"level": "AUDIT", "time": "5", "line": 3},
    ]
    by_level = sorted(records, key=lambda r: log_sort_key(r, "level"))
    assert [r["level"] for r in by_level] == [
        "AUDIT",
        "DEBUG",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ]
    # Lines sort numerically and a missing line does not break sorting
    by_line = sorted(records, key=lambda r: log_sort_key(r, "line"))
    assert [r.get("line") for r in by_line] == [None, 3, 9, "20", 100]

    assert LogsQuerySchema(order_by="-level").order_by == "-level"
    assert LogsQuerySchema(order_by="password").order_by == "-time"


async def test_dashboard_sorts_by_level(app, client_for):
    async with client_for(app) as client:
        app.logger.error("sortcheck error")
        app.logger.warning("sortcheck warning")
        app.logger.critical("sortcheck critical")
        res = await client.get(
            "/admin/en/dashboard",
            params={"query": "sortcheck", "order_by": "-level"},
            headers=ADMIN,
        )
        text = res.text
        positions = [
            text.index(f"sortcheck {name}") for name in ("critical", "error", "warning")
        ]
        assert positions == sorted(positions)


async def test_admin_under_a_url_prefix(make_app, client_for):
    app = make_app(
        extensions=[Admin],
        middleware=[HeaderAuth],
        ADMIN=ADMIN_CONFIG,
        URL_PREFIX="/v1",
    )
    async with client_for(app) as client:
        res = await client.get("/v1/admin/en/dashboard", follow_redirects=False)
        assert res.headers["location"] == "/v1/admin/en/"
        res = await client.get("/v1/admin/en/dashboard", headers={"x-user": "admin"})
        assert res.status_code == 200
        # Admin's own assets and logo live under the prefix too.
        assert "/v1/admin/en/_static/patera_logo.png" in res.text
        logo = await client.get("/v1/admin/en/_static/patera_logo.png")
        assert logo.status_code == 200
