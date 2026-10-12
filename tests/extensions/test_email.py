from __future__ import annotations

from email.message import EmailMessage

import pytest

from patera.email import EmailClient, EmailConfig

pytestmark = pytest.mark.integration


class FakeSMTP:
    def __init__(self):
        self.messages: list[EmailMessage] = []
        self.calls: list[str] = []

    async def __aenter__(self):
        self.calls.append("connect")
        return self

    async def __aexit__(self, *exc):
        self.calls.append("quit")

    async def starttls(self):
        self.calls.append("starttls")

    async def login(self, user, password):
        self.calls.append(f"login:{user}:{password}")

    async def send_message(self, msg):
        self.messages.append(msg)


class Mailer(EmailClient):
    pass


@pytest.fixture
def mailer(make_app, monkeypatch):
    app = make_app(
        extensions=[Mailer],
        files={
            "templates/mail/welcome.txt": "Welcome {{ name }}! {{ url_for('static', filename='a.png') }}"
        },
        MAILER=EmailConfig(
            SENDER_NAME_OR_ADDRESS="App <noreply@example.com>",
            SMTP_SERVER="smtp.example.com",
            SMTP_PORT=587,
            USERNAME="user",
            PASSWORD="pass",
            USE_TLS=True,
        ),
    )
    client = app.get_extension(Mailer)
    fake = FakeSMTP()
    monkeypatch.setattr(client, "get_client", lambda: fake)
    return client, fake


async def test_send_email_with_attachments(mailer):
    client, fake = mailer
    await client.send_email(
        ["a@example.com", "b@example.com"],
        "Hello",
        "Body text",
        attachments={"report.csv": b"a,b\n1,2"},
    )
    assert fake.calls == ["connect", "starttls", "login:user:pass", "quit"]
    msg = fake.messages[0]
    assert msg["To"] == "a@example.com, b@example.com"
    assert msg["From"] == "App <noreply@example.com>"
    attachments = list(msg.iter_attachments())
    assert attachments[0].get_filename() == "report.csv"
    assert attachments[0].get_content() == b"a,b\n1,2"


async def test_messages_have_date_and_message_id(mailer):
    from email.utils import parsedate_to_datetime

    client, fake = mailer
    await client.send_email("a@example.com", "One", "Body")
    await client.send_email("a@example.com", "Two", "Body")
    first, second = fake.messages
    assert parsedate_to_datetime(first["Date"]).tzinfo is not None
    assert first["Message-ID"].startswith("<")
    assert first["Message-ID"].endswith("@example.com>")
    assert first["Message-ID"] != second["Message-ID"]


async def test_send_email_with_template(mailer):
    client, fake = mailer
    await client.send_email_with_template(
        "c@example.com", "Hi", "mail/welcome.txt", context={"name": "Ana"}
    )
    assert fake.messages[0].get_content().strip() == "Welcome Ana! /static/a.png"


def test_missing_configuration_is_reported(make_app):
    with pytest.raises(TypeError):
        make_app(extensions=[Mailer])


def test_get_client_uses_configuration(make_app):
    app = make_app(
        extensions=[Mailer],
        MAILER={
            "SENDER_NAME_OR_ADDRESS": "a@b.c",
            "SMTP_SERVER": "smtp.local",
            "SMTP_PORT": "25",
        },
    )
    smtp = app.get_extension(Mailer).get_client()
    assert smtp.hostname == "smtp.local"
    assert smtp.port == 25


HTML_FILES = {
    "templates/mail/welcome.html": (
        "<html><head><style>p { color: red }</style></head><body>"
        "<h1>Welcome {{ name }}</h1>"
        "<p>Open <a href='https://app.example/start'>your dashboard</a>.</p>"
        "<ul><li>One</li><li>Two</li></ul></body></html>"
    ),
    "templates/mail/welcome_text.txt": "Welcome {{ name }} (text version)",
    "templates/mail/fragment.j2": "<p>Hi {{ name }}</p>",
}


@pytest.fixture
def html_mailer(make_app, monkeypatch):
    app = make_app(
        extensions=[Mailer],
        files=HTML_FILES,
        MAILER=EmailConfig(
            SENDER_NAME_OR_ADDRESS="noreply@example.com",
            SMTP_SERVER="smtp.example.com",
            SMTP_PORT=465,
        ),
    )
    client = app.get_extension(Mailer)
    fake = FakeSMTP()
    monkeypatch.setattr(client, "get_client", lambda: fake)
    return client, fake


