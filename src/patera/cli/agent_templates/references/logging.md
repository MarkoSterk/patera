# Logging and observation

Use `self.app.logger` in services/controllers. Configure `DEFAULT_LOGGER` and
`LOG_FILES` through their typed configuration models; inspect installed fields
for rotation, retention, paths and levels. Relative log paths are resolved from
the application root. Custom discoverable loggers use `logging/*_logger.py`.
Import `LoggerBase` and `logger` from `patera.logging`, subclass the base and
mark it with `@logger("audit")`. Override sink getters as needed; `configs_model`
selects the settings model, read under the class's upper-snake configuration key.
Loguru is process-global, so simultaneous applications share its sinks. Built-in
request logging includes the query string before middleware; redact at the logging
boundary or avoid sensitive URL parameters rather than relying on middleware.

For HTTP metrics, a service can register an observer during `init()`:

```python
from patera import Service, RequestRecord

class RequestMetrics(Service):
    def init(self):
        self.app.add_request_observer(self.observe)

    def observe(self, record: RequestRecord):
        if record.duration > 1:
            self.app.logger.warning(f"Slow request: {record.method} {record.path}")
```

List the service in `app_extensions`. Observers include static requests and route
failures that middleware misses, and run after the response is sent. Records
include method, path, matched route or None, sent status, start time, and duration
in seconds. Keep callbacks quick; failures are logged and skipped. Do not expect
an observer to change the response. Avoid credentials and private bodies in logs.

Sources: tutorial chapter 5; architecture chapter 12.
