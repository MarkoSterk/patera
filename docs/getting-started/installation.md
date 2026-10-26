# Installation

Patera requires **Python 3.13 or newer**. We recommend [uv](https://docs.astral.sh/uv/).

=== "uv"

    ```sh
    uv init --python 3.13 my-app
    cd my-app
    uv add "patera[dev]"     # core + uvicorn/watchfiles for the development server
    ```

=== "pip"

    ```sh
    pip install "patera[dev]"
    ```

## Extras

Optional features are installed with extras:

| Extra | Installs | Purpose |
| --- | --- | --- |
| `prod` | granian | production server (`patera prod`) |
| `dev` | uvicorn, watchfiles, websockets | development server with auto-reload (`patera dev`) |
| `testing` | pytest, pytest-asyncio, httpx, ... | testing tools (`patera test`) |
| `database` | `patera-database` | [async SQLAlchemy integration](../extensions/database.md) |
| `migrate` | `patera-migrate` | [SQL migrations](../extensions/migrations.md) (pyway) |
| `auth` | `patera-auth` | [authentication/authorization middleware](../extensions/authentication.md) |
| `caching` | `patera-caching` | [response caching](../extensions/caching.md) (in-memory) |
| `caching-redis` / `caching-sqlite` | + redis / aiosqlite | Redis or SQLite cache backends |
| `taskmanager` | `patera-taskmanager` | [scheduled and background tasks](../extensions/taskmanager.md) (APScheduler) |
| `email` | `patera-email` | [SMTP e-mail client](../extensions/email.md) |
| `apiinterface` | `patera-apiinterface` | [declarative clients for external HTTP APIs](../extensions/apiinterface.md) |
| `joltui` | `patera-joltui` | [JoltUI server components](../extensions/joltui.md) with typed group registration |
| `admin` | `patera-admin` | [admin dashboard](../extensions/admin.md) |
| `aiinterface` | `patera-aiinterface` | [LLM chat interface](../extensions/aiinterface.md) (experimental) |
| `desktop` | `patera-desktop` | [desktop windows and packaging](../extensions/desktop.md) (experimental) |
| `desktop-ui` | `patera-desktop-ui` | [Python browser UI for desktop apps](../extensions/desktop-ui/index.md) (experimental) |
| `all` | the server extensions | admin, API interface, authentication, caching, SQL, migrations, e-mail, task manager and JoltUI |

```sh
uv add "patera[database,auth,caching]"
```

!!! note "What `patera[all]` contains"

    `patera[all]` is the server-extension bundle. It does **not** install the experimental AI or
    desktop packages, optional cache backends, or every optional provider. Install these
    explicitly with `patera[aiinterface]`, `patera[desktop]` or `patera[desktop-ui]` and the
    relevant provider extras. Keeping the bundle's scope avoids surprising existing server
    installations with desktop or machine-learning dependencies.

The production server is an extra too, `prod`, because a deployment needs it but a desktop
program does not (it embeds Uvicorn). Without it, the core's dependencies are pure Python apart
from pydantic-core.

## Packages and imports

Every extension is a separate distribution that installs into the `patera` namespace.
Distribution names use kebab case (`patera-taskmanager`); imports live under `patera`
(`patera.taskmanager`). The full map is in the [public API reference](../reference/public-api.md).

## Next step

Continue with the [quick start](quickstart.md).
