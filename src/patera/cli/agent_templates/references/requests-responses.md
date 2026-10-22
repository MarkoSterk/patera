# Requests and responses

Use the request's existing response builder: `req.res.json(data).status(201)`,
`req.res.text("ok")`, `req.res.no_content()`, or `req.res.redirect(url)`.
HTML templates require `await req.res.html("page.html", context)` with a dictionary.
`Response` is tied to an app and request; do not create a Flask-style response
with only a body argument. Headers use `set_header` and cookies use `set_cookie`.

`@consumes(MediaType.APPLICATION_JSON)` checks media type and loads the annotated
body model. Query validation is explicit. `req.validate(Model, data)` translates
Pydantic errors into request validation errors. Plain `ValidationError` elsewhere
is an application failure, not automatically a client error.

Parsing is lazy. Await `req.body()`, `req.json()`, `req.form()`, `req.files()`, or
`req.form_and_files()` as needed; do not consume ASGI receive repeatedly yourself.
`req.query_list(name)` and `await req.form_list(name)` preserve repeated values.
`UploadedFile` from
`patera` represents uploaded bytes and supports read/seek/save. Pick safe storage
names rather than trusting an upload filename; uploads are not automatically
private merely because they came through a form.

`Response[OutputModel]` declares the successful body contract. The renderer
validates/converts 2xx data before middleware completes, including output field
filtering. Error bodies are not automatically validated against the success
model. Final encoding and transmission happen later.

Use the response streaming APIs for iterators, and controller file-serving APIs
for downloads; inspect signatures in the installed version. After a response
starts, its status/headers cannot be replaced with an error response. Release
streaming resources in `finally`. A failure after database commit cannot undo
that commit.

Sources: tutorial chapters 3–4; architecture chapters 8 and 10.
