"""
tests/integration/test_final_acceptance_assistant_intelligence.py
------------------------------------------------------------------
Authoritative End-to-End Acceptance Test Suite for AI Assistant Intelligence & Behaviour:
Verifies:
  1. Multi-turn conversations, ambiguous wording, corrections, and follow-ups.
  2. Targeted clarifying questions when essential scope or interval parameters are missing.
  3. Consequential action confirmation requirement before timetable generation or booking execution.
  4. Grounding in authoritative PostgreSQL records; refusal to hallucinate facts or invent data.
  5. Honest failure handling, permission barriers (RBAC), and tool error explanations.
  6. Strict Plain-English communication across all roles (0 emojis, 0 headings, 0 asterisks).
"""

from __future__ import annotations

import datetime
import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.resources import Resource, ResourceBooking

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


def assert_plain_english(text: str):
    """Enforces zero emojis, zero markdown headings, and zero formatting asterisks."""
    assert text is not None and len(text.strip()) > 0
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\U0001f300-\U0001f5ff\U0001f600-\U0001f64f\U0001f680-\U0001f6ff\U0001f900-\U0001f9ff]+",
        flags=re.UNICODE,
    )
    assert not emoji_pattern.search(text), f"Found emoji in: {text}"
    assert not re.search(r"^\s*#{1,6}\s", text, re.MULTILINE), f"Found heading in: {text}"
    assert "*" not in text, f"Found asterisk in: {text}"


# ── 1. Intent Distinction & Routing ───────────────────────────────────────────

def test_intent_distinction_across_domains(admin_token, student_token):
    # Timetable generation -> Scheduling Agent (Admin)
    r1 = client.post("/agents/chat", headers={"Authorization": f"Bearer {admin_token}"}, json={"message": "Generate a timetable for CSE"})
    assert r1.status_code == 200
    assert r1.json()["selected_agent"] == "scheduling_agent"
    assert_plain_english(r1.json()["reply"])

    # Facility booking inquiry -> Resource Agent
    r2 = client.post("/agents/chat", headers={"Authorization": f"Bearer {student_token}"}, json={"message": "Is Seminar Hall available tomorrow?"})
    assert r2.status_code == 200
    assert r2.json()["selected_agent"] == "resource_agent"
    assert_plain_english(r2.json()["reply"])

    # Campus information inquiry -> Query Agent
    r3 = client.post("/agents/chat", headers={"Authorization": f"Bearer {student_token}"}, json={"message": "What is the syllabus and credits for course CS101?"})
    assert r3.status_code == 200
    assert r3.json()["selected_agent"] == "query_agent"
    assert_plain_english(r3.json()["reply"])

    # Greeting -> Supervisor directly
    r4 = client.post("/agents/chat", headers={"Authorization": f"Bearer {student_token}"}, json={"message": "Good morning"})
    assert r4.status_code == 200
    assert r4.json()["selected_agent"] is None
    assert "Hello. I am the RIO Campus Assistant" in r4.json()["reply"]
    assert_plain_english(r4.json()["reply"])

    # Out of scope / Unknown -> Supervisor directly
    r5 = client.post("/agents/chat", headers={"Authorization": f"Bearer {student_token}"}, json={"message": "What is the capital of France?"})
    assert r5.status_code == 200
    assert r5.json()["selected_agent"] is None
    assert "could not find a matching campus service" in r5.json()["reply"].lower()
    assert_plain_english(r5.json()["reply"])


# ── 2. Missing Scope & Clarifying Questions ───────────────────────────────────

def test_clarifying_questions_for_incomplete_scheduling_scope(admin_token):
    # Incomplete request: missing academic year & semester
    r = client.post("/agents/chat", headers={"Authorization": f"Bearer {admin_token}"}, json={"message": "Generate a timetable for CSE"})
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert_plain_english(reply)
    # The assistant must ask a targeted clarifying question rather than guessing
    assert "academic year" in reply.lower() or "semester" in reply.lower()
    # It must not generate a timetable without full scope
    assert r.json().get("proposal") is None


