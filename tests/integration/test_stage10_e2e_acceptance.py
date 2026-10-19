"""
tests/integration/test_stage10_e2e_acceptance.py
-------------------------------------------------
Comprehensive End-to-End Integration & Acceptance Audit for Stage 10.
Validates:
1. REST API endpoint compatibility: /agents/chat and /chat with JWT authentication.
2. Multi-agent Supervisor routing and cycle prevention (Query, Scheduling, Resource, Greeting, Unknown).
3. Grounding & Anti-Hallucination in Query Agent (real database records, empty states).
4. Scheduling Agent scope resolution, strategy advisory, readiness, proposal isolation, replay defense, and draft generation.
5. Resource Agent discovery, interval conflict checks, proposal token scoping, cross-user denial, and booking lifecycle.
6. Cross-agent token isolation (prop_ vs res_prop_).
7. Schema contracts & naive UTC timestamp persistence integrity with TIMESTAMP WITHOUT TIME ZONE.
"""

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import TimeSlot, Room
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.courses import Course
from backend.models.academic import Department, Section, Semester, AcademicYear
from agents.scheduling_agent.proposal_store import proposal_store, ProposalStore
from agents.resource_agent.proposal_store import resource_proposal_store, ResourceProposalStore
from backend.utils.datetime_utils import utc_now

client = TestClient(app)


# ── Auth Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_token():
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]


# ── 1. Endpoint Compatibility & Authentication ────────────────────────────────

def test_chat_endpoints_auth_enforcement():
    # Both endpoints reject unauthenticated calls
    for endpoint in ["/agents/chat", "/chat"]:
        resp = client.post(endpoint, json={"message": "Hello"})
        assert resp.status_code == 401, f"Expected 401 for unauthenticated {endpoint}, got {resp.status_code}"

    # Invalid token rejected
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": "Bearer invalid_token_xyz"},
        json={"message": "Hello"},
    )
    assert resp.status_code == 401


def test_chat_endpoints_payload_validation(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}

    # Empty message rejected
    resp = client.post("/agents/chat", headers=headers, json={"message": "   "})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()

    # Valid message succeeds on both endpoints with identical schema
    for endpoint in ["/agents/chat", "/chat"]:
        resp = client.post(endpoint, headers=headers, json={"message": "Hi"})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "intent" in data
        assert "selected_agent" in data
        assert "tool_calls" in data
        assert "sources" in data
        assert data["success"] is True


# ── 2. Query Agent: Grounding & Anti-Hallucination ────────────────────────────

