"""
database/migrations/env.py
---------------------------
Alembic environment — reads DATABASE_URL from .env and uses the full
SQLAlchemy metadata from backend/models so that autogenerate picks up every
table, FK, CHECK constraint, and composite index.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# ── Path setup ───────────────────────────────────────────────────────────────
# Add the repo root to sys.path so `from backend.models import ...` works when
# alembic is run from the repo root (the directory containing alembic.ini).
ROOT = Path(__file__).resolve().parent.parent.parent  # RIO-MJP/
sys.path.insert(0, str(ROOT))

# ── Load .env ────────────────────────────────────────────────────────────────
load_dotenv(ROOT / ".env")

# ── Import all models so their tables are registered in Base.metadata ────────
from backend.models import metadata as target_metadata  # noqa: E402

# ── Alembic config object ────────────────────────────────────────────────────
config = context.config

# If a specific URL was already configured (e.g. by test runner via alembic_cfg.set_main_option),
# preserve it; otherwise read DATABASE_URL from the environment.
custom_url = config.get_main_option("sqlalchemy.url")
if not custom_url:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required for migrations.")
    # Escape percent signs because ConfigParser interprets them as interpolation markers.
    escaped_database_url = database_url.replace(chr(37), chr(37) * 2)
    config.set_main_option("sqlalchemy.url", escaped_database_url)

# Validate the final migration target regardless of whether it came from
# alembic.ini, an explicit Alembic Config override, or DATABASE_URL.
from sqlalchemy.engine import make_url  # noqa: E402

migration_url = config.get_main_option("sqlalchemy.url")
try:
    parsed_migration_url = make_url(migration_url)
except Exception as exc:
    raise RuntimeError("Alembic migration target must be a valid SQLAlchemy URL.") from exc

if parsed_migration_url.get_backend_name() not in ("postgresql", "postgres"):
    raise RuntimeError("Alembic migrations are supported only for PostgreSQL targets.")

if not (parsed_migration_url.database or "").strip():
    raise RuntimeError("Alembic migration target must include an explicit database name.")

# Set up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include CHECK constraints and named constraints in autogenerate
        include_schemas=False,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (requires a live database connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Render CHECK constraints in autogenerate diffs
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
