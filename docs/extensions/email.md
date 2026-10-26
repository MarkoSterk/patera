# E-mail

`patera-email` is an async SMTP e-mail client with Jinja templates.

```sh
uv add "patera[email]"
```

## Setup

```python
from patera.email import EmailClient, EmailConfig


class Mailer(EmailClient):
    pass


class Config(BaseConfig):
    ...
    MAILER: EmailConfig = EmailConfig(
        SENDER_NAME_OR_ADDRESS="My app <noreply@example.com>",
        SMTP_SERVER="smtp.example.com", SMTP_PORT=587,
        USERNAME="user", PASSWORD="secret", USE_TLS=True,
    )
```

Register `Mailer` in `app_extensions` or inject it. Keep credentials in environment-backed
settings, for example `PATERA_MAILER__PASSWORD`.

## Sending

```python
mailer: Inject[Mailer]
...
await self.mailer.send_email(
    "ana@example.com", "Report", "See attachment", attachments={"report.csv": data},
)
await self.mailer.send_email_with_template(
    ["a@example.com"], "Welcome", "mail/welcome.txt", context={"name": "Ana"},
)
```

- The recipient is one address string or a list; a comma-separated string is not split.
- Attachments map file names to bytes.
- Each send opens its own SMTP connection.

## TLS

- `USE_TLS` means STARTTLS (commonly port 587).
- `USE_SSL` means implicit TLS (commonly port 465).
- They are mutually exclusive. Credentials are used only when both username and password are set.

## Reliability

A send is an external side effect that a database rollback cannot undo. When delivery must track
committed business operations, use a durable outbox and an idempotent retry strategy; an
in-memory background task alone does not guarantee delivery after a crash. In tests, use a
capture service or a fake client.
