# Application construction

## Application layout

Keep each application class in its own file. This applies to controllers,
middleware, exception handlers, CLI controllers, extensions, services,
repositories, persistence models, Pydantic schemas, and configuration classes.
Use descriptive snake-case filenames and preserve component discovery suffixes.

Persistence models normally belong in `models/`; Pydantic request, response, and
other data schemas belong in `schemas/`. Give each model or schema its own
subpackage unless it is directly connected to others. For example, create and
response schemas for the same note may share `schemas/note/`. Sharing a package
does not mean sharing a file: each class still belongs in its own module.
Keep package `__init__.py` files for exports and intentional registration imports.
The application entry point shown below may live in `app/__init__.py` as its sole
class. Framework-required nested metadata classes remain attached to their owner.

Example structure (each package also has an `__init__.py`):

```text
app/
  __init__.py                       # App
  config.py                         # Config
  models/
    note/
      note.py                       # Note
    account/
      account.py                    # Account
  schemas/
    note/
      create_note.py                # CreateNote
      note_response.py              # NoteResponse (directly connected)
    account/
      account_response.py           # AccountResponse
  repositories/
    notes_repository.py             # NotesRepository
  services/
    notes_service.py                # NotesService
  utils/
    note_text.py                    # NoteText
  controllers/
    notes_controller.py             # NotesController
  middleware/
    request_id_middleware.py         # RequestIdMiddleware
  exceptions/
    missing_note.py                 # MissingNote
    app_exception_handler.py        # ApplicationErrors
  cli/
    notes_cli.py                    # NotesCLI
  extensions/
    audit_service.py                # AuditService
    audit_config.py                 # AuditConfig
  templates/
  static/
```

Group related utility functions in a class named for their purpose. For example,
define `excerpt` as a `@staticmethod` on `NoteText` and call it as
`NoteText.excerpt(body)`. Avoid standalone utility functions.

Import schemas into controllers and persistence models into repositories instead
of defining them alongside those classes. Import model modules explicitly so ORM
metadata is registered; creating folders alone does not discover models. These
are application organization conventions, not additional discovery mechanisms.
Apply them to new code and files being reorganized without moving unrelated
existing code solely to match the example. Short multi-class examples elsewhere
in the references illustrate relationships; split them into files in an app.

## Application entry point

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
