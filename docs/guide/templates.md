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
