# patera-migrate

SQL migrations for Patera databases, based on pyway. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-migrate
# or, with uv
uv add "patera[migrate]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

`patera-migrate` adds SQL migrations based on [pyway](https://github.com/jasondcamp/pyway). Add the
`Migrate` mixin to the database class:

```python
from patera.migrate import Migrate

class MainDb(SqlDatabase, Migrate):
    __db_name__ = "main"
```

See the [Migrations section of the Patera documentation](https://github.com/MarkoSterk/Patera#migrations) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
