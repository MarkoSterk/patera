# patera-admin

Admin dashboard for Patera applications: logs, databases, files, e-mail and task managers. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-admin
# or, with uv
uv add "patera[admin]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

`patera-admin` provides a web dashboard for logs, database models, files in the static folder, task
managers and e-mail clients. It requires an [authentication](https://github.com/MarkoSterk/Patera#authentication) middleware: users need
the roles from `patera.admin.Permissions` (`ADMIN_CAN_ENTER` plus
`ADMIN_CAN_VIEW`/`CREATE`/`EDIT`/`DELETE`).

```python
from patera.admin import AdminConfig, AdminInterface


class Admin(AdminInterface):
    MANAGED_MODELS = [Note]


class Config(BaseConfig):
    ...
    ADMIN: AdminConfig = AdminConfig(
        URL_FOR_FOR_LOGIN="AuthApi.login", URL_FOR_FOR_LOGOUT="AuthApi.logout",
    )
```

See the [Admin dashboard section of the Patera documentation](https://github.com/MarkoSterk/Patera#admin-dashboard) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
