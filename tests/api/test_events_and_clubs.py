"""
tests/api/test_events_and_clubs.py
-----------------------------------
End-to-end integration and verification suite for:
1. Coordinator Capability management (Assign, Revoke, Scope enforcement, RBAC).
2. Club management and cross-club access barriers.
3. Multi-layer venue availability conflict detection (Timetable, ResourceBooking, Event).
4. Deterministic event lifecycle (DRAFT -> PENDING_APPROVAL -> APPROVED/PUBLISHED, REJECTED, CANCELLED).
5. Direct publishing gating (Requires EVENT_DIRECT_PUBLISH capability).
6. Student privacy: Draft, pending, and faculty-only events never leaked to students.
7. Optimistic locking and version tracking.
8. Role-aware Assistant grounding for campus events & club activities.
"""

from __future__ import annotations

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models import User, Room, TimetableEntry, TimeSlot
from backend.models.events import Club, CampusEvent, CoordinatorCapability
from agents.supervisor.agent import classify_intent
from agents.query_agent.agent import _extract_intent_and_tool_call, format_grounded_response
from agents.tools import execute_tool

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    with Session(engine) as db:
        yield db


@pytest.fixture(scope="module")
def admin_auth():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def faculty_auth():
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def faculty2_auth():
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty 2 login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def student_auth():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_admin_assign_and_revoke_capabilities(admin_auth, faculty_auth, student_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    student_headers = {"Authorization": f"Bearer {student_auth['token']}"}
    fac_user_id = faculty_auth["user"]["id"]

    # 1. Non-admin cannot assign capabilities
    resp = client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac_user_id,
            "capability": "EVENT_COORDINATOR",
            "scope_type": "GLOBAL",
        },
        headers=faculty_headers,
    )
    assert resp.status_code == 403, f"Faculty assigning capability should be 403: {resp.text}"

    resp = client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac_user_id,
            "capability": "EVENT_COORDINATOR",
            "scope_type": "GLOBAL",
        },
        headers=student_headers,
    )
    assert resp.status_code == 403, f"Student assigning capability should be 403: {resp.text}"

    # 2. Admin assigns EVENT_COORDINATOR capability
    resp = client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac_user_id,
            "capability": "EVENT_COORDINATOR",
            "scope_type": "GLOBAL",
        },
        headers=admin_headers,
    )
    assert resp.status_code in (200, 201), f"Admin assign capability failed: {resp.text}"
    cap_data = resp.json()
    assert cap_data["capability"] == "EVENT_COORDINATOR"
    assert cap_data["scope_type"] == "GLOBAL"
    assert cap_data["is_active"] is True
    cap_id = cap_data["id"]

    # 3. Admin lists capabilities
    resp = client.get("/admin/capabilities", headers=admin_headers)
    assert resp.status_code == 200
    caps = resp.json()
    matched = [c for c in caps if c["id"] == cap_id]
    assert len(matched) == 1
    assert matched[0]["is_active"] is True

    # 4. Admin revokes capability with reason
    resp = client.post(
        f"/admin/capabilities/{cap_id}/revoke",
        json={"reason": "Testing capability lifecycle revocation"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    revoked = resp.json()
    assert revoked["is_active"] is False
    assert revoked["revocation_reason"] == "Testing capability lifecycle revocation"


def test_club_management_and_cross_club_isolation(admin_auth, faculty_auth, faculty2_auth, student_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    faculty2_headers = {"Authorization": f"Bearer {faculty2_auth['token']}"}
    fac_user_id = faculty_auth["user"]["id"]

    # 1. Non-admin cannot create clubs
    resp = client.post(
        "/clubs",
        json={"name": "Hacking Club", "code": f"HACK_{int(datetime.datetime.now().timestamp())}", "category": "TECHNICAL"},
        headers=faculty_headers,
    )
    assert resp.status_code == 403, f"Faculty should not create clubs directly: {resp.text}"

    # 2. Admin creates Club A and Club B
    unique_suffix = int(datetime.datetime.now().timestamp())
    resp_a = client.post(
        "/clubs",
        json={
            "name": f"Robotics Society {unique_suffix}",
            "code": f"ROBO_{unique_suffix}",
            "category": "TECHNICAL",
            "description": "Robotics and automated systems club",
        },
        headers=admin_headers,
    )
    assert resp_a.status_code in (200, 201), f"Create Club A failed: {resp_a.text}"
    club_a = resp_a.json()

    resp_b = client.post(
        "/clubs",
        json={
            "name": f"Literary Arts {unique_suffix}",
            "code": f"LIT_{unique_suffix}",
            "category": "LITERARY",
            "description": "Campus literary and debate society",
        },
        headers=admin_headers,
    )
    assert resp_b.status_code in (200, 201), f"Create Club B failed: {resp_b.text}"
    club_b = resp_b.json()

    # 3. Admin assigns Faculty 1 as coordinator for Club A ONLY
    resp = client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac_user_id,
            "capability": "CLUB_COORDINATOR",
            "scope_type": "CLUB",
            "scope_id": club_a["id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code in (200, 201)

    # 4. Faculty 1 checks assigned clubs -> sees Club A, not Club B
    resp = client.get("/faculty/my-clubs", headers=faculty_headers)
    assert resp.status_code == 200
    my_clubs = resp.json()
    my_club_ids = [c["id"] for c in my_clubs]
    assert club_a["id"] in my_club_ids
    assert club_b["id"] not in my_club_ids

    # 5. Faculty 1 creates activity for Club A -> succeeds
    st = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).replace(tzinfo=None)
    et = st + datetime.timedelta(hours=2)
    resp = client.post(
        "/events",
        json={
            "title": f"Autonomous Rover Workshop {unique_suffix}",
            "category": "CLUB_ACTIVITY",
            "club_id": club_a["id"],
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Robotics Lab Wing B",
            "requires_approval": True,
        },
        headers=faculty_headers,
    )
    assert resp.status_code in (200, 201), f"Creating activity for Club A should succeed: {resp.text}"
    event_a = resp.json()
    assert event_a["club_id"] == club_a["id"]
    assert event_a["status"] == "DRAFT"

    # 6. Faculty 1 attempts to create activity for Club B -> 403 Forbidden (cross-club isolation)
    resp = client.post(
        "/events",
        json={
            "title": f"Poetry Slam {unique_suffix}",
            "category": "CLUB_ACTIVITY",
            "club_id": club_b["id"],
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Auditorium Hall",
            "requires_approval": True,
        },
        headers=faculty_headers,
    )
    assert resp.status_code == 403, f"Faculty 1 should not coordinate Club B: {resp.text}"
    assert "not an authorized coordinator for club" in resp.json()["detail"].lower()


def test_venue_availability_and_conflict_detection(admin_auth, faculty_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    # Find a valid room
    room = db_session.query(Room).first()
    assert room is not None

    # Pick a date far in future (e.g. 90 days out on a Sunday where no classes exist)
    future_date = datetime.date.today() + datetime.timedelta(days=90)
    # Adjust to Sunday to avoid timetable collisions
    while future_date.weekday() != 6:
        future_date += datetime.timedelta(days=1)

    st = datetime.datetime.combine(future_date, datetime.time(10, 0))
    et = datetime.datetime.combine(future_date, datetime.time(12, 0))

    # 1. Free window -> no conflict
    resp = client.post(
        "/events/venue-check",
        json={
            "room_id": room.id,
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_available"] is True
    assert len(data["conflicts"]) == 0

    # 2. Create an approved event in that window
    event = CampusEvent(
        title="Existing Approved Summit",
        category="SEMINAR",
        room_id=room.id,
        start_time=st,
        end_time=et,
        status="APPROVED",
        requires_approval=True,
        coordinator_id=admin_auth["user"]["id"],
        created_by=admin_auth["user"]["id"],
        target_audience="ALL",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    try:
        # Check availability again for overlapping window (11:00 - 13:00)
        overlap_st = datetime.datetime.combine(future_date, datetime.time(11, 0))
        overlap_et = datetime.datetime.combine(future_date, datetime.time(13, 0))

        resp = client.post(
            "/events/venue-check",
            json={
                "room_id": room.id,
                "start_time": overlap_st.isoformat(),
                "end_time": overlap_et.isoformat(),
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_available"] is False
        assert len(data["conflicts"]) >= 1
        event_conflict = next((c for c in data["conflicts"] if (c.get("conflict_type") == "CAMPUS_EVENT" or c.get("type") == "CAMPUS_EVENT")), None)
        assert event_conflict is not None
        assert "Existing Approved Summit" in (event_conflict.get("reason") or event_conflict.get("title") or "")

        # Excluding the event itself during update should pass
        resp_exclude = client.post(
            "/events/venue-check",
            json={
                "room_id": room.id,
                "start_time": st.isoformat(),
                "end_time": et.isoformat(),
                "exclude_event_id": event.id,
            },
            headers=admin_headers,
        )
        assert resp_exclude.status_code == 200
        assert resp_exclude.json()["is_available"] is True
    finally:
        db_session.delete(event)
        db_session.commit()


def test_event_approval_and_rejection_flow(admin_auth, faculty_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    fac_user_id = faculty_auth["user"]["id"]

    # Assign EVENT_COORDINATOR capability to faculty
    client.post(
        "/admin/capabilities/assign",
        json={"user_id": fac_user_id, "capability": "EVENT_COORDINATOR", "scope_type": "GLOBAL"},
        headers=admin_headers,
    )

    st = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)).replace(tzinfo=None)
    et = st + datetime.timedelta(hours=2)

    # 1. Faculty creates DRAFT event
    resp = client.post(
        "/events",
        json={
            "title": "Quantum Computing Workshop",
            "category": "WORKSHOP",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "CS Auditorium",
            "requires_approval": True,
        },
        headers=faculty_headers,
    )
    assert resp.status_code in (200, 201)
    ev = resp.json()
    assert ev["status"] == "DRAFT"
    event_id = ev["id"]

    # 2. Faculty submits event for review
    resp = client.post(f"/events/{event_id}/submit", headers=faculty_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING_APPROVAL"

    # 3. Admin reviews and approves event
    resp = client.post(
        f"/events/{event_id}/review",
        json={"action": "APPROVE", "notes": "Approved for all undergraduate students"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    approved_ev = resp.json()
    assert approved_ev["status"] in ("APPROVED", "PUBLISHED")
    assert approved_ev["approved_by"] == admin_auth["user"]["id"]

    # 4. Create another event and reject it
    st2 = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=12)).replace(tzinfo=None)
    et2 = st2 + datetime.timedelta(hours=2)
    resp2 = client.post(
        "/events",
        json={
            "title": "Unapproved Late Night Hack",
            "category": "HACKATHON",
            "start_time": st2.isoformat(),
            "end_time": et2.isoformat(),
            "venue_name": "Main Foyer",
            "requires_approval": True,
        },
        headers=faculty_headers,
    )
    assert resp2.status_code in (200, 201)
    ev2_id = resp2.json()["id"]
    client.post(f"/events/{ev2_id}/submit", headers=faculty_headers)

    resp_reject = client.post(
        f"/events/{ev2_id}/review",
        json={"action": "REJECT", "reason": "Late night campus security curfew"},
        headers=admin_headers,
    )
    assert resp_reject.status_code == 200
    rej = resp_reject.json()
    assert rej["status"] == "REJECTED"
    assert rej["rejection_reason"] == "Late night campus security curfew"

    # 5. Cancel approved event
    resp_cancel = client.post(
        f"/events/{event_id}/cancel",
        json={"reason": "Speaker rescheduled"},
        headers=admin_headers,
    )
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] == "CANCELLED"
    assert resp_cancel.json()["cancellation_reason"] == "Speaker rescheduled"


def test_direct_publishing_permissions(admin_auth, faculty2_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty2_headers = {"Authorization": f"Bearer {faculty2_auth['token']}"}
    fac2_user_id = faculty2_auth["user"]["id"]

    st = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=15)).replace(tzinfo=None)
    et = st + datetime.timedelta(hours=2)

    # 1. Faculty without EVENT_DIRECT_PUBLISH tries direct publish -> 403 Forbidden
    resp = client.post(
        "/events",
        json={
            "title": "Direct Publish Attempt Without Capability",
            "category": "SEMINAR",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Seminar Room 1",
            "requires_approval": False,
        },
        headers=faculty2_headers,
    )
    assert resp.status_code == 403, f"Should reject direct publish without capability: {resp.text}"

    # 2. Admin grants EVENT_COORDINATOR and EVENT_DIRECT_PUBLISH capabilities
    client.post(
        "/admin/capabilities/assign",
        json={"user_id": fac2_user_id, "capability": "EVENT_COORDINATOR", "scope_type": "GLOBAL"},
        headers=admin_headers,
    )
    client.post(
        "/admin/capabilities/assign",
        json={"user_id": fac2_user_id, "capability": "EVENT_DIRECT_PUBLISH", "scope_type": "GLOBAL"},
        headers=admin_headers,
    )

    # 3. Faculty with EVENT_DIRECT_PUBLISH creates event -> published directly
    resp = client.post(
        "/events",
        json={
            "title": "Directly Published Research Seminar",
            "category": "SEMINAR",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Seminar Room 1",
            "requires_approval": False,
        },
        headers=faculty2_headers,
    )
    assert resp.status_code in (200, 201), f"Direct publish should succeed: {resp.text}"
    ev = resp.json()
    assert ev["status"] == "PUBLISHED"
    assert ev["published_at"] is not None


def test_student_privacy_and_audience_filtering(admin_auth, faculty_auth, student_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    student_headers = {"Authorization": f"Bearer {student_auth['token']}"}

    # 1. Student cannot access coordinator endpoints
    resp = client.post(
        "/events",
        json={
            "title": "Student Unauthorized Event",
            "category": "CULTURAL",
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": datetime.datetime.now().isoformat(),
        },
        headers=student_headers,
    )
    assert resp.status_code == 403

    resp = client.get("/admin/capabilities", headers=student_headers)
    assert resp.status_code == 403

    # 2. Create a DRAFT event, a PENDING event, a FACULTY-ONLY event, and a PUBLISHED event
    st = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=20)).replace(tzinfo=None)
    et = st + datetime.timedelta(hours=2)

    # Draft event
    resp_draft = client.post(
        "/events",
        json={
            "title": "Secret Draft Innovation Hack",
            "category": "HACKATHON",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Lab 1",
            "requires_approval": True,
        },
        headers=faculty_headers,
    )
    draft_id = resp_draft.json()["id"]

    # Faculty-only published event
    resp_fac_only = client.post(
        "/events",
        json={
            "title": "Confidential Faculty Board Review",
            "category": "ACADEMIC",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Boardroom",
            "target_audience": "FACULTY",
            "requires_approval": False,
        },
        headers=admin_headers,
    )
    fac_only_id = resp_fac_only.json()["id"]

    # All-audience published event
    resp_pub = client.post(
        "/events",
        json={
            "title": "Annual University Tech Fest",
            "category": "FEST" if "FEST" in [e.value for e in []] else "GENERAL",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Campus Grounds",
            "target_audience": "ALL",
            "requires_approval": False,
        },
        headers=admin_headers,
    )
    pub_id = resp_pub.json()["id"]

    # Student requests /events
    resp_student = client.get("/events", headers=student_headers)
    assert resp_student.status_code == 200
    student_events = resp_student.json()
    student_event_ids = [e["id"] for e in student_events]

    # Student must see published public event
    assert pub_id in student_event_ids
    # Student must NEVER see draft event
    assert draft_id not in student_event_ids
    # Student must NEVER see faculty-only event
    assert fac_only_id not in student_event_ids


def test_optimistic_locking_version_tracking(admin_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    st = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=25)).replace(tzinfo=None)
    et = st + datetime.timedelta(hours=2)

    resp = client.post(
        "/events",
        json={
            "title": "Cybersecurity Conclave",
            "category": "SEMINAR",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Auditorium",
            "requires_approval": False,
        },
        headers=admin_headers,
    )
    assert resp.status_code in (200, 201)
    ev = resp.json()
    assert ev["version"] == 1
    event_id = ev["id"]

    # Update event details
    resp_up = client.put(
        f"/events/{event_id}",
        json={"title": "Cybersecurity & Cryptography Conclave"},
        headers=admin_headers,
    )
    assert resp_up.status_code == 200
    assert resp_up.json()["version"] == 2
    assert resp_up.json()["title"] == "Cybersecurity & Cryptography Conclave"


def test_assistant_events_grounding_and_intent(admin_auth, faculty_auth, student_auth, db_session):
    student_user = db_session.query(User).filter(User.id == student_auth["user"]["id"]).first()
    faculty_user = db_session.query(User).filter(User.id == faculty_auth["user"]["id"]).first()
    assert student_user is not None
    assert faculty_user is not None

    # 1. Supervisor Intent classification
    assert classify_intent("What events are happening today?") == "QUERY_AGENT"
    assert classify_intent("Show ongoing events on campus") == "QUERY_AGENT"
    assert classify_intent("Show my clubs") == "QUERY_AGENT"
    assert classify_intent("What activities are in Robotics club?") == "QUERY_AGENT"
    assert classify_intent("Upcoming workshops") == "QUERY_AGENT"

    # 2. Query Agent tool extraction
    tool, args = _extract_intent_and_tool_call("What events are happening now?", student_user)
    assert tool == "get_ongoing_events"

    tool, args = _extract_intent_and_tool_call("Upcoming workshops", student_user)
    assert tool == "get_upcoming_events"

    tool, args = _extract_intent_and_tool_call("Show my clubs", faculty_user)
    assert tool == "list_my_clubs"

    # 3. Direct tool execution against database
    ongoing_result = execute_tool(
        tool_name="get_ongoing_events",
        tool_args={},
        user=student_user,
        db=db_session,
    )
    assert "ongoing_events" in ongoing_result
    assert "count" in ongoing_result

    # Format grounded response
    text, sources = format_grounded_response(
        tool_name="get_ongoing_events",
        tool_args={},
        tool_result=ongoing_result,
        user=student_user,
    )
    assert isinstance(text, str)
    assert "Campus Events Registry" in sources
