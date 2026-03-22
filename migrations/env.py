# File: migrations/env.py
"""
Alembic migration environment.
Uses synchronous engine for migrations — this is the correct approach
since Alembic's upgrade/downgrade commands are CLI tools, not async servers.
Works reliably on Windows, macOS and Linux.
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make sure the project root is on sys.path so 'src' can be imported
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import all models so Alembic can see the full schema
from src.db.database import Base
import src.db.database  # noqa: F401 — registers all ORM models

config = context.config

# Wire up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """
    Return the sync (non-async) database URL for Alembic.
    Alembic uses a regular synchronous engine — we strip the async driver prefix.
    """
    # Prefer DATABASE_URL env var if set
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url", "")

    # Strip async driver prefixes → use plain sync drivers
    url = url.replace("sqlite+aiosqlite:///", "sqlite:///")
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    # Default fallback
    if not url:
        url = "sqlite:///./trading.db"

    return url


def run_migrations_offline() -> None:
    """
    Offline mode — generate a .sql migration script without connecting to the DB.
    Run with: alembic upgrade head --sql
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online mode — connect to the database and apply migrations directly.
    Run with: alembic upgrade head
    """
    url = get_url()

    # Build a plain synchronous engine
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite-specific: needed to support ALTER TABLE operations
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
