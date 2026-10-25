---
name: patera
description: Build, test, and maintain Python applications and extensions using the Patera framework. Use for Patera configuration, controllers, middleware, exception handlers, CLI commands, services, desktop windows, Python browser UIs, and integrations.
---

# Patera

Use the project's installed Patera version and existing application conventions.
These references describe the APIs bundled with this Patera release; check the
installed source when upgrading. They are distilled from the Patera tutorial and
architecture books, with experimental package guidance checked against its source.

Read only the references relevant to the task:

| Task | Reference |
| --- | --- |
| Create an app, discovery, lifespan | [application](references/application.md) |
| Settings, environment, component config | [configuration](references/configuration.md) |
| Services and injection | [dependency injection](references/dependency-injection.md) |
| Routes, controller hooks, input validation | [controllers and routing](references/controllers-routing.md) |
| Bodies, uploads, response types, streaming | [requests and responses](references/requests-responses.md) |
| Request context, ordering, CORS | [middleware](references/middleware.md) |
| Exception mapping and failure responses | [error handlers](references/error-handlers.md) |
| Application terminal commands | [CLI controllers](references/cli-controllers.md) |
| Socket handlers | [WebSockets](references/websockets.md) |
| HTML, static files, API documentation | [templates, static files, OpenAPI](references/templates-static-openapi.md) |
| Build a custom extension | [extensions](references/extensions.md) |
| Logging and request observers | [logging](references/logging.md) |
| HTTP and lifecycle tests | [testing](references/testing.md) |
| Servers, environment files, production | [deployment](references/deployment.md) |
| SQL models, repositories, transactions | [database](references/database.md) |
| Versioned SQL migrations | [migrations](references/migrations.md) |
| Users, roles, sessions | [authentication](references/authentication.md) |
| Admin interface and permissions | [admin](references/admin.md) |
| SMTP and mail templates | [email](references/email.md) |
| Scheduled and background work | [task manager](references/taskmanager.md) |
| Response caching | [caching](references/caching.md) |
| Declarative HTTP clients | [API interfaces](references/apiinterface.md) |
| JolUI server components, groups, typed request bodies | [patera-joltui](references/joltui.md) |
| Experimental AI services | [AI interfaces](references/aiinterface.md) |
| Experimental desktop applications | [desktop](references/desktop.md) |
| Python/PyScript SPA pages, components, reactive lists, UI builds | [desktop UI](references/desktop-ui.md) |

## Working conventions

- Keep request-specific data out of shared controller, middleware, and service
  attributes. Use locals, explicit arguments, or `patera.ctx.current_request`.
- Match discovery folders **and filenames**; a class in an arbitrary module is
  not automatically registered. Extensions can register components explicitly.
- Keep extension `init()` synchronous and cheap. Register resources there and
  acquire/release them through lifecycle hooks. CLI and socket lifecycles differ
  from HTTP: consult their references before reusing HTTP decorators.
- Optional integrations are separate distributions. Add only dependencies the
  application uses; do not assume installing core installs every extension.
- Verify changed behavior through relevant tests, including failure paths and
  resource cleanup. Use async-context-managed `PateraTestClient` for HTTP tests.
