# Configuration

`patera.BaseConfig` uses Pydantic settings. Declare typed fields and constraints
on the model, with required values lacking defaults. Environment variables use
`PATERA_` and double underscores for nesting, e.g. `PATERA_MAIL__SMTP_PORT=587`.
Put scalar values, lists, and nested extension settings in the project's `.env`
file. Declare custom fields on application `Config` with annotations only.
Assign values directly only for Python objects such as `REQUEST_CLASS` and
`RESPONSE_CLASS`, or for values more practical to compute, such as `BASE_PATH`.

An extension's concrete class name determines its upper-snake configuration key:
`PublicCache` reads `PUBLIC_CACHE`. Renaming the class changes that key. A nested
dictionary is validated against the component's configuration model; absent
configuration uses that model's defaults if it has no required fields.

```python
from pathlib import Path

from patera import BaseConfig
from patera.caching import CachingConfig

class Config(BaseConfig):
    BASE_PATH: str = str(Path(__file__).resolve().parent)
    PUBLIC_CACHE: CachingConfig
```

In the project's `.env` file:

```dotenv
PATERA_PUBLIC_CACHE__DURATION=30
PATERA_PUBLIC_CACHE__MAX_SIZE=500
```

`ConfigVar` from `patera.injectable` reads settings through the application lookup
path; it does not declare a required Pydantic field. Dotted lookup can traverse
both models and dictionaries, e.g. `DEFAULT_LOGGER.LEVEL`.

Core groups include request size limits, `DEBUG`, templates/static paths,
`URL_PREFIX`, `STRICT_SLASHES`, OpenAPI, CORS, logger models, and discovery folders.
Inspect `patera.configuration_base.BaseConfig` for exact fields and defaults.
Use model fields rather than guessed setting names. Settings are validated when
the application is constructed; set environment values before construction.

Sources: tutorial chapters 2 and 22; architecture chapter 5.
