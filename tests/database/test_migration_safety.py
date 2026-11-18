"""
tests/database/test_migration_safety.py
---------------------------------------
Unit tests for Alembic migration safety safeguards in database/migrations/env.py.

Validates that migrations against test-named databases fail closed unless an
explicit test-runner override (environment variable or config attribute) is present.
"""

import pytest
from alembic.config import Config

from database.migrations.env import validate_migration_target


def test_refuses_migration_against_test_database_without_override(monkeypatch):
    """Attempting to run migrations against a test-named DB without an override must raise RuntimeError."""
    monkeypatch.delenv("ALLOW_TEST_DATABASE_MIGRATIONS", raising=False)
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://postgres:postgres@localhost:5432/campus_migration_test")
    cfg.attributes.pop("allow_test_database_migrations", None)

    with pytest.raises(
        RuntimeError,
        match="Refusing to run Alembic migrations against a test database without an explicit test-runner override.",
    ):
        validate_migration_target(cfg)


@pytest.mark.parametrize("env_val", ["1", "true", "True", "yes", "YES"])
def test_allows_migration_against_test_database_with_env_var(env_val, monkeypatch):
    """Setting ALLOW_TEST_DATABASE_MIGRATIONS permits migrations against test-named DBs."""
    monkeypatch.setenv("ALLOW_TEST_DATABASE_MIGRATIONS", env_val)
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://postgres:postgres@localhost:5432/campus_migration_test")
    cfg.attributes.pop("allow_test_database_migrations", None)

    url = validate_migration_target(cfg)
    assert url.database == "campus_migration_test"


def test_allows_migration_against_test_database_with_config_attribute(monkeypatch):
    """Setting allow_test_database_migrations in Config attributes permits migrations against test DBs."""
    monkeypatch.delenv("ALLOW_TEST_DATABASE_MIGRATIONS", raising=False)
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://postgres:postgres@localhost:5432/campus_ai_app_test")
    cfg.attributes["allow_test_database_migrations"] = True

    url = validate_migration_target(cfg)
    assert url.database == "campus_ai_app_test"


def test_allows_non_test_database_without_override(monkeypatch):
    """Non-test production/development database targets do not require the test-runner override."""
    monkeypatch.delenv("ALLOW_TEST_DATABASE_MIGRATIONS", raising=False)
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://campus_user:yourpassword@localhost:5432/campus_ai")
    cfg.attributes.pop("allow_test_database_migrations", None)

    url = validate_migration_target(cfg)
    assert url.database == "campus_ai"


def test_rejects_non_postgresql_target(monkeypatch):
    """Non-PostgreSQL migration targets must be rejected."""
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", "sqlite:///campus_ai.db")

    with pytest.raises(RuntimeError, match="Alembic migrations are supported only for PostgreSQL targets."):
        validate_migration_target(cfg)


def test_rejects_empty_database_name(monkeypatch):
    """URLs without an explicit database name must be rejected."""
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://campus_user:yourpassword@localhost:5432/")

    with pytest.raises(RuntimeError, match="Alembic migration target must include an explicit database name."):
        validate_migration_target(cfg)
