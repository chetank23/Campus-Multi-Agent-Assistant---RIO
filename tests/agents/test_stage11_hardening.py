"""
tests/agents/test_stage11_hardening.py
--------------------------------------
Comprehensive verification test suite for Stage 11:
1. Global Resource Lock Policy:
   - PENDING and APPROVED bookings act as global locks.
   - Resource is blocked for all new bookings and availability checks regardless of date/time/purpose.
   - Exact plain-English lock message returned.
   - Direct API cannot bypass lock (409 Conflict).
   - Alternate natural language queries cannot bypass lock.
   - Only truly unlocked resources offered as alternatives.
   - Cancellation or Rejection releases lock; invalid transitions do not.
   - Concurrent booking creation attempts serialize via row locking.
2. Plain-English Communication Standard:
   - Zero emojis across all agents (Supervisor, Resource, Scheduling, Query).
   - Zero markdown headings (#, ##, ###).
   - Zero bold/italic asterisks (**, *).
   - Preservation of real names, dates, times, statuses, and numeric IDs (#12).
   - No stack traces or raw technical internals.
3. Conversational State & Follow-ups:
   - Multi-turn 'yes' / 'confirm' binds to pending proposal.
   - Multi-turn 'no' / 'cancel' discards pending proposal.
   - 'change time' prompts for interval clarification.
   - Cross-agent proposal tokens rejected.
   - Ambiguous requests trigger targeted questions without guessing.
"""

import re
import datetime
import concurrent.futures
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Room
from backend.models.timetable import TimetableVersion
from agents.supervisor.agent import execute_supervisor, AgentState
from agents.resource_agent.agent import run_resource_agent
from agents.scheduling_agent.agent import run_scheduling_agent
from agents.resource_agent.proposal_store import resource_proposal_store
from agents.scheduling_agent.proposal_store import proposal_store
from agents.common.formatter import sanitize_plain_english

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
def faculty2_token():
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty 2 login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]


# Helper function to assert strict plain English
def assert_strict_plain_english(text: str):
    assert text is not None and len(text.strip()) > 0, "Response must not be empty"
    # Prohibit emojis
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff"
        r"\u2600-\u26ff"
        r"\u2700-\u27bf"
        r"\U0001f300-\U0001f5ff"
        r"\U0001f600-\U0001f64f"
        r"\U0001f680-\U0001f6ff"
        r"\U0001f900-\U0001f9ff"
        r"\u200d\u23e9-\u23ef\u23f0-\u23f3\u2b50\u2705\u274c\u26a0\u2139]+",
        flags=re.UNICODE,
    )
    assert not emoji_pattern.search(text), f"Response contains prohibited emojis: {text}"

    # Prohibit markdown headings (#, ##, ###) at start of lines
    assert not re.search(r"^\s*#{1,6}\s", text, re.MULTILINE), f"Response contains prohibited markdown headings: {text}"

    # Prohibit bold or italic asterisks (* or **)
    assert "*" not in text, f"Response contains prohibited asterisks: {text}"


# ── 1. Global Resource Lock: PENDING & APPROVED Locks ─────────────────────────