def test_clarifying_questions_for_incomplete_resource_booking(faculty_token):
    # Missing date and time interval
    r = client.post("/agents/chat", headers={"Authorization": f"Bearer {faculty_token}"}, json={"message": "I would like to book a lab"})
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert_plain_english(reply)
    assert "date" in reply.lower() or "time" in reply.lower()
    assert r.json().get("proposal") is None


# ── 3. Consequential Action Confirmation & Execution ──────────────────────────

def test_consequential_booking_requires_confirmation_token(faculty_token):
    # Create dedicated active resource
    with Session(engine) as db:
        res = Resource(name="Assistant Test Lab Alpha", resource_type="LAB", capacity=30, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        res_name = res.name
        res_id = res.id

    date_str = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()

    # Step 1: Request creates proposal but DOES NOT execute booking in DB
    r1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {res_name} on {date_str} from 10:00 to 12:00 for Cloud Computing Review"},
    )
    assert r1.status_code == 200
    data1 = r1.json()
    assert_plain_english(data1["reply"])
    proposal = data1.get("proposal")
    assert proposal is not None
    prop_id = proposal["proposal_id"]
    assert prop_id.startswith("res_prop_")

    # Verify no booking is in the database yet
    with Session(engine) as db:
        count = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).count()
        assert count == 0

    # Step 2: Confirm with valid token -> booking committed to DB
    r2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"confirm {prop_id}"},
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert_plain_english(data2["reply"])
    assert "submitted successfully" in data2["reply"].lower()

    # Verify booking is now committed in DB
    with Session(engine) as db:
        bk = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).first()
        assert bk is not None
        assert bk.status == "PENDING"
        # Clean up
        client.post(f"/resources/bookings/{bk.id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})


# ── 4. Multi-Turn Correction & Proposal Discard ───────────────────────────────

def test_multi_turn_correction_and_discard(faculty_token):
    with Session(engine) as db:
        res = Resource(name="Assistant Test Seminar Beta", resource_type="SEMINAR_HALL", capacity=60, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        res_name = res.name
        res_id = res.id

    date_str = (datetime.date.today() + datetime.timedelta(days=16)).isoformat()

    # Turn 1: Request booking -> creates proposal
    r1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {res_name} on {date_str} from 09:00 to 11:00 for AI Seminar"},
    )
    assert r1.status_code == 200
    assert r1.json().get("proposal") is not None

    # Turn 2: User says "change time"
    r2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": "change the time"},
    )
    assert r2.status_code == 200
    assert_plain_english(r2.json()["reply"])
    assert "date and time interval" in r2.json()["reply"].lower()

    # Turn 3: User says "cancel" -> discards proposal
    r3 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": "cancel"},
    )
    assert r3.status_code == 200
    assert_plain_english(r3.json()["reply"])
    assert "discarded" in r3.json()["reply"].lower() or "cancelled" in r3.json()["reply"].lower()

    # Verify no booking in DB
    with Session(engine) as db:
        count = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).count()
        assert count == 0


# ── 5. Grounding & Anti-Hallucination ──────────────────────────────────────────

def test_query_agent_grounding_and_anti_hallucination(student_token):
    # Real course query -> Grounded data
    r_real = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": "What are the details of course CS101?"},
    )
    assert r_real.status_code == 200
    assert_plain_english(r_real.json()["reply"])
    assert "CS101" in r_real.json()["reply"]

    # Fake course query -> Clear refusal / not found, no hallucination
    r_fake = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": "What are the details of course NONEXISTENT999?"},
    )
    assert r_fake.status_code == 200
    assert_plain_english(r_fake.json()["reply"])
    reply_lower = r_fake.json()["reply"].lower()
    assert "was found" in reply_lower or "not found" in reply_lower or "matching" in reply_lower


# ── 6. Role Authorization Barrier (Student Timetable Generation Attempt) ──────

def test_student_prohibited_from_generating_timetables(student_token):
    r = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": "Generate a timetable for CSE semester 5"},
    )
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert_plain_english(reply)
    assert "access restricted" in reply.lower() or "administrators" in reply.lower()
    assert r.json().get("proposal") is None
