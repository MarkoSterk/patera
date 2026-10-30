from __future__ import annotations

import datetime
import os
from typing import Optional

import pytest

from patera import Request, UploadedFile
from patera.admin import AdminInterface
from patera.admin.admin_interface import AdminConfig, Permissions
from patera.admin.custom_elements import (
    DateInput,
    FileInput,
    LatexInput,
    PasswordInput,
    SelectInput,
)
from patera.admin.form_values import AdminFormError
from patera.auth import Authentication
from patera.middleware import middleware
from patera.taskmanager import TaskManager
from patera.database.sql import (
    DeclarativeBaseModel,
    SqlDatabase,
    SqlDatabaseConfig,
    SqlDatabaseManager,
)
from patera.database.sql.declarative_base import ModelMeta
from sqlalchemy import Boolean, Date, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

pytestmark = pytest.mark.integration


@middleware
class HeaderAuth(Authentication):
    async def user_loader(self, req: Request):
        return req.headers.get("x-user")

    async def roles_loader(self, user):
        if user == "admin":
            return list(Permissions)
        if user == "viewer":
            # May enter and look, but not change anything.
            return [Permissions.ADMIN_CAN_ENTER, Permissions.ADMIN_CAN_VIEW]
        if user == "outsider":
            # May view records, but not enter the dashboard.
            return [Permissions.ADMIN_CAN_VIEW]
        return []


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
        assert res.status_code in (303, 403)
        res = await client.post(
            "/admin/en/files/folder",
            json={"path": "", "folder_name": "hacked"},
            headers={**REGULAR_USER, "content-type": "application/json"},
            follow_redirects=False,
        )
        # Signed in without the permission: 403 Forbidden, with an error body.
        assert res.status_code == 403
        assert res.json()["status"] == "error"
    from pathlib import Path

    assert not (Path(files_app.static_files_path) / "hacked").exists()


async def test_admin_actions_need_entry_and_their_own_permission(files_app, client_for):
    from pathlib import Path

    static = Path(files_app.static_files_path)
    viewer = {"x-user": "viewer"}
    async with client_for(files_app) as client:
        res = await client.get("/admin/en/files/", headers=viewer)
        assert res.status_code == 200
        # ADMIN_CAN_ENTER alone no longer allows creating or deleting.
        res = await client.post(
            "/admin/en/files/folder",
            json={"path": "", "folder_name": "made_by_viewer"},
            headers={**viewer, "content-type": "application/json"},
            follow_redirects=False,
        )
        assert res.status_code == 403
        assert not (static / "made_by_viewer").exists()
        res = await client.request(
            "DELETE",
            "/admin/en/files/",
            json={"path": "", "files": ["existing.txt"]},
            headers={**viewer, "content-type": "application/json"},
            follow_redirects=False,
        )
        assert res.status_code == 403
        assert (static / "existing.txt").exists()
        # ADMIN_CAN_VIEW without ADMIN_CAN_ENTER does not open the panel.
        res = await client.get(
            "/admin/en/files/",
            headers={"x-user": "outsider"},
            follow_redirects=False,
        )
        assert res.status_code in (303, 403)


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


class NoteBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "notes"


class AdminNote(NoteBase):
    __tablename__ = "admin_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class NotesDb(SqlDatabase):
    __db_name__ = "notes"


class NoteDatabases(SqlDatabaseManager):
    databases = [NotesDb]


class NotesAdmin(AdminInterface):
    MANAGED_MODELS = [AdminNote]


async def test_database_pages_only_accept_databases(make_app, client_for, tmp_path):
    app = make_app(
        extensions=[NoteDatabases, Jobs, NotesAdmin],
        middleware=[HeaderAuth],
        NOTES_DB=SqlDatabaseConfig(
            DATABASE_URI=f"sqlite+aiosqlite:///{tmp_path / 'notes.db'}"
        ),
        NOTES_ADMIN=ADMIN_CONFIG,
    )
    async with client_for(app) as client:
        res = await client.get("/admin/en/databases/notes", headers={"x-user": "admin"})
        assert res.status_code == 200
        # Other extensions and unknown names are not databases.
        for name in ("NOTES_ADMIN", "JOBS", "missing"):
            res = await client.get(
                f"/admin/en/databases/{name}", headers={"x-user": "admin"}
            )
            assert res.status_code == 404
            assert res.json()["status"] == "error"


class MemberBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "members"


class Member(MemberBase):
    __tablename__ = "admin_form_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int] = mapped_column(Integer)
    joined: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(20), default="member")

    class Meta(ModelMeta):
        exclude_from_create_form = ["role"]
        exclude_from_update_form = ["role"]


class MembersDb(SqlDatabase):
    __db_name__ = "members"


class MemberDatabases(SqlDatabaseManager):
    databases = [MembersDb]


class MembersAdmin(AdminInterface):
    MANAGED_MODELS = [Member]


MEMBER_BACKENDS = ["sqlite"] + (
    ["postgresql"] if os.environ.get("PATERA_TEST_PG_URI") else []
)


@pytest.mark.parametrize("backend", MEMBER_BACKENDS)
async def test_admin_forms_without_a_schema(make_app, client_for, tmp_path, backend):
    uri = (
        f"sqlite+aiosqlite:///{tmp_path / 'members.db'}"
        if backend == "sqlite"
        else os.environ["PATERA_TEST_PG_URI"]
    )
    app = make_app(
        extensions=[MemberDatabases, Jobs, MembersAdmin],
        middleware=[HeaderAuth],
        MEMBERS_DB=SqlDatabaseConfig(DATABASE_URI=uri),
        MEMBERS_ADMIN=ADMIN_CONFIG,
    )
    db = app.get_extension(MemberDatabases).get_database("members")
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(MemberBase.metadata.drop_all, tables=[Member.__table__])
        await conn.run_sync(MemberBase.metadata.create_all, tables=[Member.__table__])
    base = "/admin/en/databases/members/model/Member"
    try:
        async with client_for(app) as client:
            # Values arrive as text, as a browser form sends them; "role" is
            # not in the form and must not be settable.
            res = await client.post(
                base + "/create",
                headers=ADMIN,
                files={
                    "name": (None, "Ana"),
                    "age": (None, "31"),
                    "joined": (None, "2026-01-02"),
                    "active": (None, "true"),
                    "role": (None, "owner"),
                },
                follow_redirects=False,
            )
            assert res.status_code == 303, res.text
            res = await client.post(
                base + "/create",
                headers=ADMIN,
                files={"name": (None, "Bo"), "age": (None, "old")},
            )
            assert res.status_code == 422
            assert res.json()["details"][0]["loc"] == ["age"]

            # The key in the URL is converted too (PostgreSQL compares types).
            record = await client.get(base + "/pk/id/1", headers=ADMIN)
            assert record.status_code == 200, record.text
            assert record.json()["data"]["age"] == 31

            # An unticked checkbox is not sent: it switches the value off.
            res = await client.put(
                base + "/pk/id/1",
                headers=ADMIN,
                files={
                    "name": (None, "Ana"),
                    "age": (None, "32"),
                    "joined": (None, ""),
                },
                follow_redirects=False,
            )
            assert res.status_code == 303, res.text

            for url in (
                base + "/pk/id/x",
                base + "/pk/other/1",
                base + "/pk/id",
                "/admin/en/databases/members/model/Missing/pk/id/1",
                "/admin/en/databases/missing/model/Member/pk/id/1",
            ):
                assert (await client.get(url, headers=ADMIN)).status_code == 404, url
        async with db.session_scope() as session:
            member = (await session.execute(select(Member))).scalar_one()
        assert (member.name, member.age, member.joined, member.active, member.role) == (
            "Ana",
            32,
            None,
            False,
            "member",
        )
    finally:
        async with db.engine.begin() as conn:
            await conn.run_sync(MemberBase.metadata.drop_all, tables=[Member.__table__])
        await db.disconnect()


class GuardedBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "guarded"


class GuardedItem(GuardedBase):
    __tablename__ = "admin_guarded_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    async def admin_delete(self) -> None:
        if self.locked:
            raise AdminFormError(
                [
                    {
                        "loc": ["record"],
                        "msg": "Locked items are kept",
                        "type": "value_error",
                    }
                ]
            )


class GuardedDb(SqlDatabase):
    __db_name__ = "guarded"


class GuardedDatabases(SqlDatabaseManager):
    databases = [GuardedDb]


class GuardedAdmin(AdminInterface):
    MANAGED_MODELS = [GuardedItem]


async def test_refused_deletes_and_unknown_models(make_app, client_for, tmp_path):
    app = make_app(
        extensions=[GuardedDatabases, Jobs, GuardedAdmin],
        middleware=[HeaderAuth],
        GUARDED_DB=SqlDatabaseConfig(
            DATABASE_URI=f"sqlite+aiosqlite:///{tmp_path / 'guarded.db'}"
        ),
        GUARDED_ADMIN=ADMIN_CONFIG,
    )
    db = app.get_extension(GuardedDatabases).get_database("guarded")
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(
            GuardedBase.metadata.create_all, tables=[GuardedItem.__table__]
        )
    async with db.session_scope() as session:
        session.add_all(
            [
                GuardedItem(id=1, name="kept", locked=True),
                GuardedItem(id=2, name="free"),
            ]
        )
    base = "/admin/en/databases/guarded/model/"
    try:
        async with client_for(app) as client:
            # A hook that refuses deletion is a client error with its reason.
            res = await client.delete(base + "GuardedItem/pk/id/1", headers=ADMIN)
            assert res.status_code == 422
            assert res.json()["message"] == "Locked items are kept"
            res = await client.delete(
                base + "GuardedItem/pk/id/2", headers=ADMIN, follow_redirects=False
            )
            assert res.status_code == 303

            # An unknown model is answered with the Admin error page.
            res = await client.get(base + "Missing", headers=ADMIN)
            assert res.status_code == 404
            assert "text/html" in res.headers["content-type"]
            assert "Unknown database or model" in res.text
        async with db.session_scope() as session:
            names = (await session.execute(select(GuardedItem.name))).scalars().all()
        assert names == ["kept"]
    finally:
        await db.disconnect()


BUNDLE = "/admin/en/_static/js/vendors/bootstrap/bootstrap.bundle.min.js"


async def test_pages_outside_the_layout_use_bundled_assets(app, client_for):
    async with client_for(app) as client:
        pages = [
            await client.get("/admin/en/"),
            await client.get("/admin/en/unauthorized", headers={"x-user": "bob"}),
        ]
        for page in pages:
            assert page.status_code == 200
            assert "cdn.jsdelivr.net" not in page.text
            assert BUNDLE in page.text
        asset = await client.get(BUNDLE)
        assert asset.status_code == 200


class UploadBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "uploads"


class Upload(UploadBase):
    __tablename__ = "admin_uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    attachment: Mapped[str] = mapped_column(String(200), default="")
    due: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)

    class Meta(ModelMeta):
        custom_form_fields = [
            FileInput(name="attachment", accept="text/plain", max_size=100),
            DateInput(name="due"),
        ]

    async def admin_create(self, new_data):
        await self.admin_update(new_data)

    async def admin_update(self, new_data):
        upload = new_data.pop("attachment", None)
        if isinstance(upload, UploadedFile):
            self.attachment = upload.read().decode()
        for key, value in new_data.items():
            setattr(self, key, value)


class UploadsDb(SqlDatabase):
    __db_name__ = "uploads"


class UploadDatabases(SqlDatabaseManager):
    databases = [UploadsDb]


class UploadsAdmin(AdminInterface):
    MANAGED_MODELS = [Upload]


