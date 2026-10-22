# Application construction

Define configuration in `app/config.py`:

```python
from pathlib import Path
from patera import BaseConfig

class Config(BaseConfig):
    BASE_PATH: str = str(Path(__file__).resolve().parent)
```

Define the application in `app/__init__.py`:

```python
from patera import Patera, app
from .config import Config

@app(__name__, configs=Config)
class App(Patera[Config]):
    pass
```

`@app` supplies runtime metadata; the generic argument supplies typing. Keep the
configuration class consistent. The import name determines the application root
for discovery, templates, and static files; `BASE_PATH` is not a URL prefix.
Use `Config.URL_PREFIX` for controller URLs.

Typical discoverable paths under `app/` are `api/greeting_api.py`,
`controllers/page_controller.py`, `middleware/request_id_middleware.py`,
`exceptions/app_exception_handler.py`, `cli/tools_cli.py`, and
`logging/audit_logger.py`. Include package `__init__.py` files. Configured discovery
folder lists can extend these conventions. Models and services require imports.

List infrastructure classes in `app_extensions = [YourService]` so they are
constructed even if nothing injects them. Injection can construct them earlier;
list order alone does not establish all dependency ordering.

`@on_startup` and `@on_shutdown` from `patera` mark application methods.
Application hooks run alphabetically; extension callbacks registered with
`add_on_startup_method` are appended after application startup hooks. Do not assume
a database is connected in an application startup hook. Construction is distinct
from ASGI lifespan; simply calling `App()` does not start resource hooks.

Sources: tutorial chapters 1–2; architecture chapters 3–4 and 9.
