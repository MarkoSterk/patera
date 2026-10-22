# Templates, static assets, and OpenAPI

Render Jinja with `await req.res.html("page.html", {"title": "Notes"})`. Templates
live under the import-derived application root (`templates` by default). The
application loader precedes extension loaders. Extensions add folders with
`add_template_path` or namespaces with `add_template_prefix`. HTML/XML autoescape
and strict undefined variables are enabled by default. Keep escaping enabled for
untrusted values; use template `url_for` rather than hardcoded application paths.

`STATIC_DIR`/`STATIC_URL` default to `static`/`/static`; static URLs are not
automatically prefixed by `URL_PREFIX`. Static files bypass authentication
middleware: use this directory only for public assets. Serve private downloads
through an authorized controller. `USE_STATIC_PAGES` enables a separate HTML-page
controller; its templates and URL prefix have their own settings.

HTTP route metadata and body/response annotations feed OpenAPI. Use
`@consumes`, `@produces`, and `@open_api_docs`/`Descriptor` from
`patera.controller` for incoming HTTP operations, not identically named API-client
decorators. Inspect `OPEN_API` and related BaseConfig fields for document/UI
locations and settings. Verify the generated schema after changing annotations.

For a custom serializer or renderer, inspect the application serializer registry
and renderer API rather than bypassing response preparation. Body validation,
serialization and ASGI send are different stages.

Sources: tutorial chapters 3–4; architecture chapters 8 and 11.
