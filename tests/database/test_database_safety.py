"""Unit tests for test-database target validation.

These tests exercise URL validation only. They do not connect to PostgreSQL,
create schemas, run migrations, or invoke destructive seed/reset scripts.
"""

import importlib.util
from pathlib import Path

import pytest


_CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"
_SPEC = importlib.util.spec_from_file_location("rio_test_conftest", _CONFTEST_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Could not load tests/conftest.py for database safety tests.")
_CONFTEST = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CONFTEST)
validate_and_build_test_urls = _CONFTEST.validate_and_build_test_urls


LOCAL_TEST_URL = "postgresql+psycopg://tester:secret@localhost:5432/campus_ai_test"


def test_accepts_distinct_local_postgres_test_database(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    clean_url, schema_url = validate_and_build_test_urls(
        LOCAL_TEST_URL,
        "postgresql+psycopg://app:secret@localhost:5432/campus_ai",
    )

    assert clean_url == LOCAL_TEST_URL
    assert "test_schema" in schema_url


@pytest.mark.parametrize("test_url", ["", "   ", None])
def test_rejects_missing_test_database_url(test_url, monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="TEST_DATABASE_URL is not set"):
        validate_and_build_test_urls(test_url, "postgresql+psycopg://app:secret@localhost/campus_ai")


def test_rejects_malformed_test_database_url(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="could not be parsed"):
        validate_and_build_test_urls("not-a-database-url", "")


def test_rejects_non_postgresql_test_database(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="must be a PostgreSQL"):
        validate_and_build_test_urls("sqlite:///campus_ai_test.db", "")


def test_rejects_test_database_without_explicit_database_name(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="does not specify a target database name"):
        validate_and_build_test_urls("postgresql+psycopg://tester:secret@localhost", "")


def test_rejects_database_name_without_test_marker(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="violates the test database naming rule"):
        validate_and_build_test_urls(
            "postgresql+psycopg://tester:secret@localhost:5432/campus_ai",
            "",
        )


def test_rejects_same_database_name_as_application_even_on_different_host(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="database name .* matches"):
        validate_and_build_test_urls(
            "postgresql+psycopg://tester:secret@localhost:5432/campus_ai_test",
            "postgresql+psycopg://app:secret@db.example.com:5432/CAMPUS_AI_TEST",
        )


def test_rejects_remote_test_database_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="Remote test databases are blocked by default"):
        validate_and_build_test_urls(
            "postgresql+psycopg://tester:secret@db.example.com:5432/campus_ai_test",
            "postgresql+psycopg://app:secret@localhost:5432/campus_ai",
        )


def test_allows_remote_test_database_only_with_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("ALLOW_REMOTE_TEST_DATABASE", "true")

    clean_url, schema_url = validate_and_build_test_urls(
        "postgresql+psycopg://tester:secret@db.example.com:5432/campus_ai_test",
        "postgresql+psycopg://app:secret@localhost:5432/campus_ai",
    )

    assert "db.example.com" in clean_url
    assert "test_schema" in schema_url


def test_rejects_malformed_application_database_url(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL could not be parsed"):
        validate_and_build_test_urls(LOCAL_TEST_URL, "not-a-database-url")
