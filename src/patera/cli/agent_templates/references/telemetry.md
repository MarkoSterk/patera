# Telemetry (OpenTelemetry)

Install `patera-telemetry` (`patera[telemetry]`; `patera-telemetry[all]` adds the SDK, the
OTLP/HTTP exporter and the integrations). Register `Telemetry` in `app_extensions` (before any
extension that creates instrumented clients during construction; database engines are created
at startup, so order does not matter for them) and configure `TELEMETRY: TelemetryConfig`.

```python
TELEMETRY: TelemetryConfig = TelemetryConfig(
    SETUP_SDK=True,                     # create providers at startup, flush at shutdown
    INSTRUMENT=["sqlalchemy", "httpx"],
    EXCLUDE_PATHS=["/health"],
)
```

Each HTTP request becomes a SERVER span (`GET /route/<param>`, or just the method when no
route matched) and an `http.server.request.duration` measurement. 5xx marks the span as an
error; 4xx does not. Log records written during a request carry `trace_id` and `span_id`.

Send data with the standard `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_HEADERS`
variables; never put API keys in config. `SETUP_SDK=False` (default) uses providers
configured elsewhere and is a no-op without them. Global providers can be set once per
process: in tests install in-memory providers once, or run SETUP_SDK checks in a subprocess.

Client address, query string, user id and headers are opt-in (`RECORD_*`, `CAPTURE_*`);
`REDACT_HEADERS` masks secrets. Use `TRUST_INCOMING_CONTEXT=False` for apps exposed directly
to the internet. Static files are not traced unless `TRACE_STATIC`. WebSockets are not traced.
Use `run_traced_in_background(name, func, ...)` for background work that should get its own
trace linked to the request.
