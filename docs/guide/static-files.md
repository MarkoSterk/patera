# Static files and static pages

## Static files

Files in `STATIC_DIR` are served at `STATIC_URL` (`/static/<path:filename>`) with:

- `Content-Type` detection,
- HTTP range requests (`206 Partial Content`, useful for media),
- path traversal protection.

```html
<link rel="stylesheet" href="{{ url_for('static', filename='site.css') }}">
```

| Option | Default | Description |
| --- | --- | --- |
| `STATIC_DIR` / `STATIC_URL` | `"static"` / `"/static"` | Static files folder and URL prefix. |
| `STATIC_CONTROLLER_NAME` | `"static"` | `url_for` alias for static files. |

!!! warning "Static files are public"

    Static files bypass middleware, including [authentication](../extensions/authentication.md).
    Use the static folder only for public assets and serve private downloads through an
    authorized controller (see [Responses](responses.md#files)). Static URLs are **not**
    prefixed by `URL_PREFIX`.

In production, consider serving static files with a reverse proxy instead.

## Static pages

With `USE_STATIC_PAGES=True`, HTML files in `STATIC_PAGES_DIR` are rendered as Jinja templates
and served under `STATIC_PAGES_URL` without writing a controller:

| File | URL |
| --- | --- |
| `pages/about.html` | `/about` or `/about.html` |
| `pages/docs/intro.html` | `/docs/intro` |

Pages can extend and include each other by name. Build links with
`url_for("static_pages", page="about")`.

| Option | Default | Description |
| --- | --- | --- |
| `USE_STATIC_PAGES` | `False` | Serve HTML pages from `STATIC_PAGES_DIR`. |
| `STATIC_PAGES_DIR` / `STATIC_PAGES_URL` | `"static_pages"` / `"/"` | Static pages folder and URL prefix. |
| `STATIC_PAGES_CONTROLLER_NAME` | `"static_pages"` | `url_for` alias for pages. |

A missing page raises `StaticPageNotFound`; register a handler for that exact class to customize
the response (see [Exception handling](exception-handling.md#special-cases)).
