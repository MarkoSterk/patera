---
name: patera
description: Build, test, and maintain Python applications and extensions using the Patera framework. Use for Patera configuration, controllers, middleware, exception handlers, CLI commands, services, desktop windows, Python browser UIs, and integrations.
---

# Patera

Use the project's installed Patera version and existing application conventions.
These references describe the APIs bundled with this Patera release; check the
installed source when upgrading. They are distilled from the Patera tutorial and
architecture books, with experimental package guidance checked against its source.

Use the concrete application type in backend controller and application-specific
extension bases, for example `Controller["App"]`, `CLIController["App"]`, and
`BaseExtension["App", AuditConfig]`. Import `TYPE_CHECKING` from `typing` and
place the application import inside `if TYPE_CHECKING:` to avoid circular
imports. Keep config models and `Inject` targets available at runtime.

Always import `HttpStatus` from `patera` when specifying or comparing an HTTP
status. Use named members in application code, examples, and tests. This includes
response builders, route decorators, exceptions, and assertions such as
`assert response.status_code == HttpStatus.OK`. Never use bare integer status codes.

Put application setting values in the project's `.env` file, including ordinary
defaults and nested extension settings. Declare custom fields on `Config` with
type annotations only. Reserve Python assignments for values that require Python
(such as `REQUEST_CLASS` and `RESPONSE_CLASS`) or are impractical to store as
literals (such as `BASE_PATH` derived from the module's location).

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
| JoltUI server components, groups, typed request bodies | [patera-joltui](references/joltui.md) |
| Experimental AI services | [AI interfaces](references/aiinterface.md) |
| Experimental desktop applications | [desktop](references/desktop.md) |
| Python/PyScript SPA pages, components, reactive lists, UI builds | [desktop UI](references/desktop-ui.md) |

## Working conventions

- Place each application class in its own file: controllers, middleware,
  exception handlers, CLI controllers, extensions, services, models, schemas,
  and other components. Keep persistence models under `models/` and Pydantic
  schemas under `schemas/`, with separate subpackages for individual models or
  schemas unless they are directly connected. Connected classes may share a
  subpackage, but each class still has its own file. See the
  [application layout](references/application.md).
- Group related utility functions in a utility class and define each with
  `@staticmethod`. Avoid standalone utility functions.
- Reference snippets sometimes show several classes together to explain their
  relationship. Split those classes into the appropriate files when creating
  application code; do not copy the combined snippet as the application layout.
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
