"""
tests/conftest.py
-----------------
Pytest configuration and session-scoped database isolation fixture for RIO-MJP.

Safety & Isolation Rules:
1. Tests require an explicitly configured TEST_DATABASE_URL.
   There is NO fallback to DATABASE_URL under any circumstances.
2. The test database target must comply with the test-database naming rule:
   its database name must explicitly include 'test' (e.g., 'campus_ai_test').
3. The test database target must not match the application database configured in DATABASE_URL.
4. If safety checks pass, search_path=test_schema is configured for test isolation.
5. All destructive DDL/DML (schema drop/create, Alembic migrations, seeding) executes
   strictly against the validated test database.
"""

from __future__ import annotations

import os
import subprocess
import sys
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command


def validate_and_build_test_urls(
    test_url: str | None = None,
    app_url: str | None = None,
) -> tuple[str, str]:
    """
    Validates TEST_DATABASE_URL against strict isolation rules.
    Fails closed if the configuration is missing, invalid, or unsafe.
    Returns (clean_test_url, test_url_with_schema).
    Never exposes passwords or sensitive credentials in error messages.

    Parameters:
        test_url: Optional explicit test URL (for testing/isolated validation).
                  If None, loaded from TEST_DATABASE_URL environment variable.
        app_url:  Optional explicit application URL (for testing/comparison).
                  If None, loaded from DATABASE_URL environment variable.
    """
    if test_url is None:
        load_dotenv(".env")
        test_raw = os.environ.get("TEST_DATABASE_URL", "").strip()
    else:
        test_raw = test_url.strip()

    if not test_raw:
        raise RuntimeError(
            "CRITICAL CONFIGURATION ERROR: TEST_DATABASE_URL is not set or is blank.\n"
            "To prevent accidental modification of development or production data, "
            "RIO-MJP tests require an explicitly configured TEST_DATABASE_URL.\n"
            "Fallback to DATABASE_URL is strictly forbidden.\n"
            "Please configure TEST_DATABASE_URL in .env pointing to a dedicated test database "
            "(e.g., postgresql+psycopg://user:password@localhost:5432/campus_ai_test)."
        )

    try:
        test_target = make_url(test_raw)
    except Exception:
        raise RuntimeError(
            "CRITICAL CONFIGURATION ERROR: TEST_DATABASE_URL could not be parsed as a valid database URL."
        )

    # Dialect check: must be a PostgreSQL URL
    backend_name = test_target.get_backend_name()
    if backend_name not in ("postgresql", "postgres"):
        raise RuntimeError(
            f"CRITICAL CONFIGURATION ERROR: TEST_DATABASE_URL must be a PostgreSQL database URL (found '{backend_name}')."
        )

    test_db = (test_target.database or "").strip()
    if not test_db:
        raise RuntimeError(
            "CRITICAL CONFIGURATION ERROR: TEST_DATABASE_URL does not specify a target database name."
        )

    # Naming Rule: Target database name must explicitly contain 'test'
    test_db_lower = test_db.lower()
    if "test" not in test_db_lower:
        raise RuntimeError(
            f"CRITICAL SAFETY VIOLATION: Test database target '{test_db}' violates the test database naming rule.\n"
            f"The target database name must explicitly include 'test' (e.g., 'campus_ai_test' or 'test_campus_ai') "
            f"to prevent running tests against non-test databases."
        )

    # Comparison with application DATABASE_URL
    if app_url is None:
        app_raw = os.environ.get("DATABASE_URL", "").strip()
    else:
        app_raw = app_url.strip()

    if app_raw:
        try:
            app_target = make_url(app_raw)
            app_db = (app_target.database or "").strip()

            test_host = (test_target.host or "localhost").lower()
            app_host = (app_target.host or "localhost").lower()
            test_port = test_target.port or 5432
            app_port = app_target.port or 5432

            # Check 1: Identical host + port + database
            if test_host == app_host and test_port == app_port and test_db_lower == app_db.lower():
                raise RuntimeError(
                    f"CRITICAL SAFETY VIOLATION: TEST_DATABASE_URL targets the same database ('{test_db}') "
                    f"on host '{test_host}:{test_port}' as the application DATABASE_URL.\n"
                    f"Tests must use a separate, dedicated test database."
                )

            # Check 2: Identical database name regardless of host
            if test_db_lower == app_db.lower():
                raise RuntimeError(
                    f"CRITICAL SAFETY VIOLATION: TEST_DATABASE_URL database name '{test_db}' matches "
                    f"the application database name in DATABASE_URL.\n"
                    f"Tests must use a distinct test database name (e.g., '{test_db}_test')."
                )
        except RuntimeError:
            # Preserve explicit safety violations raised above.
            raise
        except Exception as exc:
            # A malformed application URL makes database identity impossible
            # to establish; fail closed rather than allowing destructive tests.
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: DATABASE_URL could not be parsed as a valid database URL."
            ) from exc

    # The test fixture drops and recreates test_schema and the seed script
    # truncates tables. Keep the entire pytest lifecycle local-only; an opt-in
    # here would still be unsafe because test setup performs destructive DDL.
    host = (test_target.host or "localhost").strip().lower()
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if host not in local_hosts:
        raise RuntimeError(
            "CRITICAL SAFETY VIOLATION: TEST_DATABASE_URL points to a remote database host. "
            "Automated tests are restricted to local PostgreSQL databases because setup "
            "drops and recreates test_schema and seeds test data. Remote test databases "
            "cannot be enabled through an environment-variable override."
        )

    # Clean URL (without search_path options, for dropping/creating the schema)
    clean_url = test_target.render_as_string(hide_password=False)

    # URL with search_path=test_schema query parameter
    query_params = dict(test_target.query)
    existing_opts = query_params.get("options", "")
    if "search_path" not in existing_opts:
        if existing_opts:
            query_params["options"] = f"{existing_opts} -csearch_path=test_schema".strip()
        else:
            query_params["options"] = "-csearch_path=test_schema"

    url_with_schema = test_target.set(query=query_params).render_as_string(hide_password=False)

    return clean_url, url_with_schema


