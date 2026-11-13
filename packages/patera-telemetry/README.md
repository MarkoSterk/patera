# patera-telemetry

OpenTelemetry tracing, metrics and log correlation for Patera. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-telemetry            # instrumentation only (opentelemetry-api)
pip install "patera-telemetry[all]"     # + SDK, OTLP/HTTP exporter, integrations
# or, with uv
uv add "patera[telemetry]"
```

Extras: `sdk` (SDK and OTLP/HTTP exporter), `grpc` (OTLP/gRPC exporter), `sqlalchemy`,
`httpx`, `redis` (instrumentations), and `all` (everything except `grpc`).

Requires Python 3.13 or newer and a Patera core with `req.on_finish` and the middleware
opt-in flags.

## Usage

```python
from patera.telemetry import Telemetry, TelemetryConfig

class Config(BaseConfig):
    TELEMETRY: TelemetryConfig = TelemetryConfig(SETUP_SDK=True, INSTRUMENT=["sqlalchemy"])

@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Telemetry, Databases]
```

Each HTTP request becomes a SERVER span named after its route, with the
`http.server.request.duration` metric and `trace_id`/`span_id` in the request's log records.
Set `OTEL_EXPORTER_OTLP_ENDPOINT` to send them to a collector, Jaeger or a hosted backend.
Without `SETUP_SDK`, the extension uses the providers configured elsewhere; without any, it is a
no-op.

Privacy defaults: client addresses, query strings and headers are not recorded unless enabled,
and captured `authorization`, `cookie`, `set-cookie` and `proxy-authorization` values are masked.

See the [telemetry documentation](https://github.com/MarkoSterk/Patera/blob/main/docs/extensions/telemetry.md).