def test_file_and_date_inputs_render_as_inputs():
    file_input = FileInput(
        name="attachment", accept=["image/png", "image/jpeg"], max_size=10
    )
    html = str(file_input.render({"name": "attachment", "form": "update"}))
    assert html.startswith("<input ") and not html.endswith("</input>")
    assert 'type="file"' in html and 'id="update-field-attachment"' in html
    assert 'accept="image/png,image/jpeg"' in html and 'data-max-size="10"' in html
    assert 'class="form-control"' in html

    date_html = str(DateInput(name="due").render({"name": "due"}))
    assert 'type="date"' in date_html and 'id="create-field-due"' in date_html
    moment = str(
        DateInput(name="at", include_time=True, utc=True).render({"name": "at"})
    )
    assert 'type="datetime-local"' in moment and 'data-utc="true"' in moment
    with pytest.raises(ValueError):
        DateInput(name="day", utc=True)


def test_password_never_renders_existing_value():
    element = PasswordInput(
        name="password", value="secret", attributes={"value": "hash"}
    )
    html = str(element.render({"name": "password", "form": "update"}))
    assert 'type="password"' in html
    assert 'autocomplete="new-password"' in html
    assert 'id="update-field-password"' in html
    assert "value=" not in html and "secret" not in html and "hash" not in html


def test_select_options_escape_and_select_values():
    element = SelectInput(
        name="status", options={0: "<Draft>", 1: "Published"}, value=0
    )
    html = str(element.render({"name": "status", "form": "update", "required": True}))
    assert '<option value="0" selected>&lt;Draft&gt;</option>' in html
    assert '<option value="1">Published</option>' in html
    assert 'id="update-field-status"' in html and " required" in html
    assert element.converts_value
    html = str(SelectInput(name="x", options=[('a"b', "A&B")]).render())
    assert '<option value="a&quot;b">A&amp;B</option>' in html


def test_latex_input_renders_a_form_control_and_preview():
    element = LatexInput(name="body", maxlength=50)
    html = str(
        element.render(
            {"name": "body", "label": "Body", "required": True, "form": "update"}
        )
    )
    assert html.startswith('<latex-input data-field-name="body">')
    # The inner control carries the form attributes; the wrapper does not.
    assert (
        '<textarea name="body" id="update-field-body" required aria-label="Body"'
        ' class="form-control" maxlength="50" rows="4">\n</textarea>'
    ) in html
    assert "data-preview" in html and 'aria-live="polite"' in html
    assert element.converts_value

    single = str(
        LatexInput(name="line", multiline=False, value='a<"b').render({"name": "line"})
    )
    assert '<input name="line" id="create-field-line"' in single
    assert 'type="text" value="a&lt;&quot;b"' in single and "<textarea" not in single
    assert str(LatexInput(name="t", value="<b>").render(None)).count("&lt;b&gt;") == 1


async def test_latex_input_assets_are_served_by_admin(make_app, client_for):
    app = make_app(extensions=[Admin], middleware=[HeaderAuth], ADMIN=ADMIN_CONFIG)
    async with client_for(app) as client:
        for path in (
            "js/inputs/latexInput.js",
            "js/inputs/latex.js",
            "js/inputs/latexInput.css",
            "js/vendors/temml/temml.min.js",
            "js/vendors/temml/Temml-Local.css",
            "js/vendors/temml/Temml.woff2",
        ):
            res = await client.get("/admin/en/_static/" + path)
            assert res.status_code == 200, path


