"""
tests/api/test_chat_endpoint.py
-------------------------------
REST API integration tests for Chat endpoints:
- POST /agents/chat and POST /chat
- Authentication verification (401 without Bearer token)
- Message length validation (empty -> 400, oversized -> 422)
- Structured response schema validation
- Safe handling of out-of-scope scheduling and booking intents
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def student_token():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_token():
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


def test_chat_unauthenticated_rejected():
    resp = client.post("/agents/chat", json={"message": "What is my next class?"})
    assert resp.status_code == 401

    resp_alt = client.post("/chat", json={"message": "What is my next class?"})
    assert resp_alt.status_code == 401


def test_chat_empty_message_rejected(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}

    # Empty string fails pydantic min_length=1 with 422
    resp_empty = client.post("/agents/chat", headers=headers, json={"message": ""})
    assert resp_empty.status_code == 422

    # Whitespace-only string returns 400
    resp_whitespace = client.post("/agents/chat", headers=headers, json={"message": "   "})
    assert resp_whitespace.status_code == 400


def test_chat_oversized_message_rejected(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    oversized = "A" * 2000
    resp = client.post("/agents/chat", headers=headers, json={"message": oversized})
    assert resp.status_code == 422


def test_chat_student_query_success(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post("/agents/chat", headers=headers, json={"message": "What is my next class?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert data["success"] is True
    assert isinstance(data["sources"], list)


def test_chat_scheduling_scope_clarification(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/agents/chat", headers=headers, json={"message": "Generate new semester timetable"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] in ("TIMETABLE_GENERATION", "SCOPE_RESOLUTION")
    assert "Academic Scope Clarification Needed" in data["reply"] or "Which department" in data["reply"]


def test_chat_unsupported_booking_response(faculty_token):
    headers = {"Authorization": f"Bearer {faculty_token}"}
    resp = client.post("/agents/chat", headers=headers, json={"message": "Book the seminar hall for tomorrow"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "RESOURCE_BOOKING"
    assert "not enabled in Stage 9B" in data["reply"]



def test_chat_compat_endpoint(student_token):
    # Tests /chat alternate endpoint
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post("/chat", headers=headers, json={"message": "Where is Room 101?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert data["success"] is True


def test_chat_classroom_count_query(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/agents/chat", headers=headers, json={"message": "HOW MANY classrooms AVAILABLE"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Campus Room Inventory" in data["reply"] or "Active Facilities" in data["reply"]
    assert "Room Type" in data["reply"]

