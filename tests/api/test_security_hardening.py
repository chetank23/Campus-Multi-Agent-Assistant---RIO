"""
tests/api/test_security_hardening.py
------------------------------------
Security regression test suite for RIO-MJP:
1. Database Integrity Error Sanitization (Zero raw SQL, zero driver details to client).
2. Request / Correlation ID Propagation.
3. AI Tool Logging Security & PII Redaction.
4. Secret Scanner Behavior & Allowlist Verification.
5. Authorization & RBAC integrity preservation.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from agents.common.diagnostics import sanitize_for_logging, sanitize_log_message
from scripts.scan_secrets import RULES, is_allowlisted

client = TestClient(app)


def get_token_for(email: str, password: str = "Test@1234") -> str:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


def admin_headers(custom_req_id: str | None = None) -> dict[str, str]:
    token = get_token_for("admin@campus.edu")
    headers = {"Authorization": f"Bearer {token}"}
    if custom_req_id:
        headers["X-Request-ID"] = custom_req_id
    return headers


def student_headers() -> dict[str, str]:
    credentials = [
        ("monica.herrera@campus.edu", "Test@1234"),
        ("r23eh001@rio-mjp.test", "R23eh001#RioLocal26"),
        ("r23eh001@rio-mjp.test", "Password@123"),
    ]
    for email, pwd in credentials:
        resp = client.post("/auth/login", json={"email": email, "password": pwd})
        if resp.status_code == 200:
            return {"Authorization": f"Bearer {resp.json()['access_token']}"}
    pytest.fail("Failed to authenticate test student")


# ─── 1. Database Error Sanitization Tests ────────────────────────────────────────

def test_foreign_key_violation_sanitized_error():
    """Verify FK violations return 422, request_id, and NO raw SQL or DB exception details."""
    custom_id = "req-audit-test-fk-001"
    response = client.post(
        "/rooms/",
        headers=admin_headers(custom_req_id=custom_id),
        json={
            "building_id": 99999999,  # Non-existent FK target
            "room_number": "SEC-999",
            "capacity": 40,
            "room_type": "CLASSROOM",
        },
    )

    assert response.status_code == 422
    assert response.headers.get("X-Request-ID") == custom_id

    data = response.json()
    assert "Database integrity error" in data["detail"]
    assert data["request_id"] == custom_id
    assert data["error_code"] == "INTEGRITY_ERROR"

    # Strict check: zero driver / SQL keywords leaked
    response_raw = response.text.lower()
    assert "insert into" not in response_raw
    assert "pg_catalog" not in response_raw
    assert "violates foreign key constraint" not in response_raw
    assert "error" not in data  # No raw exception object key exposed


def test_duplicate_record_sanitized_error():
    """Verify unique constraint violations return sanitized 422 without raw schema leaks."""
    headers = admin_headers()
    dept_code = "SEC-DUP-01"

    # Create department first
    res1 = client.post(
        "/departments/",
        headers=headers,
        json={"name": "Duplicate Test Dept", "department_code": dept_code},
    )
    assert res1.status_code in (200, 201)

    # Attempt to create exact duplicate department_code
    res2 = client.post(
        "/departments/",
        headers=headers,
        json={"name": "Another Dept Same Code", "department_code": dept_code},
    )

    assert res2.status_code == 422
    data = res2.json()
    assert "Database integrity error" in data["detail"]
    assert "request_id" in data
    assert data["error_code"] == "INTEGRITY_ERROR"

    # Verify no raw SQL statements exposed
    raw_text = res2.text.lower()
    assert "insert into" not in raw_text
    assert "duplicate key value" not in raw_text
    assert "error" not in data


def test_request_id_propagation_on_success():
    """Verify request ID is assigned and returned in response headers for successful calls."""
    custom_id = "req-custom-success-12345"
    response = client.get(
        "/health",
        headers={"X-Request-ID": custom_id},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


# ─── 2. AI Tool Logging Security Tests ──────────────────────────────────────────

def test_ai_tool_argument_sanitization():
    """Verify sensitive fields, student PII, and credentials are completely redacted from tool logs."""
    dirty_args = {
        "user_id": 42,
        "course_code": "CS101",
        "password": "SuperSecretPassword123!",
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.dummy",
        "api_key": "nvapi-fake-test-key-value-here",
        "student_phone": "+91 9876543210",
        "permanent_address": "123 Academic Block, Bangalore",
        "parent_contact": "Father: +91 9876500000",
        "nested_details": {
            "auth_secret": "my-secret-signing-key",
            "cgpa": 9.8,
            "safe_metadata": "semester 7",
        },
    }

    cleaned = sanitize_for_logging(dirty_args)

    # Safe fields preserved
    assert cleaned["user_id"] == 42
    assert cleaned["course_code"] == "CS101"
    assert cleaned["nested_details"]["safe_metadata"] == "semester 7"

    # Sensitive fields redacted
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["access_token"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["student_phone"] == "[REDACTED]"
    assert cleaned["permanent_address"] == "[REDACTED]"
    assert cleaned["parent_contact"] == "[REDACTED]"
    assert cleaned["nested_details"]["auth_secret"] == "[REDACTED]"
    assert cleaned["nested_details"]["cgpa"] == "[REDACTED]"


def test_log_message_credential_redaction():
    """Verify arbitrary error strings have database connection passwords and API keys redacted."""
    raw_error = (
        "Failed to connect to postgresql+psycopg://app_user:SuperSecretDBPass@db.internal:5432/campus_ai "
        "using key nvapi-abcdef12345678901234567890."
    )
    sanitized = sanitize_log_message(raw_error)

    assert "SuperSecretDBPass" not in sanitized
    assert "nvapi-abcdef12345678901234567890" not in sanitized
    assert "[REDACTED_DB_URL]" in sanitized or "[REDACTED_USER]" in sanitized
    assert "[REDACTED_API_KEY]" in sanitized


# ─── 3. Secret Scanner Unit Tests ──────────────────────────────────────────────

def test_secret_scanner_rules_detection():
    """Verify secret scanning rules detect authentic token structures."""
    nv_match = False
    for name, rule in RULES:
        if name == "NVIDIA_API_KEY" and rule.search("NVIDIA_API_KEY=nvapi-1234567890abcdefghijklmnop"):
            nv_match = True
    assert nv_match is True

    anthropic_match = False
    for name, rule in RULES:
        if name == "ANTHROPIC_API_KEY" and rule.search("sk-ant-api03-abcdef12345678901234567890"):
            anthropic_match = True
    assert anthropic_match is True


def test_secret_scanner_allowlist_preserves_mock_fixtures():
    """Verify unit-testing mocks and env examples are safely allowlisted."""
    assert is_allowlisted(".env.example", "DATABASE_URL=postgresql://...") is True
    assert is_allowlisted("tests/test.py", "sk-ant-api03-validlookingkeyforunitmocking") is True
    assert is_allowlisted("tests/test.py", "nvapi-valid-test-key") is True


# ─── 4. Authorization & RBAC Integrity Preservation ─────────────────────────────

def test_authorization_guards_unaffected_by_error_handling():
    """Ensure unauthorized requests still receive 401/403 and never bypass RBAC guards."""
    # Unauthenticated -> 401
    res1 = client.get("/users/")
    assert res1.status_code == 401

    # Student attempting Admin route -> 403
    res2 = client.post(
        "/rooms/",
        headers=student_headers(),
        json={"building_id": 1, "room_number": "STUDENT-ATTEMPT", "capacity": 20, "room_type": "CLASSROOM"},
    )
    assert res2.status_code == 403