async def test_file_and_date_inputs_through_admin_forms(make_app, client_for, tmp_path):
    app = make_app(
        extensions=[UploadDatabases, Jobs, UploadsAdmin],
        middleware=[HeaderAuth],
        UPLOADS_DB=SqlDatabaseConfig(
            DATABASE_URI=f"sqlite+aiosqlite:///{tmp_path / 'uploads.db'}"
        ),
        UPLOADS_ADMIN=ADMIN_CONFIG,
    )
    db = app.get_extension(UploadDatabases).get_database("uploads")
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(UploadBase.metadata.create_all, tables=[Upload.__table__])
    base = "/admin/en/databases/uploads/model/Upload"
    try:
        async with client_for(app) as client:
            page = await client.get(base, headers=ADMIN)
            assert page.status_code == 200
            # Each dialog has its own element, and labels point at it.
            assert 'id="create-field-attachment"' in page.text
            assert 'id="update-field-attachment"' in page.text
            assert 'for="update-field-attachment"' in page.text
            assert "</input>" not in page.text

            res = await client.post(
                base + "/create",
                headers=ADMIN,
                files={
                    "name": (None, "report"),
                    "attachment": ("notes.txt", b"hello", "text/plain"),
                    "due": (None, "2026-10-20"),
                },
                follow_redirects=False,
            )
            assert res.status_code == 303, res.text

            # No file chosen: the field is not sent and the value is kept.
            res = await client.put(
                base + "/pk/id/1",
                headers=ADMIN,
                files={"name": (None, "renamed"), "due": (None, "2026-11-01")},
                follow_redirects=False,
            )
            assert res.status_code == 303, res.text
            res = await client.post(
                base + "/create",
                headers=ADMIN,
                files={"name": (None, "bad"), "due": (None, "not a date")},
            )
            assert res.status_code == 422
            assert res.json()["details"][0]["loc"] == ["due"]
        async with db.session_scope() as session:
            upload = (await session.execute(select(Upload))).scalar_one()
        assert (upload.name, upload.attachment, upload.due) == (
            "renamed",
            "hello",
            datetime.date(2026, 11, 1),
        )
    finally:
        await db.disconnect()


# ----- Request statistics ----------------------------------------------------------

from patera import RequestRecord  # noqa: E402
from patera.admin.request_stats import RequestStats, percentile  # noqa: E402


def _record(at, status=200, route="/items/<id>", method="GET", ms=10.0):
    return RequestRecord(
        method=method,
        path="/x",
        route=route,
        status_code=status,
        started_at=at,
        duration=ms / 1000,
    )


def test_request_stats_counts_classes_routes_and_errors():
    now = 1_800_000_000.0
    stats = RequestStats(started_at=now - 7200)
    for second in range(30):
        stats.observe(_record(now - 60 + second, ms=20))
    stats.observe(_record(now - 30, status=404, route=None, ms=1))
    stats.observe(_record(now - 20, status=500, route="/boom", method="POST", ms=900))
    stats.observe(_record(now - 10, status=302))
    stats.observe(_record(now - 5, status=None))  # the client left: not counted
    stats.observe(_record(now - 4000))  # older than one hour

    summary = stats.summary("1h", now=now)
    totals = summary["totals"]
    assert (totals["requests"], totals["2xx"], totals["3xx"]) == (33, 30, 1)
    assert (totals["4xx"], totals["5xx"]) == (1, 1)
    assert totals["p95_ms"] is not None and 10 < totals["p95_ms"] <= 1000
    assert summary["uptime"] == 7200 and summary["step"] == 60
    assert len(summary["series"]) == 60
    assert sum(point["requests"] for point in summary["series"]) == 33

    assert summary["routes"][0] == {
        "method": "GET",
        "route": "/items/<id>",
        "requests": 31,
        "4xx": 0,
        "5xx": 0,
        "average_ms": pytest.approx((30 * 20 + 10) / 31),
    }
    assert [e["status"] for e in summary["errors"]] == [404, 500]
    assert summary["errors"][0]["routes"] == [{"route": "(no route)", "requests": 1}]

    # The 24-hour view still sees the older request.
    assert stats.summary("24h", now=now)["totals"]["requests"] == 34


def test_request_stats_drop_buckets_older_than_a_day():
    stats = RequestStats(started_at=0)
    stats.observe(_record(1000.0))
    stats.observe(_record(1000.0 + 2 * 86400))
    assert len(stats._buckets) == 1 and len(stats._route_buckets) == 1


