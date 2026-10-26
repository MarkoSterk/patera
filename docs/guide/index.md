# Guide

The guide explains every feature of the core `patera` package. Each page can be read on its own;
read them in order for a complete tour.

## Fundamentals

- [Configuration](configuration.md): typed settings from classes and environment variables.
- [The application class](application.md): lifecycle hooks, extensions and useful members.
- [Services and dependency injection](dependency-injection.md): singleton services and `Inject[...]`.

## HTTP

- [Controllers and routing](controllers.md): endpoints, route parameters, validation and hooks.
- [Requests](requests.md): headers, bodies, forms, files and request context.
- [Responses](responses.md): JSON, templates, streaming, files, cookies and response models.
- [Exception handling](exception-handling.md): handler classes and default error responses.
- [Middleware](middleware.md): wrap the request chain.
- [CORS](cors.md): cross-origin settings, globally and per endpoint.
- [WebSockets](websockets.md): socket endpoints in controllers.

## Content

- [Templates](templates.md): Jinja2 rendering.
- [Static files and static pages](static-files.md): files and controller-less HTML pages.
- [OpenAPI](openapi.md): generated specification and Swagger UI.

## Operations

- [Logging](logging.md): Loguru, JSON Lines log files, custom sinks and request observers.
- [Command line interface](cli.md): CLI controllers and commands.
- [Testing](testing.md): `PateraTestClient` and `patera test`.
- [Coding agents](coding-agents.md): generate instructions for Codex and Claude.

## Building on Patera

- [Custom extensions](custom-extensions.md): write reusable services and packages.
