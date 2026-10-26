# Public API conventions

## Packages and imports

Distribution names use kebab case (`patera-taskmanager`); imports live under the `patera`
namespace (`patera.taskmanager`). Class names describe their role, so the AI distribution
exports `AiService`. Existing public names remain supported.

| Distribution | Import | Entry point | Configuration |
| --- | --- | --- | --- |
| patera | `patera` | `Patera` | `BaseConfig` |
| patera-admin | `patera.admin` | `AdminInterface` | `AdminConfig` |
| patera-aiinterface | `patera.aiinterface` | `AiService` | `AiServiceConfig` |
| patera-apiinterface | `patera.apiinterface` | `ApiInterface` | class/method decorators |
| patera-auth | `patera.auth` | `Authentication` | `AuthConfig` |
| patera-caching | `patera.caching` | `Caching` | `CachingConfig` |
| patera-database | `patera.database.sql` | `SqlDatabase` | `SqlDatabaseConfig` |
| patera-desktop | `patera.desktop` | `Desktop` | `DesktopConfig` |
| patera-desktop-ui | `patera.desktop.ui` | `DesktopUI` | `DesktopUIConfig` |
| patera-email | `patera.email` | `EmailClient` | `EmailConfig` |
| patera-joltui | `patera.joltui` | `PateraJoltui` | `JoltuiConfig` |
| patera-migrate | `patera.migrate` | `Migrate` | `MigrateConfig` |
| patera-taskmanager | `patera.taskmanager` | `TaskManager` | `TaskManagerConfig` |

SQL classes intentionally live under `patera.database.sql`, leaving room for other database
implementations.

## Naming rules

- PascalCase for new classes, treating acronyms as words (`Api`, `Ai`, `Sql`).
- snake_case for methods, decorators and model fields.
- UPPER_SNAKE_CASE for configuration settings.
- New configuration classes use the component's full class name followed by `Config`; the
  established shorter names above remain canonical.
- Existing names such as `DesktopUI` remain compatibility exceptions.

JoltUI is written `JoltUI` in prose, `joltui` in distribution and import names, and `Joltui` in
Python classes. `PateraJoltui` keeps its integration name; `JoltuiGroupHandler` and
`JoltuiRequest` describe protocol-facing roles.

## Installation bundle

`patera[all]` means the server-extension bundle: admin, API interface, authentication, caching,
SQL, migrations, e-mail, task manager and JoltUI. It does not install the experimental AI or
desktop packages, optional cache backends, or every optional provider.

## Maturity

A core 1.0 release does not automatically change every extension's maturity. The AI interface,
desktop and desktop UI packages remain experimental until their own stability requirements are
met.
