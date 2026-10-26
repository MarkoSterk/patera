# Reference

Look-up material for everyday use.

- [Configuration options](configuration.md): every built-in setting with its default.
- [CLI commands](cli.md): the `patera` command and the commands extensions add.
- [Public API conventions](public-api.md): packages, imports, entry points and naming rules.

## Python API

Generated from the source code and its docstrings with
[mkdocstrings](https://mkdocstrings.github.io):

- [`patera`](api/patera.md): the application, configuration, request, response and helpers.
- [`patera.controller`](api/controller.md): controllers and endpoint decorators.
- [`patera.exceptions`](api/exceptions.md): HTTP exceptions and exception handlers.
- [`patera.injectable`](api/injectable.md): dependency injection.
- [`patera.middleware`](api/middleware.md): middleware.
- [`patera.logging`](api/logging.md): logging configuration and custom sinks.
- [`patera.cli`](api/cli.md): CLI controllers.
- [`patera.testing`](api/testing.md): the test client.
