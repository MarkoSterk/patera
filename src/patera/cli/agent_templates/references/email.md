# Email

Install `patera-email`. Subclass `EmailClient` from `patera.email`, e.g. `Mail`,
register or inject it, and declare `MAIL: EmailConfig` with SMTP settings.

```python
from patera.email import EmailClient

class Mail(EmailClient):
    pass

```

Put the SMTP settings in `.env`:

```dotenv
PATERA_MAIL__SENDER_NAME_OR_ADDRESS="App <app@example.test>"
PATERA_MAIL__SMTP_SERVER=localhost
PATERA_MAIL__SMTP_PORT=1025
```

`await mail.send_email(recipient, subject, body)` accepts one address string or a
list. A comma-separated string is not split. Attachments map filenames to bytes.
Use the client's template APIs for rendered mail, inspecting their signatures.

`USE_TLS` means STARTTLS (commonly 587); `USE_SSL` means implicit TLS (commonly
465). They are mutually exclusive. Credentials are used only when both username
and password are supplied; declare them through environment-backed settings.
Each send creates its SMTP connection.

Use a capture service or fake client in tests. A send is an external side effect
that a database rollback cannot undo. Use a durable outbox and idempotent retry
strategy when delivery must track committed business operations. Scheduling an
in-memory task alone does not guarantee delivery after a crash.

Sources: tutorial chapters 12 and 19; architecture chapter 18.
