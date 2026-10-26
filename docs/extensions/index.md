# Extensions

Optional features ship as separate packages that install into the `patera` namespace. Each one is
a [service](../guide/dependency-injection.md): you subclass it, configure it through a config
field named after your subclass, and register it in `App.app_extensions` (or inject it).

```python
@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Databases, PublicCache, Jobs]
```

## Official packages

| Package | Import | Entry point | Configuration | Install |
| --- | --- | --- | --- | --- |
| [SQL databases](database.md) | `patera.database.sql` | `SqlDatabase`, `SqlDatabaseManager` | `SqlDatabaseConfig` | `patera[database]` |
| [Migrations](migrations.md) | `patera.migrate` | `Migrate` | `MigrateConfig` | `patera[migrate]` |
| [Authentication](authentication.md) | `patera.auth` | `Authentication` | `AuthConfig` | `patera[auth]` |
| [Caching](caching.md) | `patera.caching` | `Caching` | `CachingConfig` | `patera[caching]` |
| [Task manager](taskmanager.md) | `patera.taskmanager` | `TaskManager` | `TaskManagerConfig` | `patera[taskmanager]` |
| [E-mail](email.md) | `patera.email` | `EmailClient` | `EmailConfig` | `patera[email]` |
| [External APIs](apiinterface.md) | `patera.apiinterface` | `ApiInterface` | class/method decorators | `patera[apiinterface]` |
| [JoltUI](joltui.md) | `patera.joltui` | `PateraJoltui` | `JoltuiConfig` | `patera[joltui]` |
| [Admin dashboard](admin.md) | `patera.admin` | `AdminInterface` | `AdminConfig` | `patera[admin]` |
| [AI interface](aiinterface.md) :material-flask-outline: | `patera.aiinterface` | `AiService` | `AiServiceConfig` | `patera[aiinterface]` |
| [Desktop](desktop.md) :material-flask-outline: | `patera.desktop` | `Desktop` | `DesktopConfig` | `patera[desktop]` |
| [Desktop UI](desktop-ui/index.md) :material-flask-outline: | `patera.desktop.ui` | `DesktopUI` | `DesktopUIConfig` | `patera[desktop-ui]` |

:material-flask-outline: Experimental: not yet ready for production use; the API may change in
any release.

`patera[all]` installs the server extensions: admin, API interface, authentication, caching,
SQL, migrations, e-mail, task manager and JoltUI. It does not install the experimental packages
or optional backends such as `caching-redis` and `caching-sqlite`.

Each extension package requires Python 3.13 or newer and a compatible `patera` core (`>=0.121`).

## Writing your own

See [Custom extensions](../guide/custom-extensions.md).
