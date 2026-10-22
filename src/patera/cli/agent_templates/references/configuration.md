# Configuration

`patera.BaseConfig` uses Pydantic settings. Declare typed fields and constraints
on the model, with required values lacking defaults. Environment variables use
`PATERA_` and double underscores for nesting, e.g. `PATERA_MAIL__SMTP_PORT=587`.
Declare the nested model field on application Config for environment loading.

An extension's concrete class name determines its upper-snake configuration key:
`PublicCache` reads `PUBLIC_CACHE`. Renaming the class changes that key. A nested
dictionary is validated against the component's configuration model; absent
configuration uses that model's defaults if it has no required fields.

```python
from patera import BaseConfig
from patera.caching import CachingConfig

class Config(BaseConfig):
    BASE_PATH: str = "."  # Prefer the config module's resolved directory.
    PUBLIC_CACHE: CachingConfig = CachingConfig(DURATION=30, MAX_SIZE=500)
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