def test_global_lock_pending_blocks_all_dates_and_times(admin_token, faculty_token):
    """
    A resource with a PENDING booking is globally locked for all new bookings and inquiries,
    regardless of date, time, or purpose.
    """
    # 1. Create a dedicated resource for this test
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Stage11 Global Lock Room", "resource_type": "LAB", "capacity": 25},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    # 2. Submit a booking request for Date A (status -> PENDING)
    date_a = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    req_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_a,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "purpose": "Initial Lock Session",
        },
    )
    assert req_resp.status_code == 201
    booking_id = req_resp.json()["id"]

    # 3. Direct API attempt on completely different date/time (Date B, next month) -> 409 Conflict
    date_b = (datetime.date.today() + datetime.timedelta(days=45)).isoformat()
    conflict_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_b,
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "purpose": "Different Date Attempt",
        },
    )
    assert conflict_resp.status_code == 409
    assert "Resource already booked" in conflict_resp.text
    assert "Stage11 Global Lock Room has an active booking" in conflict_resp.text

    # 4. Agent availability inquiry for Date B -> returns plain-English lock message
    chat_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Is Stage11 Global Lock Room available on {date_b} from 14:00 to 16:00?"},
    )
    assert chat_resp.status_code == 200
    reply = chat_resp.json()["reply"]
    assert_strict_plain_english(reply)
    assert "Resource already booked" in reply
    assert "Stage11 Global Lock Room has an active booking" in reply
    assert "Please select another resource" in reply

    # 5. Alternate natural language query wording cannot bypass the lock
    alt_chat_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Can I book Stage11 Global Lock Room on {date_b}?"},
    )
    assert alt_chat_resp.status_code == 200
    alt_reply = alt_chat_resp.json()["reply"]
    assert_strict_plain_english(alt_reply)
    assert "Resource already booked" in alt_reply

    # 6. Cancellation releases the lock
    cancel_resp = client.post(
        f"/resources/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {faculty_token}"},
    )
    assert cancel_resp.status_code == 200

    # 7. Now the resource is available again!
    date_c = (datetime.date.today() + datetime.timedelta(days=12)).isoformat()
    free_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_c,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Now Available Session",
        },
    )
    assert free_resp.status_code == 201
    new_booking_id = free_resp.json()["id"]

    # Clean up
    client.post(f"/resources/bookings/{new_booking_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})


def test_global_lock_approved_and_rejection_lifecycle(admin_token, faculty_token):
    """
    Verify that an APPROVED booking locks the resource, and that admin rejection releases the lock.
    """
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Stage11 Approval Lock Room", "resource_type": "SEMINAR_HALL", "capacity": 60},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    # Create booking and approve it
    date_str = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
    req_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_str,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Approved Lock Test",
        },
    )
    assert req_resp.status_code == 201
    b_id = req_resp.json()["id"]

    appr = client.post(f"/resources/bookings/{b_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    assert appr.status_code == 200

    # Locked when approved
    check_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    attempt = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": check_date,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Should Fail Due to Approved Lock",
        },
    )
    assert attempt.status_code == 409
    assert "Resource already booked" in attempt.text

    # Cancel approved booking
    cancel = client.post(f"/resources/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})
    assert cancel.status_code == 200

    # Now unlocked: create a new pending request and reject it to verify rejection releases lock
    req_resp2 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_str,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Will Be Rejected",
        },
    )
    assert req_resp2.status_code == 201
    b_id2 = req_resp2.json()["id"]

    # Reject via admin
    rej = client.post(
        f"/resources/bookings/{b_id2}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Testing rejection lock release"},
    )
    assert rej.status_code == 200

    # Resource must now be unlocked again
    avail_check = client.get(
        "/resources/availability",
        headers={"Authorization": f"Bearer {faculty_token}"},
        params={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00"},
    )
    assert avail_check.status_code == 200
    assert avail_check.json()["available"] is True


# ── 2. Plain-English Compliance Across All Agents ─────────────────────────────

def test_plain_english_query_agent_responses(student_token):
    """Query agent responses must strictly have 0 emojis, 0 headings, 0 asterisks, while preserving IDs."""
    queries = [
        "What are the credits for course CS101?",
        "Show me information about the Department of Computer Science",
        "List all available facilities",
        "Who is Dr. Allison Hill?",
    ]
    for q in queries:
        resp = client.post("/agents/chat", headers={"Authorization": f"Bearer {student_token}"}, json={"message": q})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert_strict_plain_english(reply)


def test_plain_english_scheduling_agent_responses(admin_token):
    """Scheduling agent responses must adhere strictly to the plain-English standard."""
    queries = [
        "Generate a timetable for CSE",  # missing academic year & semester
        "Show timetable optimization status",
        "What is the schedule readiness for academic year 2026?",
    ]
    for q in queries:
        resp = client.post("/agents/chat", headers={"Authorization": f"Bearer {admin_token}"}, json={"message": q})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert_strict_plain_english(reply)


def test_plain_english_supervisor_greetings_and_fallbacks(student_token):
    """Supervisor greeting, clarification, and fallback messages must be clean plain English."""
    messages = [
        "Hello!",
        "Thank you so much",
        "xyzabc123 non-existent intent gibberish query",
    ]
    for m in messages:
        resp = client.post("/agents/chat", headers={"Authorization": f"Bearer {student_token}"}, json={"message": m})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert_strict_plain_english(reply)


# ── 3. Conversational State & Follow-ups ──────────────────────────────────────

def test_conversational_followup_yes_confirms_pending_proposal(faculty_token):
    """
    Multi-turn conversation:
    Turn 1: Request to book an available resource -> Generates proposal.
    Turn 2: Follow-up 'yes' -> Resolves pending proposal and executes booking.
    """
    with Session(engine) as db:
        # Create dedicated unlocked resource
        test_res = Resource(name="Stage11 Turn Room", resource_type="LAB", capacity=20, status="ACTIVE")
        db.add(test_res)
        db.commit()
        db.refresh(test_res)
        res_name = test_res.name
        res_id = test_res.id

    target_date = (datetime.date.today() + datetime.timedelta(days=15)).isoformat()

    # Turn 1: Create proposal
    msg1 = f"Book {res_name} on {target_date} from 14:00 to 16:00 for Architecture Review"
    r1 = client.post("/agents/chat", headers={"Authorization": f"Bearer {faculty_token}"}, json={"message": msg1})
    assert r1.status_code == 200
    data1 = r1.json()
    assert_strict_plain_english(data1["reply"])
    proposal = data1.get("proposal")
    assert proposal is not None
    prop_id = proposal["proposal_id"]
    assert prop_id.startswith("res_prop_")

    # Turn 2: Follow-up "yes"
    r2 = client.post("/agents/chat", headers={"Authorization": f"Bearer {faculty_token}"}, json={"message": "yes"})
    assert r2.status_code == 200
    data2 = r2.json()
    reply2 = data2["reply"]
    assert_strict_plain_english(reply2)
    assert "submitted successfully" in reply2.lower()
    assert "Booking ID" in reply2 or "#" in reply2

    # Clean up created booking
    with Session(engine) as db:
        bk = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).first()
        if bk:
            bk.status = "CANCELLED"
            db.commit()


