# patera-email

Async SMTP e-mail client with Jinja templates for Patera. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-email
# or, with uv
uv add "patera[email]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

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

See the [E-mail section of the Patera documentation](https://github.com/MarkoSterk/Patera#e-mail) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
