# Configuration

Configuration classes inherit from `patera.BaseConfig`, a
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) model:

```python
import os

from patera import BaseConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)   # required
    APP_NAME: str = "My app"
    SECRET_KEY: str                              # required, e.g. from PATERA_SECRET_KEY
```

Settings are validated when the application is constructed, so set environment values before
constructing the app.

## Environment variables

Every option can be overridden with an environment variable prefixed with `PATERA_`. Nested
values use `__` as separator:

```sh
PATERA_DEBUG=false
PATERA_PORT=8080
PATERA_CORS_ALLOW_ORIGINS='["https://app.example.com"]'
PATERA_MAIN_DB__DATABASE_URI=postgresql+asyncpg://user:pass@db/app
```

Values usually live in `.env` files; see [Running the application](../getting-started/running.md#environment-files)
for which file each command loads.

## Extension and component settings

Extension, service and middleware settings are regular fields of your config class, named after
the **class** in UPPER_SNAKE_CASE: `MainDb` → `MAIN_DB`, `PublicCache` → `PUBLIC_CACHE`.
Renaming the class changes the key.

```python
from patera import BaseConfig
from patera.caching import CachingConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    PUBLIC_CACHE: CachingConfig = CachingConfig(DURATION=30, MAX_SIZE=500)
```

A nested dictionary is validated against the component's configuration model; an absent
configuration uses the model's defaults if it has no required fields. See
[Services and dependency injection](dependency-injection.md#service-configuration).

### Settings from the environment only

The values can live in `.env` (or the environment) instead of the class. Declare a settings
model **without a value**, and it is built from the variables that are set, with the model's
defaults for the rest:

```python
class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    MAIN_DB: SqlDatabaseConfig    # PATERA_MAIN_DB__DATABASE_URI must be set
    DESKTOP: DesktopConfig        # every field has a default; PATERA_DESKTOP__WIDTH=1200 changes one
```

A required field that no variable sets stops the application at startup with its name
(`MAIN_DB.DATABASE_URI: Field required`). A model declared with a value in the class
(`MAIN_DB: SqlDatabaseConfig = SqlDatabaseConfig(...)`) keeps that value as its default, and
variables change single fields of it.

## Reading configuration

- `app.configs.NAME`: typed attribute access.
- `app.get_conf("NAME", default)`: supports dotted paths into nested models and dictionaries,
  for example `app.get_conf("MAIN_DB.DATABASE_URI")` or `app.get_conf("DEFAULT_LOGGER.LEVEL")`.
- The `ConfigVar` descriptor in controllers and services:

```python
from typing import TYPE_CHECKING

from patera.injectable import ConfigVar

if TYPE_CHECKING:
    from app import App


@path("/greetings")
class GreetingApi(Controller["App"]):
    app_name: str = ConfigVar("APP_NAME")
    label: str = ConfigVar("GREETING_LABEL", "Greetings")   # with default
```

`ConfigVar` reads settings through the application lookup path; it does not declare a required
Pydantic field.

## Built-in options

The most important built-in options are `BASE_PATH`, `APP_NAME`, `VERSION`, `DEBUG`, `HOST`,
`PORT`, `URL_PREFIX`, `MAX_CONTENT_LENGTH` and the `CORS_*`, `OPEN_API*`, `TEMPLATES_*` and
`STATIC_*` groups. The complete table with defaults is in the
[configuration reference](../reference/configuration.md).

!!! tip "Use the model, not guesses"

    `patera.configuration_base.BaseConfig` is the source of truth for exact field names and
    defaults. See the [API reference](../reference/api/patera.md#patera.BaseConfig).
