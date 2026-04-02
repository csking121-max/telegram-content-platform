"""
Alembic env.py — uses the sync engine for migrations.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure project root is on sys.path so "backend.*" imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import settings  # noqa: E402
from backend.database import Base  # noqa: E402

# Force-import all models so Base.metadata knows every table
import backend.models  # noqa: E402, F401

config = context.config

# Override sqlalchemy.url from our config (not from alembic.ini)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()