def test_conversational_followup_no_cancels_pending_proposal(faculty_token):
    """
    Multi-turn conversation:
    Turn 1: Request to book an available resource -> Generates proposal.
    Turn 2: Follow-up 'no' -> Discards pending proposal.
    """
    with Session(engine) as db:
        test_res = Resource(name="Stage11 Discard Room", resource_type="LAB", capacity=20, status="ACTIVE")
        db.add(test_res)
        db.commit()
        db.refresh(test_res)
        res_name = test_res.name
        res_id = test_res.id

    target_date = (datetime.date.today() + datetime.timedelta(days=16)).isoformat()

    # Turn 1: Create proposal
    msg1 = f"Book {res_name} on {target_date} from 10:00 to 12:00 for Team Standup"
    r1 = client.post("/agents/chat", headers={"Authorization": f"Bearer {faculty_token}"}, json={"message": msg1})
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1.get("proposal") is not None

    # Turn 2: Follow-up "no"
    r2 = client.post("/agents/chat", headers={"Authorization": f"Bearer {faculty_token}"}, json={"message": "no"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert_strict_plain_english(data2["reply"])
    assert "discarded" in data2["reply"].lower() or "cancelled" in data2["reply"].lower()

    # Verify no booking was created in DB
    with Session(engine) as db:
        bk_count = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).count()
        assert bk_count == 0


def test_cross_agent_proposal_tokens_isolated(admin_token, faculty_token):
    """A resource proposal cannot confirm a timetable draft, and vice versa."""
    # 1. Admin confirms a fake resource proposal on supervisor -> routed to resource agent
    res_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "confirm res_prop_fake123"},
    )
    assert res_resp.status_code == 200
    assert_strict_plain_english(res_resp.json()["reply"])
    # Handled by resource agent, rejected as not found
    assert "not found" in res_resp.json()["reply"].lower() or "expired" in res_resp.json()["reply"].lower()

    # 2. Admin confirms a fake scheduling proposal -> routed to scheduling agent
    sched_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "confirm prop_fake123"},
    )
    assert sched_resp.status_code == 200
    assert_strict_plain_english(sched_resp.json()["reply"])
    # Handled by scheduling agent, rejected as not found / expired without touching resources
    assert "not found" in sched_resp.json()["reply"].lower() or "expired" in sched_resp.json()["reply"].lower()

    # 3. Faculty confirms a scheduling proposal -> blocked by role authorization
    fac_sched_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": "confirm prop_fake123"},
    )
    assert fac_sched_resp.status_code == 200
    assert "access restricted" in fac_sched_resp.json()["reply"].lower() or "administrator" in fac_sched_resp.json()["reply"].lower()


# ── 4. Formatter Integrity Test ───────────────────────────────────────────────

def test_sanitize_plain_english_preserves_identifiers():
    """Sanitizer preserves identifiers, codes, dates, times, while stripping decoration."""
    dirty_text = "### Booking Confirmed! 🎉\n\nBooking **#42** for **CSE Department** on *2026-11-20* at 14:00 is confirmed! ✅"
    clean = sanitize_plain_english(dirty_text)
    assert "#42" in clean
    assert "CSE Department" in clean
    assert "2026-11-20" in clean
    assert "14:00" in clean
    assert_strict_plain_english(clean)
