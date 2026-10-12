# patera-database

Async SQLAlchemy integration for Patera: databases, request sessions, repositories and transactions. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-database
# or, with uv
uv add "patera[database]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

`patera-database` integrates async SQLAlchemy. Install a driver for your database too
(`aiosqlite` is included; e.g. `asyncpg` for PostgreSQL).

```python
# app/database.py
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from patera.database.sql import DeclarativeBaseModel, SqlDatabase, SqlDatabaseManager


class MainDb(SqlDatabase):
    __db_name__ = "main"


class Databases(SqlDatabaseManager):
    databases = [MainDb]


class Base(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "main"          # models are bound to a database by name


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
```

See the [SQL databases section of the Patera documentation](https://github.com/MarkoSterk/Patera#sql-databases) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
