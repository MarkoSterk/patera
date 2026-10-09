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
