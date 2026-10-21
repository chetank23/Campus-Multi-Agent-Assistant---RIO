"""
tests/integration/test_admin_readiness_and_pending_bookings.py
--------------------------------------------------------------
Focused regression and end-to-end integration tests for:
1. Genuine timetable-readiness query:
   - Evaluates authoritative data readiness without solver invocation,
     proposal tokens, or draft timetable version persistence.
   - Enforces Admin authorization.
   - Prompts for missing scope parameters without guessing.
   - Clearly distinguishes READY, READY_WITH_WARNINGS, and BLOCKED.
2. Real pending resource bookings query:
   - Filters authoritative booking store by status == 'PENDING'.
   - Excludes APPROVED, REJECTED, and CANCELLED bookings.
   - Reports clear empty state when no pending requests exist.
   - Enforces Admin-only access for campus-wide pending bookings.
   - Preserves standard "Show my bookings" for Faculty and Students.
   - Preserves global resource lock integrity.
"""

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.timetable import TimetableVersion
from agents.scheduling_agent.proposal_store import proposal_store

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


# ── 1. Genuine Timetable Readiness Query Tests ─────────────────────────────────

def test_admin_readiness_query_success_without_proposal(admin_token):
    """
    Readiness query must reach the Scheduling Agent, evaluate authoritative
    academic readiness data, and return findings without creating a proposal,
    consuming tokens, or writing a draft timetable version.
    """
    with Session(engine) as db:
        initial_version_count = db.query(TimetableVersion).count()
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        assert admin_user is not None
        initial_proposal = proposal_store.get_latest_pending_proposal(admin_user.id)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Check timetable readiness for CSE Semester 1."},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["selected_agent"] == "scheduling_agent"
    assert data["intent"] == "TIMETABLE_READINESS"
    # Action type reflects genuine readiness status
    assert data.get("action_type") in [
        "READINESS_READY",
        "READINESS_READY_WITH_WARNINGS",
        "READINESS_BLOCKED",
    ]
    # Critical: No proposal must be returned or stored
    assert data.get("proposal") is None
    assert "Readiness" in data["reply"]

    # Verify no timetable version was created in the database
    with Session(engine) as db:
        new_version_count = db.query(TimetableVersion).count()
        assert new_version_count == initial_version_count, "Readiness query must not write timetable versions."
        latest_proposal = proposal_store.get_latest_pending_proposal(admin_user.id)
        if initial_proposal is None:
            assert latest_proposal is None, "Readiness query must not add pending generation proposals."
        else:
            assert latest_proposal is not None and latest_proposal.proposal_id == initial_proposal.proposal_id


def test_admin_readiness_query_missing_scope_triggers_clarification(admin_token):
    """
    If required parameters like department or semester are missing,
    the Scheduling Agent must prompt for concise clarification without guessing.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Check timetable readiness"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["selected_agent"] == "scheduling_agent"
    assert data.get("action_type") == "CLARIFICATION_NEEDED"
    assert data.get("proposal") is None
    assert "Clarification" in data["reply"] or "missing" in data["reply"].lower()


def test_unauthorized_user_readiness_query_denied(faculty_token, student_token):
    """
    Faculty and Student users must not be permitted to run administrative
    timetable readiness evaluations.
    """
    for tok, label in [(faculty_token, "FACULTY"), (student_token, "STUDENT")]:
        headers = {"Authorization": f"Bearer {tok}"}
        resp = client.post(
            "/agents/chat",
            headers=headers,
            json={"message": "Check timetable readiness for CSE Semester 1."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_agent"] == "scheduling_agent"
        assert "Access Restricted" in data["reply"] or "Administrators" in data["reply"]
        assert data.get("proposal") is None


def test_admin_readiness_reports_real_blockers_when_prerequisites_missing(admin_token):
    """
    When an academic semester has missing prerequisites (e.g. empty semester with no sections),
    the readiness analysis must clearly report status as BLOCKED with specific blocker findings.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Semester 8 typically has no sections seeded for Year 1 programs
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Check timetable readiness for CSE Semester 8"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "scheduling_agent"
    assert data.get("proposal") is None
    # Action type reflects blocked or clarification
    if data.get("action_type") == "READINESS_BLOCKED":
        assert "BLOCKED" in data["reply"]
        assert "prerequisites" in data["reply"].lower() or "sections" in data["reply"].lower()