def _parts(msg: EmailMessage) -> dict[str, str]:
    return {
        part.get_content_type(): part.get_content()
        for part in msg.walk()
        if part.get_content_maintype() == "text"
    }


async def test_html_template_is_sent_as_html_with_text_alternative(html_mailer):
    client, fake = html_mailer
    await client.send_email_with_template(
        "a@example.com", "Welcome", "mail/welcome.html", context={"name": "Ana"}
    )
    msg = fake.messages[0]
    assert msg.get_content_type() == "multipart/alternative"
    parts = _parts(msg)
    assert "<h1>Welcome Ana</h1>" in parts["text/html"]
    text = parts["text/plain"]
    assert "Welcome Ana" in text
    assert "your dashboard (https://app.example/start)" in text
    assert "- One\n- Two" in text
    assert "<" not in text and "color: red" not in text


async def test_html_template_with_its_own_text_template(html_mailer):
    client, fake = html_mailer
    await client.send_email_with_template(
        "a@example.com",
        "Welcome",
        "mail/welcome.html",
        context={"name": "Ana"},
        text_template_path="mail/welcome_text.txt",
    )
    parts = _parts(fake.messages[0])
    assert parts["text/plain"].strip() == "Welcome Ana (text version)"
    assert "<h1>Welcome Ana</h1>" in parts["text/html"]


async def test_is_html_overrides_the_file_extension(html_mailer):
    client, fake = html_mailer
    await client.send_email_with_template(
        "a@example.com", "Hi", "mail/fragment.j2", context={"name": "Bo"}, is_html=True
    )
    assert _parts(fake.messages[0])["text/html"].strip() == "<p>Hi Bo</p>"


async def test_html_with_attachments_is_mixed(html_mailer):
    client, fake = html_mailer
    await client.send_email(
        "a@example.com",
        "Report",
        "See the report.",
        attachments={"report.csv": b"a,b"},
        html="<p>See the <b>report</b>.</p>",
    )
    msg = fake.messages[0]
    assert msg.get_content_type() == "multipart/mixed"
    assert set(_parts(msg)) == {"text/plain", "text/html"}
    assert [a.get_filename() for a in msg.iter_attachments()] == ["report.csv"]


async def test_template_context_is_not_modified(html_mailer):
    client, _ = html_mailer
    context = {"name": "Ana"}
    await client.send_email_with_template(
        "a@example.com", "Hi", "mail/welcome.html", context=context
    )
    assert context == {"name": "Ana"}


def _mailer_app(make_app, **settings):
    return make_app(
        extensions=[Mailer],
        MAILER={
            "SENDER_NAME_OR_ADDRESS": "a@b.c",
            "SMTP_SERVER": "smtp.local",
            "SMTP_PORT": 465,
            **settings,
        },
    )


def test_implicit_tls_client(make_app):
    smtp = _mailer_app(make_app, USE_SSL=True).get_extension(Mailer).get_client()
    assert smtp.use_tls is True
    assert smtp._start_tls_on_connect is False


def test_plain_and_starttls_clients_do_not_use_implicit_tls(make_app):
    for settings in ({}, {"USE_TLS": True}):
        smtp = _mailer_app(make_app, **settings).get_extension(Mailer).get_client()
        assert smtp.use_tls is False


def test_tls_modes_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        EmailConfig(
            SENDER_NAME_OR_ADDRESS="a@b.c",
            SMTP_SERVER="smtp.local",
            SMTP_PORT=465,
            USE_TLS=True,
            USE_SSL=True,
        )


async def test_implicit_tls_does_not_issue_starttls(make_app, monkeypatch):
    client = _mailer_app(make_app, USE_SSL=True).get_extension(Mailer)
    fake = FakeSMTP()
    monkeypatch.setattr(client, "get_client", lambda: fake)
    await client.send_email("x@example.com", "Hi", "Body")
    assert "starttls" not in fake.calls


def test_html_to_text():
    from patera.email.email_client import html_to_text

    assert (
        html_to_text("<p>Lines<br>split &amp; joined</p><script>x()</script>")
        == "Lines\nsplit & joined"
    )