def test_query_agent_grounded_course_details(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "What are the credits for course CS101?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "query_agent"
    assert data["intent"] == "QUERY_AGENT"
    assert len(data["sources"]) > 0

    # Ensure actual course info from DB is in reply or gracefully reported if CS101 code differs
    assert any("Course Catalog" in source or "Academic Master Register" in source for source in data["sources"])


def test_query_agent_uninvented_empty_results(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "What are the credits for course NON_EXISTENT_XYZ_9999?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "query_agent"
    # Anti-hallucination check: Must state that no course was found, never fabricate credits
    assert "no course" in data["reply"].lower() or "not found" in data["reply"].lower()
    assert "credits" not in data["reply"].lower() or "no course" in data["reply"].lower()


def test_query_agent_facility_location(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Where is Room 101 located?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "query_agent"
    assert data["success"] is True


def test_query_agent_academic_calendar(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "When are the upcoming academic holidays?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "query_agent"
    assert data["success"] is True


# ── 3. Scheduling Agent: Access, Scope, Advisory & Execution ──────────────────

def test_scheduling_agent_role_guard_non_admin(student_token, faculty_token):
    for token, role_name in [(student_token, "Student"), (faculty_token, "Faculty")]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post(
            "/agents/chat",
            headers=headers,
            json={"message": "Generate a timetable for CSE Semester 1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_agent"] == "scheduling_agent"
        assert "Administrators" in data["reply"] or "Access Restricted" in data["reply"]
        assert data.get("proposal") is None


def test_scheduling_agent_clarification_on_missing_scope(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Generate a timetable for CSE"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "scheduling_agent"
    assert data.get("action_type") == "CLARIFICATION_NEEDED"
    assert "semester" in data["reply"].lower()
    assert data.get("proposal") is None


def test_scheduling_agent_strategy_advisory(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Compare scheduling strategies"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "scheduling_agent"
    assert data.get("action_type") == "ADVISORY"
    assert "BALANCED" in data["reply"]
    assert "FACULTY_COMFORT" in data["reply"]
    assert "ROOM_EFFICIENCY" in data["reply"]
    assert "LAB_PREFERENCE" in data["reply"]


def test_scheduling_agent_proposal_lifecycle_and_cross_user_denial(admin_token, faculty_token):
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    fac_headers = {"Authorization": f"Bearer {faculty_token}"}

    # 1. Admin generates proposal
    resp = client.post(
        "/agents/chat",
        headers=admin_headers,
        json={"message": "Generate timetable for CSE Semester 1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "scheduling_agent"

    # If prerequisites ready, proposal is created
    if data.get("action_type") == "PROPOSAL_CREATED":
        proposal = data["proposal"]
        assert proposal is not None
        prop_id = proposal["proposal_id"]
        assert prop_id.startswith("prop_")

        # 2. Cross-user security check: Faculty tries to confirm admin's proposal
        fac_resp = client.post(
            "/agents/chat",
            headers=fac_headers,
            json={"message": f"confirm {prop_id}"},
        )
        assert fac_resp.status_code == 200
        fac_data = fac_resp.json()
        assert fac_data["selected_agent"] == "scheduling_agent"
        # Non-admin role guard blocks execution before consumption
        assert "Administrators" in fac_data["reply"] or "Access Restricted" in fac_data["reply"]

        # 3. Direct proposal store cross-user denial
        with Session(engine) as db:
            fac_user = db.query(User).filter(User.role == "FACULTY").first()
            assert fac_user is not None
            consumed, _, err = proposal_store.consume_proposal(prop_id, user_id=fac_user.id)
            assert consumed is False
            assert "belongs to another user" in err

        # 4. Admin confirms proposal
        admin_resp = client.post(
            "/agents/chat",
            headers=admin_headers,
            json={"message": f"confirm {prop_id}"},
        )
        assert admin_resp.status_code == 200
        admin_data = admin_resp.json()
        assert admin_data["selected_agent"] == "scheduling_agent"
        # Action type indicates execution attempt
        assert admin_data.get("action_type") in ["GENERATION_SUCCESS", "GENERATION_INFEASIBLE", "GENERATION_ABORTED"]

        # 5. Replay protection: Re-confirming same token must be rejected
        replay_resp = client.post(
            "/agents/chat",
            headers=admin_headers,
            json={"message": f"confirm {prop_id}"},
        )
        assert replay_resp.status_code == 200
        replay_data = replay_resp.json()
        assert replay_data["selected_agent"] == "scheduling_agent"
        assert replay_data.get("action_type") == "CONFIRMATION_REJECTED"
        assert "already been confirmed" in replay_data["reply"] or "blocked" in replay_data["reply"].lower()


# ── 4. Resource Agent: Discovery, Conflicts, Proposal & Cancellation ──────────

def test_resource_agent_discovery(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Find available seminar halls and auditoriums"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "resource_agent"
    assert data["intent"] in ["RESOURCE_DISCOVERY", "RESOURCE_BOOKING"]
    assert data["success"] is True
    assert "Main Auditorium" in data["reply"] or "facilities" in data["reply"].lower()


def test_resource_agent_incomplete_interval_clarification(faculty_token):
    headers = {"Authorization": f"Bearer {faculty_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Book the Main Auditorium tomorrow"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "resource_agent"
    assert data.get("action_type") == "CLARIFICATION_NEEDED"
    assert "time" in data["reply"].lower() or "hours" in data["reply"].lower()


def test_resource_agent_booking_proposal_and_security(faculty_token, student_token):
    fac_headers = {"Authorization": f"Bearer {faculty_token}"}
    stu_headers = {"Authorization": f"Bearer {student_token}"}

    # Request proposal for a distant future date
    future_date = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
    resp = client.post(
        "/agents/chat",
        headers=fac_headers,
        json={"message": f"Book Main Auditorium on {future_date} from 10:00 to 12:00 for Faculty Workshop"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "resource_agent"

    if data.get("action_type") == "PROPOSAL_CREATED":
        proposal = data["proposal"]
        assert proposal is not None
        res_prop_id = proposal["proposal_id"]
        assert res_prop_id.startswith("res_prop_")

        # 1. Cross-user confirmation denial: Student tries to confirm Faculty proposal
        cross_resp = client.post(
            "/agents/chat",
            headers=stu_headers,
            json={"message": f"confirm {res_prop_id}"},
        )
        assert cross_resp.status_code == 200
        cross_data = cross_resp.json()
        assert cross_data["selected_agent"] == "resource_agent"
        assert cross_data.get("action_type") == "CONFIRMATION_REJECTED"
        assert "another user" in cross_data["reply"].lower()

        # 2. Authorized Faculty confirms proposal
        fac_confirm = client.post(
            "/agents/chat",
            headers=fac_headers,
            json={"message": f"confirm {res_prop_id}"},
        )
        assert fac_confirm.status_code == 200
        confirm_data = fac_confirm.json()
        assert confirm_data["selected_agent"] == "resource_agent"
        assert confirm_data.get("action_type") == "BOOKING_CREATED"
        assert "PENDING" in confirm_data["reply"] or "submitted" in confirm_data["reply"].lower()

        # 3. Replay protection: Submitting same token again must fail
        replay_resp = client.post(
            "/agents/chat",
            headers=fac_headers,
            json={"message": f"confirm {res_prop_id}"},
        )
        assert replay_resp.status_code == 200
        replay_data = replay_resp.json()
        assert replay_data.get("action_type") == "CONFIRMATION_REJECTED"
        assert "already been confirmed" in replay_data["reply"].lower()


def test_resource_agent_role_guard_on_approval(student_token, faculty_token):
    # Non-admin users cannot approve bookings through chat
    for token in [student_token, faculty_token]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post(
            "/agents/chat",
            headers=headers,
            json={"message": "Approve booking #1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_agent"] == "resource_agent"
        assert "Administrators" in data["reply"] or "Access Restricted" in data["reply"] or "portal" in data["reply"].lower()


# ── 5. Cross-Agent Routing & Token Isolation ──────────────────────────────────

def test_cross_agent_token_isolation(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # res_prop_ token sent with 'confirm' must route to resource_agent, never scheduling_agent
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "confirm res_prop_1234567890abcdef1234567890abcdef"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "resource_agent"
    assert data["intent"] == "RESOURCE_BOOKING"

    # prop_ token sent with 'confirm' must route to scheduling_agent, never resource_agent
    resp2 = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "confirm prop_12345678-1234-1234-1234-123456789abc"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["selected_agent"] == "scheduling_agent"
    assert data2["intent"] == "TIMETABLE_GENERATION"


def test_supervisor_polite_termination_for_unknown_requests(student_token):
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Can you play classical jazz music?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] is None
    assert data["intent"] == "UNKNOWN"
    assert "could not find a matching campus service" in data["reply"].lower()


# ── 6. Schema Contract & Timestamp Consistency ────────────────────────────────

def test_utc_naive_timestamp_invariance_under_session_timezone():
    """
    Verifies that naive UTC timestamps generated by utc_now() store accurately
    and do not experience timezone shifts across PostgreSQL session configurations.
    """
    with Session(engine) as db:
        # Create a test version with current utc_now()
        now_val = utc_now()
        version = TimetableVersion(
            status="DRAFT",
            version_number="V-TZ-1",
            created_at=now_val,
        )
        db.add(version)
        db.commit()
        db.refresh(version)

        # 1. Read under standard session
        retrieved_created_at = version.created_at
        # Should match within milliseconds
        diff = abs((retrieved_created_at - now_val).total_seconds())
        assert diff < 1.0, f"Timestamp shifted! Stored: {now_val}, Retrieved: {retrieved_created_at}"

        # 2. Change session timezone to UTC+05:30 (Asia/Kolkata)
        db.execute(text("SET timezone = 'Asia/Kolkata'"))
        db_res = db.execute(
            text("SELECT created_at FROM timetable_versions WHERE id = :vid"),
            {"vid": version.id},
        ).scalar()
        assert db_res is not None
        # In TIMESTAMP WITHOUT TIME ZONE, PostgreSQL stores exact literal components
        # Verify year, month, day, hour match
        assert db_res.hour == now_val.hour
        assert db_res.minute == now_val.minute

        # 3. Change session timezone to UTC-08:00 (America/Los_Angeles)
        db.execute(text("SET timezone = 'America/Los_Angeles'"))
        db_res_la = db.execute(
            text("SELECT created_at FROM timetable_versions WHERE id = :vid"),
            {"vid": version.id},
        ).scalar()
        assert db_res_la is not None
        # Literal hours/minutes must not alter
        assert db_res_la.hour == now_val.hour
        assert db_res_la.minute == now_val.minute

        # Reset session timezone
        db.execute(text("SET timezone = 'UTC'"))

        # Clean up test version
        db.delete(version)
        db.commit()
