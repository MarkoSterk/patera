# Responses

Each request carries the response being built as `req.res`. Its methods return the response, so
calls can be chained:

```python
return req.res.json({"ok": True}).status(HttpStatus.CREATED).set_header("x-id", "7")
```

`Response` is tied to the application and the request: always start from `req.res` rather than
constructing a response with only a body.

## Body methods

| Method | Description |
| --- | --- |
| `json(data)` | JSON body: dicts, lists, Pydantic models and values inside them such as dates, UUIDs and decimals, encoded as Pydantic encodes them. A `str` or `bytes` raises `TypeError` (use `text()`, or `bytes(data, MediaType.APPLICATION_JSON.value)` for encoded JSON) |
| `text()`, `html_body()`, `xml()`, `csv()`, `yaml()`, `ndjson(rows)`, `bytes(data, media_type)` | other bodies |
| `await html(template, context)`, `await html_from_string(source, context)` | rendered [templates](templates.md) |
| `problem(title, detail, status, type_="about:blank", instance=None, extra=None)` | [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details |
| `stream(iterable, media_type)`, `stream_text(iterable)` | streaming responses (sync or async iterables) |
| `redirect(location, status=303)`, `no_content()` | redirects and `204` |

## Status and headers

| Method | Description |
| --- | --- |
| `status(code)` | status code (`int` or `HttpStatus`) |
| `set_header()`, `set_headers()` | headers |
| `set_cookie(name, value, max_age, path, domain, secure, http_only, same_site)` | set a cookie |
| `delete_cookie()`, `add_raw_cookie()` | delete or add a raw cookie |

Choose `secure`, `http_only` and `same_site` deliberately for session cookies.

## Response models

Annotate an endpoint with `-> Response[Model]` to validate and filter successful bodies through a
Pydantic model. See [Controllers](controllers.md#responses-and-response-models).

The renderer validates and converts 2xx data before middleware completes. Error bodies are not
validated against the success model.

## Streaming

```python
@get("/export")
async def export(self, req: Request) -> Response:
    async def rows():
        try:
            async for row in self.reports.rows():
                yield row
        finally:
            await self.reports.close()

    return req.res.ndjson(rows())
```

After the first chunk is sent, the status and headers can no longer change: an error is logged
and the connection is closed. Release resources in `finally`.

## Files

`file_response(res, path, req.headers, download_name=...)` from `patera.utilities` streams a file
from disk, with range requests, `ETag` and `304` support. `download_name` makes it a download
under any file name.

```python
from patera.utilities import file_response


@get("/reports/<int:report_id>")
async def download(self, req: Request, report_id: int) -> Response:
    path = self.reports.path_for(report_id)        # authorize before serving
    return file_response(req.res, path, req.headers, download_name=f"report-{report_id}.pdf")
```

Serve private files through an authorized controller like this, never from the static folder.

## Aborting

`abort()` and `html_abort()` raise HTTP exceptions that become error responses; see
[Exception handling](exception-handling.md#quick-aborts).
