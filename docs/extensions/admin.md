# Admin dashboard

`patera-admin` provides a web dashboard for request statistics, logs, database models, files in
the static folder, task managers and e-mail clients.

```sh
uv add "patera[admin]"
```

## Setup

The dashboard requires an [authentication](authentication.md) middleware.

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

Register `Admin` in `app_extensions`. The dashboard is served at `/admin/<lang>/` (`en`, `de`,
`sl`, `es`), for example `/admin/en/dashboard`, plus `URL_PREFIX` when configured.

Admin looks up the extensions it manages (databases, task managers, e-mail clients) on every page
load, so their order in `app_extensions` does not matter.

## Settings

| Option | Default | Description |
| --- | --- | --- |
| `ADMIN_BASE_URL` | `"/admin"` | Base URL of the dashboard. |
| `DEFAULT_LANGUAGE` | `"en"` | `en`, `de`, `sl` or `es`. |
| `URL_FOR_FOR_LOGIN` | required | Endpoint name of your login route (the repeated `FOR` is intentional). |
| `URL_FOR_FOR_LOGOUT` | required | Endpoint name of your logout route. |
| `LOGIN_MEDIA_TYPE` | `application/json` | Media type of the login response. |
| `LOGO_URL` | `None` | Logo shown in the dashboard. |
| `SHOW_REMEMBER_ME` | `False` | Show a "remember me" option at login. |
| `SHOW_FORGOT_PASSWORD` | `False` | Show a "forgot password" option at login. |
| `REQUEST_STATISTICS` | `True` | Count requests in memory and show statistics. |

Admin does not create accounts or provide an authentication policy: login and logout are routes
your application implements.

## Permissions

Users need roles from `patera.admin.Permissions`, returned by your authentication
`roles_loader`:

| Permission | Allows |
| --- | --- |
| `ADMIN_CAN_ENTER` | opening the dashboard |
| `ADMIN_CAN_VIEW` | viewing records, logs and files |
| `ADMIN_CAN_CREATE` | creating records |
| `ADMIN_CAN_EDIT` | editing records |
| `ADMIN_CAN_DELETE` | deleting records |

Each action needs `ADMIN_CAN_ENTER` together with its own permission. A user with `ENTER` and
`VIEW` can look around but not change anything. A role named `admin` does not automatically grant
these permissions.

## Request statistics

The dashboard opens with the application's request statistics for the last 15 minutes, hour,
6 hours or 24 hours: uptime, requests per second by status class, 2xx/4xx/5xx counts, average and
95th-percentile response times, the busiest endpoints and the most frequent error statuses.
Admin counts requests in memory, so each worker process shows its own requests since it started.
Set `REQUEST_STATISTICS=False` to turn this off.

The log view reads the application's [JSON Lines log files](../guide/logging.md#log-files).

## Model forms

Form metadata derives from the model's `Meta` (`patera.database.sql.declarative_base.ModelMeta`).

- Record forms are validated with `Meta.create_validation_schema` / `update_validation_schema`
  when the model has them.
- Otherwise values are converted to the column types (an unticked checkbox is `False`, an empty
  optional field `None`), and only fields the form shows are written: fields in
  `exclude_from_create_form` / `exclude_from_update_form` cannot be set through a request.
- The `admin_create`, `admin_update` and `admin_delete` hooks implement application rules; raise
  `AdminFormError` from `patera.admin.form_values` for field errors.
- Custom form elements in `patera.admin.custom_elements` (for `Meta.custom_form_fields`) include
  `FileInput` (the hooks receive an `UploadedFile`), `DateInput` (date or date-and-time, with
  optional UTC conversion) and `LatexInput` (text with live LaTeX math preview).

!!! warning

    Generic CRUD does not know password hashing, ownership or publication rules. Exclude
    sensitive fields, provide validation schemas, and test direct requests with forged fields and
    insufficient permissions, not only the displayed form.
