# Templates

Templates are rendered with [Jinja2](https://jinja.palletsprojects.com) (async, auto-escaping for
HTML/XML) from `TEMPLATES_DIR` (default `templates`, relative to the application package):

```python
@get("/")
async def index(self, req: Request) -> Response:
    return await req.res.html("index.html", {"title": "Home"})
```

```html
<h1>{{ title }}</h1>
<a href="{{ url_for('UserApi.list_users') }}">Users</a>
<link rel="stylesheet" href="{{ url_for('static', filename='site.css') }}">
```

`await req.res.html_from_string(source, context)` renders a template from a string.

## Template context

Besides your context, templates receive:

| Name | Value |
| --- | --- |
| `app` | the application |
| `request` | the current request |
| `url_for` | URL building, as on the application |
| `attribute` | `getattr` |
| `len` | `len` |
| `flashed_messages` | current context's `(message, status)` pairs; empty when none were added |

## Flash messages

Applications, controllers, extensions, and middleware share the same synchronous method:

```python
self.flash_message("Changes saved.", "success")
self.flash_message("Welcome!")  # status defaults to None
```

Messages appear in insertion order in every template, including templates rendered directly
through `app.jinja_environment`:

```jinja
{% for message, status in flashed_messages %}
    <span class="{{ status or '' }}">{{ message }}</span>
{% endfor %}
```

`flashed_messages` behaves as an empty list when there are no messages, so loops and
`{% if flashed_messages %}` need no special handling. Reading it does not consume messages.
Each request has its own list; child contexts share their parent's messages. Messages last
only for the current context and do not survive redirects. Calling `flash_message` without
an active context raises `RuntimeError`.

## Settings

| Option | Default | Description |
| --- | --- | --- |
| `TEMPLATES_DIR` | `"templates"` | Template folder, relative to `BASE_PATH`. |
| `TEMPLATES_STRICT` | `True` | Undefined template variables raise errors. |
| `AUTO_RELOAD` | `True` | Reload changed templates. |

## Template folders

The application's own template folder always takes precedence over folders added by extensions
or static pages. Extensions add folders with `app.add_template_path(path)` or namespaced folders
with `app.add_template_prefix(prefix, path)`.

!!! warning

    Keep auto-escaping enabled for untrusted values and use `url_for` rather than hard-coded
    application paths, so `URL_PREFIX` is respected.

## HTML error pages

`html_abort("errors/404.html", HttpStatus.NOT_FOUND, {"id": user_id})` renders a template as an
error response; see [Exception handling](exception-handling.md#quick-aborts).