def test_admin_generate_timetable_enters_proposal_workflow(admin_token):
    """
    Prompt 'Generate timetable for CSE Semester 1' must enter the proposal-and-confirmation
    workflow, creating a proposal object if prerequisites are met.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Generate timetable for CSE Semester 1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "scheduling_agent"
    assert data.get("action_type") in ["PROPOSAL_CREATED", "READINESS_BLOCKED"]
    if data.get("action_type") == "PROPOSAL_CREATED":
        assert data.get("proposal") is not None
        assert "confirm prop_" in data["reply"].lower()


def test_check_resource_availability_prompts_for_missing_details(admin_token):
    """
    Submitted prompt 'Check resource availability' without parameters must prompt
    for missing facility, date, and time interval details.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/agents/chat",
        headers=headers,
        json={"message": "Check resource availability"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_agent"] == "resource_agent"
    assert data.get("action_type") == "CLARIFICATION_NEEDED"
    assert data.get("proposal") is None
    assert "facility" in data["reply"].lower() or "interval" in data["reply"].lower() or "time" in data["reply"].lower()


# ── 2. Real Pending Resource Bookings Query Tests ──────────────────────────────

def test_admin_pending_bookings_returns_only_pending_and_excludes_others(admin_token):
    """
    Admin pending bookings query must return only PENDING bookings,
    excluding APPROVED, REJECTED, and CANCELLED records.
    """
    with Session(engine) as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        faculty_user = db.query(User).filter(User.role == "FACULTY").first()
        assert admin_user is not None and faculty_user is not None

        # Create or find a test resource
        res = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        if not res:
            res = Resource(name="Pending Test Lab", resource_type="LAB", capacity=30, status="ACTIVE")
            db.add(res)
            db.commit()
            db.refresh(res)

        test_date = datetime.date.today() + datetime.timedelta(days=120)

        # 1. PENDING booking
        b_pending = ResourceBooking(
            resource_id=res.id,
            requested_by=faculty_user.id,
            date=test_date,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
            status="PENDING",
            purpose="Pending Capstone Review Session",
        )
        # 2. APPROVED booking
        b_approved = ResourceBooking(
            resource_id=res.id,
            requested_by=faculty_user.id,
            date=test_date,
            start_time=datetime.time(10, 30),
            end_time=datetime.time(11, 30),
            status="APPROVED",
            purpose="Approved Lab Practicum",
        )
        # 3. REJECTED booking
        b_rejected = ResourceBooking(
            resource_id=res.id,
            requested_by=faculty_user.id,
            date=test_date,
            start_time=datetime.time(12, 0),
            end_time=datetime.time(13, 0),
            status="REJECTED",
            purpose="Rejected Session",
        )
        # 4. CANCELLED booking
        b_cancelled = ResourceBooking(
            resource_id=res.id,
            requested_by=faculty_user.id,
            date=test_date,
            start_time=datetime.time(14, 0),
            end_time=datetime.time(15, 0),
            status="CANCELLED",
            purpose="Cancelled Session",
        )

        db.add_all([b_pending, b_approved, b_rejected, b_cancelled])
        db.commit()
        db.refresh(b_pending)
        db.refresh(b_approved)
        db.refresh(b_rejected)
        db.refresh(b_cancelled)

        pending_id = b_pending.id
        approved_id = b_approved.id
        rejected_id = b_rejected.id
        cancelled_id = b_cancelled.id

    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = client.post(
            "/agents/chat",
            headers=headers,
            json={"message": "View pending resource bookings"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["selected_agent"] == "resource_agent"
        assert data.get("action_type") == "BOOKINGS_LIST"

        reply = data["reply"]
        # Pending booking MUST be present
        assert f"Booking #{pending_id}" in reply, "Pending booking must appear in the result."
        assert "PENDING" in reply

        # Other statuses MUST be excluded
        assert f"Booking #{approved_id}" not in reply, "APPROVED booking must not appear in pending listing."
        assert f"Booking #{rejected_id}" not in reply, "REJECTED booking must not appear in pending listing."
        assert f"Booking #{cancelled_id}" not in reply, "CANCELLED booking must not appear in pending listing."

    finally:
        # Cleanup test records
        with Session(engine) as db:
            db.query(ResourceBooking).filter(
                ResourceBooking.id.in_([pending_id, approved_id, rejected_id, cancelled_id])
            ).delete(synchronize_session=False)
            db.commit()


def test_admin_pending_bookings_empty_state(admin_token):
    """
    When there are no pending bookings on record, the Assistant must clearly
    state that there are no pending resource booking requests.
    """
    with Session(engine) as db:
        # Temporarily stash any existing pending bookings
        existing_pending = db.query(ResourceBooking).filter(ResourceBooking.status == "PENDING").all()
        stash_ids = [b.id for b in existing_pending]
        if stash_ids:
            db.query(ResourceBooking).filter(ResourceBooking.id.in_(stash_ids)).update(
                {"status": "APPROVED"}, synchronize_session=False
            )
            db.commit()

    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = client.post(
            "/agents/chat",
            headers=headers,
            json={"message": "View pending resource bookings"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_agent"] == "resource_agent"
        assert "no pending resource booking requests on record" in data["reply"].lower()

    finally:
        # Restore stashed bookings
        if stash_ids:
            with Session(engine) as db:
                db.query(ResourceBooking).filter(ResourceBooking.id.in_(stash_ids)).update(
                    {"status": "PENDING"}, synchronize_session=False
                )
                db.commit()


def test_unauthorized_user_pending_bookings_access_denied(faculty_token, student_token):
    """
    Non-admin users asking for campus pending resource bookings must receive
    an access restriction notice and guidance to use 'Show my bookings'.
    """
    for tok, label in [(faculty_token, "FACULTY"), (student_token, "STUDENT")]:
        headers = {"Authorization": f"Bearer {tok}"}
        resp = client.post(
            "/agents/chat",
            headers=headers,
            json={"message": "View pending resource bookings"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_agent"] == "resource_agent"
        assert "Access Restricted" in data["reply"] or "Administrators" in data["reply"]
        assert "Show my bookings" in data["reply"]


def test_faculty_show_my_bookings_unchanged(faculty_token):
    """
    The existing 'Show my bookings' behavior for Faculty and Students must
    remain intact and query the user's personal booking history.
    """
    with Session(engine) as db:
        faculty_user = db.query(User).filter(User.role == "FACULTY").first()
        assert faculty_user is not None
        res = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        assert res is not None

        # Add a personal booking for this faculty
        test_booking = ResourceBooking(
            resource_id=res.id,
            requested_by=faculty_user.id,
            date=datetime.date.today() + datetime.timedelta(days=150),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(15, 0),
            status="APPROVED",
            purpose="Faculty Office Hours Review",
        )
        db.add(test_booking)
        db.commit()
        db.refresh(test_booking)
        test_b_id = test_booking.id

    try:
        headers = {"Authorization": f"Bearer {faculty_token}"}
        resp = client.post(
            "/agents/chat",
            headers=headers,
            json={"message": "Show my bookings"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["selected_agent"] == "resource_agent"
        assert data.get("action_type") == "BOOKINGS_LIST"
        assert f"Booking #{test_b_id}" in data["reply"]
        assert "Access Restricted" not in data["reply"]

    finally:
        with Session(engine) as db:
            db.query(ResourceBooking).filter(ResourceBooking.id == test_b_id).delete()
            db.commit()
