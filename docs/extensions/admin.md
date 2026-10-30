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
- Use `Meta.custom_form_fields` to replace generated inputs with the
  [custom form fields](#custom-form-fields) below.

!!! warning

    Generic CRUD does not know password hashing, ownership or publication rules. Exclude
    sensitive fields, provide validation schemas, and test direct requests with forged fields and
    insufficient permissions, not only the displayed form.

## Custom form fields

Import the built-in fields from `patera.admin.custom_elements`. Set
`Meta.custom_form_fields` to a list of field instances, with each `name` matching a
model field (or a field declared in `Meta.add_to_form`).

| Field | Purpose and options |
| --- | --- |
| `TagsInput` | Tag entry: press Enter to add a tag and use its remove button to delete it. Empty and duplicate tags are ignored. Accepts `placeholder`. |
| `PasswordInput` | Masked text input that is never prefilled with a stored value. `autocomplete` defaults to `"new-password"`. |
| `SelectInput` | Single selection with `options` supplied as a mapping of values to labels or a sequence of `(value, label)` pairs. Submitted values use normal column-type conversion. |
| `SummernoteEditor` | Rich text editor. Configure `features`, `height`, and `upload_url`. The default features are `headings`, `font`, and `alignment`; supplying `upload_url` also enables images. |
| `FileInput` | File upload. `accept` takes MIME types or extensions, as a string or sequence; `max_size` is a limit in bytes checked by the browser. |
| `DateInput` | Date picker, or date and time with `include_time=True`. Supports `min` and `max`. With `include_time=True, utc=True`, displays timestamps in the viewer's local time and submits UTC. |
| `LatexInput` | Text with live LaTeX math preview. Multiline by default; set `multiline=False` for a single line. Supports `rows` (default `4`), `maxlength`, and `preview_label` (default `"Preview"`). |

For example, add this metadata to a model that defines `tags`, `body`, `attachment`,
`published_at`, and `formula` fields:

```python
from patera.admin.custom_elements import (
    DateInput,
    FileInput,
    LatexInput,
    SummernoteEditor,
    TagsInput,
)


class Meta(Base.Meta):
    custom_form_fields = [
        TagsInput(name="tags", placeholder="Type a tag and press Enter"),
        SummernoteEditor(name="body", height=300),
        FileInput(name="attachment", accept=[".pdf"], max_size=5 * 1024 * 1024),
        DateInput(name="published_at", include_time=True, utc=True),
        LatexInput(name="formula", multiline=False, maxlength=2000),
    ]
```

All fields accept `label`, `required`, `disabled`, and HTML customization through
`classes`, `attributes`, `data_attributes`, `aria_attributes`, and `styles`.

### Submitted values

- `PasswordInput` submits the entered text. Hash it in your admin hook before
  storage. An empty input submits an empty string; handle that explicitly in
  update hooks if it should preserve the current password. Exclude password/hash
  columns from tables and use a separate `Meta.add_to_form` field when appropriate.
- `SelectInput` restricts the visible choices, but your validation schema or admin
  hook must enforce allowed values for direct requests as well.
- `TagsInput` submits a JSON array encoded as text, such as `'["python", "web"]'`.
  Parse and validate that text in your validation schema or admin hook if the model
  stores a list. Existing values can be JSON arrays or comma-separated text.
- `SummernoteEditor` submits HTML text. An image upload requires your application
  to provide the endpoint specified by `upload_url`.
- `FileInput` passes a `patera.UploadedFile` to the admin hooks, which decide how to
  store it. When no file is selected, the field is omitted so an update preserves
  the current value. Validate uploads on the server as well; `accept` and
  `max_size` only constrain the browser.
- `DateInput` uses the normal column-type conversion for `Date`, `DateTime`, or
  string columns. `utc=True` requires `include_time=True`.
- `LatexInput` submits the original text and uses normal column-type conversion.
  Write inline math as `$...$`, display math as `$$...$$`, and a literal dollar
  sign as `\$`. The preview uses the bundled Temml renderer, loaded only on pages
  containing this input.

### Password and select example

Declare the options directly in the model's metadata:

```python
from patera.admin.custom_elements import PasswordInput, SelectInput


class Meta(Base.Meta):
    add_to_form = {"new_password": str}
    custom_form_fields = [
        PasswordInput(name="new_password", required=False),
        SelectInput(name="status", options={"draft": "Draft", "published": "Published"}),
    ]
```

Here `status` is a model column. Consume `new_password` in the model's admin hook
and store its hash in your password column.
