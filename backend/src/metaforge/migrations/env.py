"""Alembic environment configuration for MetaForge migrations.

This module is used by Alembic's migration runner. It is configured
programmatically by runner.py — no static alembic.ini needed.
"""

from alembic import context
from sqlalchemy import create_engine, pool


def run_migrations_offline():
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode (direct database execution)."""
    url = context.config.get_main_option("sqlalchemy.url")

    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
