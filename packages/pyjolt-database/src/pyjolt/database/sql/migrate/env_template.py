# migrations/env.py

from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# Obtain target_metadata from config
target_metadata = config.attributes.get("target_metadata", None)


def run_migrations_offline():
    """
    Run migrations in 'offline' mode.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        kwargs = {
            "connection": connection,
            "target_metadata": target_metadata,
            "compare_type": True,
            "compare_server_default": True,
        }

        if connection.dialect.name == "sqlite":
            # Force batch mode so ALTER COLUMN is emulated by
            # creating a temp table and copying data.
            kwargs["render_as_batch"] = True

        context.configure(**kwargs)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
