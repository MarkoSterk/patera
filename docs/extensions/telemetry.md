# Telemetry

`patera-telemetry` records what happens in each request with [OpenTelemetry](https://opentelemetry.io/):
a trace of timed steps (spans), the request-duration metric, and trace ids in your log records.
It sends them to a backend of your choice, such as Jaeger, Grafana Tempo and Prometheus, or a
hosted service.

```sh
uv add "patera[telemetry]"             # instrumentation only (opentelemetry-api)
uv add "patera-telemetry[all]"         # + SDK, OTLP/HTTP exporter, integrations
```

## Setup

```python
from patera.telemetry import Telemetry, TelemetryConfig


class Config(BaseConfig):
    ...
    TELEMETRY: TelemetryConfig = TelemetryConfig(
        SETUP_SDK=True,                  # create the exporter here (needs [sdk])
        INSTRUMENT=["sqlalchemy", "httpx"],
    )


@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Telemetry, Databases]
```

Point it at a receiver with the standard variable, for example a local Jaeger:

```sh
docker run --rm -p 16686:16686 -p 4317:4317 -p 4318:4318 jaegertracing/jaeger:latest
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 patera dev
```

and open `http://localhost:16686`.

`Telemetry` instruments the libraries when it is constructed, so it must come before an
extension that creates its clients while it is constructed. `patera-database` creates its engines
at startup, after every extension exists, so its order does not matter.

## What it records

For each HTTP request, `TelemetryMiddleware` (order `-200`, the outermost layer) records:

- **A SERVER span** named after the route, such as `GET /api/exams/<exam_id>`, or just `GET` when
  no route matched. Attributes follow the OpenTelemetry HTTP conventions: `http.request.method`,
  `url.scheme`, `url.path`, `http.route`, `http.response.status_code`, `server.address`,
  `server.port`, `network.protocol.version`, `user_agent.original`, and `code.function.name`
  for the handler.
- **Errors.** The span is marked as an error for 5xx responses, with `error.type` and the
  exception recorded. 4xx responses are not errors on a server span.
- **The `http.server.request.duration` histogram** (seconds), by method, route, status and
  scheme. Unmatched requests have no route, so the number of series stays bounded.
- **Child spans** for work done during the request, including while a response is streamed:
  database queries and outgoing HTTP calls with `INSTRUMENT`, and your own spans.

The span ends when the request is finished: the response has been sent completely, it failed, or
the client left. Responses are not changed (except with `TRACE_ID_RESPONSE_HEADER`).

An incoming W3C `traceparent` header continues the caller's trace; outgoing `httpx` calls pass
it on, so a request across several services is one trace.

## Configuration

`TELEMETRY` (`TelemetryConfig`). Options left at `None` defer to the standard `OTEL_*`
environment variables and then to the SDK defaults. Keep secrets, such as the API key of a hosted
backend, in `OTEL_EXPORTER_OTLP_HEADERS`.

| Setting | Default | |
| --- | --- | --- |
| `ENABLED` | `True` | `False` registers nothing |
| `SERVICE_NAME` / `SERVICE_VERSION` | `APP_NAME` / `VERSION` | Resource attributes |
| `ENVIRONMENT` | `None` | `deployment.environment.name` |
| `RESOURCE_ATTRIBUTES` | `{}` | Extra resource attributes |
| `SETUP_SDK` | `False` | Create the providers at startup and flush them at shutdown (needs `[sdk]`) |
| `EXPORTER` | `"otlp"` | `"otlp"`, `"console"` or `"none"` (with `SETUP_SDK`) |
| `OTLP_ENDPOINT` | `None` | Base URL, such as `http://localhost:4318` |
| `OTLP_PROTOCOL` | `"http/protobuf"` | `"grpc"` needs `patera-telemetry[grpc]` |
| `SAMPLE_RATIO` | `1.0` | Share of new traces recorded (with `SETUP_SDK`) |
| `METRICS` | `True` | Record the duration histogram |
| `METRIC_EXPORT_INTERVAL` | `60` | Seconds between metric exports |
| `EXCLUDE_PATHS` | `[]` | Glob patterns never traced, such as `/health` |
| `TRACE_STATIC` | `False` | Trace static files |
| `TRACE_UNMATCHED` | `True` | Trace 404, 405 and redirects |
| `TRUST_INCOMING_CONTEXT` | `True` | Continue incoming traces; `False` starts a new trace and links the caller's |
| `RECORD_CLIENT_ADDRESS` | `False` | Client IP address (personal data) |
| `RECORD_QUERY` | `False` | Query string |
| `CAPTURE_REQUEST_HEADERS` / `CAPTURE_RESPONSE_HEADERS` | `[]` | Header names to record |
| `REDACT_HEADERS` | `authorization`, `cookie`, `set-cookie`, `proxy-authorization` | Captured but masked |
| `RECORD_USER_ID` | `False` | `enduser.id` from `req.user` |
| `USER_ID_ATTRIBUTE` | `"id"` | Attribute of the user recorded |
| `LOG_CORRELATION` | `True` | `trace_id` and `span_id` in the request's log records |
| `INSTRUMENT` | `[]` | `"sqlalchemy"`, `"httpx"`, `"redis"` (each needs its extra) |
| `TRACE_ID_RESPONSE_HEADER` | `None` | Return the trace id in this response header |

An app exposed directly to the internet should set `TRUST_INCOMING_CONTEXT=False`, so clients
cannot attach to your traces or force sampling.

## Providers and exporters

With `SETUP_SDK=True` the extension creates the tracer and meter providers in a startup action,
so each server worker creates its own after the fork, and flushes and shuts them down at
shutdown. OpenTelemetry allows the global providers to be set once per process; providers that
are already set (by `opentelemetry-instrument` or a vendor distribution) are kept.

With `SETUP_SDK=False` (the default) Patera only instruments and uses the providers configured
elsewhere. Without any, every OpenTelemetry call is a no-op and costs almost nothing, so the
extension can be added before a backend is chosen.

## Logs

With `LOG_CORRELATION`, every log record written while a request is handled carries
`trace_id` and `span_id` in `extra`. The [JSON Lines log files](../guide/logging.md) store
`extra`, so a backend that reads them can link log lines to traces.

## Integrations

`INSTRUMENT` turns on the OpenTelemetry contrib instrumentations. They patch the libraries for
the whole process, so they apply to every engine or client, not only Patera's.

| Name | Records | Extra |
| --- | --- | --- |
| `sqlalchemy` | each SQL statement (including `patera-database` engines) | `patera-telemetry[sqlalchemy]` |
| `httpx` | outgoing HTTP calls, with trace propagation | `patera-telemetry[httpx]` |
| `redis` | Redis commands | `patera-telemetry[redis]` |

## Background work

A task started with `run_in_background` inherits the request's trace, and its spans hang under
a request span that may have ended long before. `run_traced_in_background(name, func, ...)`
records the work as a span in a trace of its own that links to the request:

```python
from patera.telemetry import run_traced_in_background

run_traced_in_background("send report", send_report, report_id)
```

## Not covered

WebSocket handlers do not pass through HTTP middleware, so they are not traced. OpenTelemetry's
logs signal is not used; log correlation adds the trace ids to Patera's own logs instead.
