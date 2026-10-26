# Public API conventions

Distribution names use kebab case (`patera-taskmanager`); imports live under the
`patera` namespace (`patera.taskmanager`). Class names describe their role, so
the AI distribution exports `AiService`. Existing public names remain supported.

Use PascalCase for new classes, treating acronyms as words (`Api`, `Ai`, `Sql`),
snake_case for methods, decorators and model fields, and UPPER_SNAKE_CASE for
configuration settings. Existing names such as `DesktopUI` remain compatibility
exceptions. New config classes should use the component's full class name
followed by `Config`; the established shorter names below remain canonical.

| Distribution | Import | Entry point | Configuration |
| --- | --- | --- | --- |
| patera | patera | Patera | BaseConfig |
| patera-admin | patera.admin | AdminInterface | AdminConfig |
| patera-aiinterface | patera.aiinterface | AiService | AiServiceConfig |
| patera-apiinterface | patera.apiinterface | ApiInterface | Class/method decorators |
| patera-auth | patera.auth | Authentication | AuthenticationConfig |
| patera-caching | patera.caching | Caching | CachingConfig |
| patera-database | patera.database.sql | SqlDatabase | SqlDatabaseConfig |
| patera-desktop | patera.desktop | Desktop | DesktopConfig |
| patera-desktop-ui | patera.desktop.ui | DesktopUI | DesktopUIConfig |
| patera-email | patera.email | EmailClient | EmailConfig |
| patera-joltui | patera.joltui | PateraJoltui | JoltuiConfig |
| patera-migrate | patera.migrate | Migrate | MigrateConfig |
| patera-taskmanager | patera.taskmanager | TaskManager | TaskManagerConfig |

SQL classes intentionally live under `patera.database.sql`, leaving room for
other database implementations. `MigrateConfig` is the public migration settings
model; the former private name remains an alias for compatibility.

JoltUI is the TypeScript SPA framework authored by Marko Šterk. Use `JoltUI` in
prose, `joltui` in distribution/import names, and the established `Joltui` spelling
in Python classes. `PateraJoltui` intentionally retains its requested integration
name; `JoltuiGroupHandler` and `JoltuiRequest` describe the protocol-facing roles.

`patera[all]` means the server-extension bundle: admin, API interface,
authentication, caching, SQL, migrations, email, task manager and JoltUI. It does
not install experimental AI or desktop packages, optional cache backends, or
every optional provider. Install these explicitly with `patera[aiinterface]`,
`patera[desktop]`, or `patera[desktop-ui]` and the relevant provider extras.
Keeping this bundle's scope avoids surprising existing server installations
with desktop or machine-learning dependencies.

A core 1.0 release does not automatically change every extension's maturity.
AI, desktop and desktop-ui remain experimental until their own stability
requirements are met. No maturity or version bump is implied by these fixes.