# Module-level cached URLs for active test session
_TEST_URLS: tuple[str, str] | None = None


def get_test_urls() -> tuple[str, str]:
    """
    Retrieves or initializes the validated test database URLs.
    Sets os.environ["DATABASE_URL"] to the validated test database with test_schema.
    """
    global _TEST_URLS
    if _TEST_URLS is None:
        clean_url, schema_url = validate_and_build_test_urls()
        os.environ["DATABASE_URL"] = schema_url
        _TEST_URLS = (clean_url, schema_url)
    return _TEST_URLS


def pytest_configure(config):
    """
    Pytest session configuration hook.
    Runs BEFORE any test modules are collected or imported.
    Validates TEST_DATABASE_URL and configures DATABASE_URL to point to test_schema.
    Fails closed immediately if TEST_DATABASE_URL is missing or unsafe.
    """
    get_test_urls()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Session-scoped test fixture that initializes the isolated test_schema
    in the validated test database.
    """
    clean_url, schema_url = get_test_urls()

    # Keep engine references available for cleanup even when setup fails midway.
    engine = None
    schema_engine = None
    try:
        # 1. Connect exclusively to the validated test database to manage test_schema
        engine = create_engine(clean_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS test_schema CASCADE"))
            conn.execute(text("CREATE SCHEMA test_schema"))

        # 2. Run Alembic migrations against the test database with search_path=test_schema
        alembic_cfg = Config("alembic.ini")
        # This explicit marker is required by env.py for test-database migrations.
        alembic_cfg.attributes["allow_test_database_migrations"] = True
        # ConfigParser treats percent signs as interpolation markers; escape them in URLs.
        alembic_cfg.set_main_option("sqlalchemy.url", schema_url.replace("%", "%%"))
        command.upgrade(alembic_cfg, "head")

        # 3. Seed test data explicitly into the test database
        sub_env = os.environ.copy()
        sub_env["DATABASE_URL"] = schema_url
        sub_env["TEST_DATABASE_URL"] = schema_url
        sub_env["TEST_PASSWORD"] = "Test@1234"
        sub_env["IS_TEST_RUN"] = "true"

        subprocess.run(
            [sys.executable, "scripts/seed_database.py", "--dataset", "A"],
            env=sub_env,
            check=True,
        )

        # 4. Reset sequences for test_schema
        schema_engine = create_engine(schema_url)
        with schema_engine.begin() as conn:
            conn.execute(text("""
                DO $$
                DECLARE
                    seq RECORD;
                BEGIN
                    FOR seq IN
                        SELECT c.relname as seq_name, t.relname as table_name
                        FROM pg_class c
                        JOIN pg_depend d ON d.objid = c.oid
                        JOIN pg_class t ON d.refobjid = t.oid
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relkind = 'S' AND n.nspname = 'test_schema'
                    LOOP
                        EXECUTE 'SELECT setval(''test_schema.' || seq.seq_name || ''', COALESCE((SELECT MAX(id) FROM test_schema.' || seq.table_name || '), 1), true)';
                    END LOOP;
                END $$;
            """))

        yield
    finally:
        if schema_engine is not None:
            schema_engine.dispose()
        if engine is not None:
            engine.dispose()