def test_percentile_interpolates_within_a_bin():
    histogram = [0] * 14
    histogram[3] = 10  # ten requests between 5 and 10 ms
    assert percentile(histogram, 0.5) == pytest.approx(7.5)
    assert percentile([0] * 14, 0.95) is None


async def test_dashboard_request_statistics(app, client_for):
    admin = {"x-user": "admin"}
    async with client_for(app) as client:
        await client.get("/nowhere")
        page = await client.get("/admin/en/dashboard", headers=admin)
        assert page.status_code == 200
        assert 'id="request-stats"' in page.text
        assert "js/dashboard/request_stats.js" in page.text
        assert "Busiest endpoints" in page.text

        res = await client.get("/admin/en/dashboard/stats?period=15m", headers=admin)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["period"] == "15m" and len(data["series"]) == 90
        assert data["totals"]["4xx"] >= 1
        assert {
            "status": 404,
            "requests": 1,
            "routes": [{"route": "(no route)", "requests": 1}],
        } in data["errors"]
        # The dashboard's own polling is not counted.
        routes = {entry["route"] for entry in data["routes"]}
        assert not any(route.endswith("/dashboard/stats") for route in routes)
        assert any(route.endswith("/dashboard") for route in routes)

        res = await client.get("/admin/en/dashboard/stats?period=2d", headers=admin)
        assert res.status_code == 400
        res = await client.get("/admin/en/dashboard/stats", follow_redirects=False)
        assert res.status_code in (302, 303)
        js = await client.get("/admin/en/_static/js/dashboard/request_stats.js")
        assert js.status_code == 200


async def test_request_statistics_can_be_disabled(make_app, client_for):
    config = AdminConfig(
        URL_FOR_FOR_LOGIN="OpenAPIController.docs",
        URL_FOR_FOR_LOGOUT="OpenAPIController.docs",
        REQUEST_STATISTICS=False,
    )
    app = make_app(extensions=[Jobs, Admin], middleware=[HeaderAuth], ADMIN=config)
    assert app._request_observers == []
    async with client_for(app) as client:
        page = await client.get("/admin/en/dashboard", headers={"x-user": "admin"})
        assert 'id="request-stats"' not in page.text
        res = await client.get("/admin/en/dashboard/stats", headers={"x-user": "admin"})
        assert res.status_code == 404


# ----- Pagination -------------------------------------------------------------------

from patera.admin.pagination import page_items  # noqa: E402


def test_page_items_show_edges_and_a_window_with_ellipses():
    assert page_items(10, 59) == [1, None, 8, 9, 10, 11, 12, None, 59]
    assert page_items(1, 59) == [1, 2, 3, None, 59]
    assert page_items(59, 59) == [1, None, 57, 58, 59]
    # A gap of one page shows that page rather than an ellipsis.
    assert page_items(5, 10) == [1, 2, 3, 4, 5, 6, 7, None, 10]
    assert page_items(3, 7) == list(range(1, 8))
    assert page_items(1, 1) == [1]
    assert page_items(1, 0) == []
    assert page_items(99, 5) == [1, 2, 3, 4, 5]


async def test_dashboard_log_pagination_stays_compact(app, client_for):
    for number in range(600):
        app.logger.warning(f"pagination record {number}")
    async with client_for(app) as client:
        res = await client.get(
            "/admin/en/dashboard?count=10&page=20&severity=WARNING",
            headers={"x-user": "admin"},
        )
    assert res.status_code == 200
    html = res.text
    nav = html[html.index('aria-label="Log table pagination"') :]
    nav = nav[: nav.index("</nav>")]
    assert (
        nav.count('class="page-link"') == 2 + 7 + 2
    )  # prev, 7 pages, 2 ellipses, next
    assert nav.count("…") == 2 and 'aria-current="page"' in nav
    assert "page=1&" in nav and "page=60&" in nav and "page=30&" not in nav
    assert "flex-wrap" in nav
