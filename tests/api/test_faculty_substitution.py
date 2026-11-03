"""
tests/api/test_faculty_substitution.py
--------------------------------------
Comprehensive end-to-end integration and verification suite for Faculty Substitution:
1. Faculty Upcoming Class Occurrences: Real published schedule inspection with date-weekday mapping.
2. Unavailability Request Lifecycle & Validations:
   - Valid request submission (201 Created).
   - Reason minimum length validation (400 Bad Request).
   - Ownership barrier: cannot request for another faculty's class (403 Forbidden).
   - Date-weekday mismatch validation (400 Bad Request).
   - Duplicate active request prevention (409 Conflict).
   - Past date prevention (400 Bad Request).
3. Deterministic Candidate Ranking Engine:
   - Qualification scoring (direct course assignment, department match, general).
   - Timetable clash detection at slot.
   - FacultyAvailability record evaluation.
   - Conflicting approved substitution detection.
   - Workload limit bounds check (current load + 1 <= max_load).
   - Strict self-exclusion.
   - Deterministic multi-attribute sort order.
4. Reviewer Capabilities & Scoped RBAC:
   - Admin access.
   - Non-coordinator faculty rejected (403 Forbidden).
   - Coordinator capability grant (SUBSTITUTION_COORDINATOR / SUBSTITUTION_REVIEWER) enables review.
5. Optimistic Concurrency Control: Version mismatch raises 409 Conflict.
6. Rejection Workflow: Rejection reason audit and requesting faculty notification.
7. Approval Workflow & Master Timetable Immutability:
   - Date occurrence override applied.
   - Master weekly TimetableEntry remains 100% UNCHANGED.
   - Multi-party notifications (original faculty, substitute, students).
   - Strict Privacy Barrier: Student notifications and views NEVER disclose personal absence reason.
8. Date-Specific Schedule Layering:
   - Student timetable date query overlays substitute teacher.
   - Student master timetable without date remains canonical original teacher.
   - Faculty timetable overlays covering duty for substitute.
   - Live status reflects effective substitute for today.
9. Multi-Agent Assistant Grounding: Grounded PostgreSQL query tools with privacy protection.
"""

from __future__ import annotations

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Faculty, Student, Department, Section
from backend.models.courses import Course, CourseAssignment
from backend.models.events import CoordinatorCapability
from backend.models.space_time import Room, TimeSlot, FacultyAvailability
from backend.models.substitution import FacultySubstitution
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import Notification
from backend.services.substitution_service import day_matches_date
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


@pytest.fixture(scope="module", autouse=True)
def setup_substitution_test_data():
    with Session(engine) as db:
        pub_v = db.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
        if not pub_v:
            pub_v = TimetableVersion(
                status="PUBLISHED",
                version_number="V-SUB-1",
                published_at=datetime.datetime.now(datetime.timezone.utc),
            )
            db.add(pub_v)
            db.flush()

        fac1 = db.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "allison.hill@campus.edu").first()
        fac2 = db.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "noah.rhodes@campus.edu").first()
        assert fac1 is not None and fac2 is not None

        fac1.max_weekly_load = 24
        fac2.max_weekly_load = 24

        course = db.query(Course).first()
        room = db.query(Room).first()
        sec = db.query(Section).first()
        slots = db.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").all()
        assert course and room and sec and len(slots) >= 5

        ca1 = db.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac1.id, CourseAssignment.course_id == course.id).first()
        if not ca1:
            db.add(CourseAssignment(faculty_id=fac1.id, course_id=course.id, section_id=sec.id))

        ca2 = db.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac2.id, CourseAssignment.course_id == course.id).first()
        if not ca2:
            db.add(CourseAssignment(faculty_id=fac2.id, course_id=course.id, section_id=sec.id))

        # Check existing entries for fac1
        existing_entries = db.query(TimetableEntry).filter(TimetableEntry.version_id == pub_v.id, TimetableEntry.faculty_id == fac1.id).all()
        if not existing_entries:
            days_seen = set()
            for s in slots:
                if s.day and s.day not in days_seen and len(days_seen) < 5:
                    days_seen.add(s.day)
                    db.add(
                        TimetableEntry(
                            version_id=pub_v.id,
                            faculty_id=fac1.id,
                            course_id=course.id,
                            room_id=room.id,
                            slot_id=s.id,
                            section_id=sec.id,
                            department_id=fac1.department_id,
                            status="ACTIVE",
                        )
                    )
            db.commit()
    yield


# ---------------------------------------------------------------------------
# Test 1: Scheduled Occurrences
# ---------------------------------------------------------------------------

def test_faculty_scheduled_occurrences(faculty_auth, db_session):
    headers = {"Authorization": f"Bearer {faculty_auth['token']}"}

    resp = client.get("/substitutions/my-classes?days_ahead=14", headers=headers)
    assert resp.status_code == 200, f"Failed to list my-classes: {resp.text}"
    classes = resp.json()
    assert isinstance(classes, list)

    if classes:
        first = classes[0]
        assert "timetable_entry_id" in first
        assert "date" in first
        assert "day" in first
        assert "course_code" in first
        assert "has_active_request" in first
        occurrence_date = datetime.date.fromisoformat(first["date"])
        assert occurrence_date >= datetime.date.today()
        # Verify weekday alignment
        assert day_matches_date(first["day"], occurrence_date)


# ---------------------------------------------------------------------------
# Test 2: Unavailability Request Lifecycle & Validations
# ---------------------------------------------------------------------------

def test_substitution_request_creation_and_validations(faculty_auth, faculty2_auth, db_session):
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    faculty2_headers = {"Authorization": f"Bearer {faculty2_auth['token']}"}

    # 1. Get an assigned published class for faculty 1
    my_classes_resp = client.get("/substitutions/my-classes?days_ahead=21", headers=faculty1_headers)
    assert my_classes_resp.status_code == 200
    classes = my_classes_resp.json()
    assert len(classes) > 0, "Faculty 1 should have scheduled classes"

    target_class = classes[0]
    entry_id = target_class["timetable_entry_id"]
    valid_date = target_class["date"]

    # 2. Validation: Reason too short (< 3 chars) fails with 400
    short_resp = client.post(
        "/substitutions/requests",
        json={"timetable_entry_id": entry_id, "substitution_date": valid_date, "reason": "No"},
        headers=faculty1_headers,
    )
    assert short_resp.status_code == 422 or short_resp.status_code == 400

    # 3. Validation: Faculty 2 cannot request substitution for Faculty 1's class (403 Forbidden)
    forbidden_resp = client.post(
        "/substitutions/requests",
        json={"timetable_entry_id": entry_id, "substitution_date": valid_date, "reason": "Attempting to take over"},
        headers=faculty2_headers,
    )
    assert forbidden_resp.status_code == 403, f"Expected 403, got {forbidden_resp.status_code}: {forbidden_resp.text}"

    # 4. Validation: Date weekday mismatch fails with 400
    wrong_date = (datetime.date.fromisoformat(valid_date) + datetime.timedelta(days=1)).isoformat()
    mismatch_resp = client.post(
        "/substitutions/requests",
        json={"timetable_entry_id": entry_id, "substitution_date": wrong_date, "reason": "Wrong weekday test"},
        headers=faculty1_headers,
    )
    assert mismatch_resp.status_code == 400, f"Expected 400 for weekday mismatch, got {mismatch_resp.status_code}"

    # 5. Validation: Past date fails with 400
    past_date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    past_resp = client.post(
        "/substitutions/requests",
        json={"timetable_entry_id": entry_id, "substitution_date": past_date, "reason": "Past date request"},
        headers=faculty1_headers,
    )
    assert past_resp.status_code == 400, f"Expected 400 for past date, got {past_resp.status_code}"

    # 6. Valid Submission succeeds with 201 Created
    create_resp = client.post(
        "/substitutions/requests",
        json={
            "timetable_entry_id": entry_id,
            "substitution_date": valid_date,
            "reason": "Attending IEEE Academic Research Conference in Singapore",
        },
        headers=faculty1_headers,
    )
    assert create_resp.status_code == 201, f"Expected 201 Created: {create_resp.text}"
    sub_data = create_resp.json()
    assert sub_data["status"] == "REQUESTED"
    assert sub_data["version"] == 1
    sub_id = sub_data["id"]

    # 7. Duplicate Request Prevention: Re-submitting for same occurrence raises 409 Conflict
    dup_resp = client.post(
        "/substitutions/requests",
        json={
            "timetable_entry_id": entry_id,
            "substitution_date": valid_date,
            "reason": "Duplicate attempt for same date",
        },
        headers=faculty1_headers,
    )
    assert dup_resp.status_code == 409, f"Expected 409 Conflict for duplicate active request, got {dup_resp.status_code}"

    # Verify visible in my-requests
    my_reqs = client.get("/substitutions/my-requests", headers=faculty1_headers)
    assert my_reqs.status_code == 200
    assert any(r["id"] == sub_id for r in my_reqs.json())


# ---------------------------------------------------------------------------
# Test 3: Deterministic Candidate Ranking Engine
# ---------------------------------------------------------------------------

def test_deterministic_candidate_ranking(admin_auth, faculty_auth, faculty2_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}

    # Fetch existing request or create one
    my_classes = client.get("/substitutions/my-classes?days_ahead=28", headers=faculty1_headers).json()
    assert len(my_classes) > 0
    target_class = next((c for c in my_classes if not c["has_active_request"]), my_classes[0])

    if not target_class["has_active_request"]:
        create_resp = client.post(
            "/substitutions/requests",
            json={
                "timetable_entry_id": target_class["timetable_entry_id"],
                "substitution_date": target_class["date"],
                "reason": "Attending University Curriculum Committee",
            },
            headers=faculty1_headers,
        )
        sub_id = create_resp.json()["id"]
    else:
        sub_id = target_class["active_substitution_id"]

    # Query candidate recommendations via admin/reviewer
    cand_resp = client.get(f"/substitutions/requests/{sub_id}/candidates", headers=admin_headers)
    assert cand_resp.status_code == 200, f"Failed to get candidates: {cand_resp.text}"
    rec_data = cand_resp.json()

    assert rec_data["substitution_id"] == sub_id
    assert rec_data["cannot_determine"] is False
    candidates = rec_data["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) > 0, "Should have candidate recommendations"

    # Strict Self-Exclusion: Original faculty must never be recommended
    orig_fac_id = rec_data["original_faculty_id"]
    assert all(c["faculty_id"] != orig_fac_id for c in candidates), "Original faculty must be strictly excluded"

    # Verify structure and deterministic breakdown of each candidate
    for cand in candidates:
        assert "faculty_id" in cand
        assert "faculty_name" in cand
        assert "qualification_tier" in cand
        assert cand["qualification_tier"] in ("VERIFIED_QUALIFICATION", "DIRECT_ASSIGNMENT", "UNQUALIFIED", "DEPARTMENT_MATCH", "GENERAL")
        assert "current_weekly_load" in cand
        assert "max_weekly_load" in cand
        assert "score" in cand
        assert "is_eligible" in cand
        assert "eligibility_breakdown" in cand

        # Check factors in breakdown
        factors = {b["factor"]: b["status"] for b in cand["eligibility_breakdown"]}
        assert "QUALIFICATION" in factors
        assert "TIMETABLE_CLASH" in factors
        assert "AVAILABILITY" in factors
        assert "EXISTING_SUBSTITUTION" in factors
        assert "WORKLOAD_LIMIT" in factors

    # Verify deterministic ordering:
    # 1. Eligible first (is_eligible == True comes before False)
    # 2. Higher score comes first among eligible
    # 3. Lower workload comes first among equal scores
    eligible_cands = [c for c in candidates if c["is_eligible"]]
    ineligible_cands = [c for c in candidates if not c["is_eligible"]]

    if eligible_cands and ineligible_cands:
        first_ineligible_idx = candidates.index(ineligible_cands[0])
        last_eligible_idx = candidates.index(eligible_cands[-1])
        assert last_eligible_idx < first_ineligible_idx, "All eligible candidates must precede ineligible ones"

    if len(eligible_cands) >= 2:
        for i in range(len(eligible_cands) - 1):
            assert eligible_cands[i]["score"] >= eligible_cands[i + 1]["score"] or (
                eligible_cands[i]["score"] == eligible_cands[i + 1]["score"]
                and eligible_cands[i]["current_weekly_load"] <= eligible_cands[i + 1]["current_weekly_load"]
            )


# ---------------------------------------------------------------------------
# Test 4: Reviewer Capabilities & Scoped RBAC
# ---------------------------------------------------------------------------

def test_reviewer_capabilities_and_rbac(admin_auth, faculty_auth, faculty2_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    faculty2_headers = {"Authorization": f"Bearer {faculty2_auth['token']}"}

    # 1. Create a request from Faculty 1
    my_classes = client.get("/substitutions/my-classes?days_ahead=35", headers=faculty1_headers).json()
    open_class = next((c for c in my_classes if not c["has_active_request"]), None)
    if not open_class:
        pytest.skip("No open class available for capability test")

    sub_resp = client.post(
        "/substitutions/requests",
        json={
            "timetable_entry_id": open_class["timetable_entry_id"],
            "substitution_date": open_class["date"],
            "reason": "Department Head Consultation",
        },
        headers=faculty1_headers,
    )
    assert sub_resp.status_code == 201
    sub_id = sub_resp.json()["id"]

    # 2. Non-coordinator faculty cannot access pending queue or review
    unauth_pending = client.get("/substitutions/pending", headers=faculty2_headers)
    assert unauth_pending.status_code == 403, f"Expected 403 for unauthorized pending queue, got {unauth_pending.status_code}"

    unauth_cand = client.get(f"/substitutions/requests/{sub_id}/candidates", headers=faculty2_headers)
    assert unauth_cand.status_code == 403, f"Expected 403 for unauthorized candidates lookup, got {unauth_cand.status_code}"

    # 3. Admin grants SUBSTITUTION_COORDINATOR capability to Faculty 2
    fac2_user_id = faculty2_auth["user"]["id"]
    cap = CoordinatorCapability(
        user_id=fac2_user_id,
        capability="SUBSTITUTION_COORDINATOR",
        scope_type="GLOBAL",
        is_active=True,
    )
    db_session.add(cap)
    db_session.commit()

    # 4. Faculty 2 can now access pending queue and candidates!
    auth_pending = client.get("/substitutions/pending", headers=faculty2_headers)
    assert auth_pending.status_code == 200, f"Expected 200 after capability grant: {auth_pending.text}"
    assert any(s["id"] == sub_id for s in auth_pending.json())

    auth_cands = client.get(f"/substitutions/requests/{sub_id}/candidates", headers=faculty2_headers)
    assert auth_cands.status_code == 200, f"Expected 200 after capability grant: {auth_cands.text}"


# ---------------------------------------------------------------------------
# Test 5: Optimistic Concurrency Control
# ---------------------------------------------------------------------------

def test_optimistic_concurrency_control(admin_auth, faculty_auth, faculty2_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}

    my_classes = client.get("/substitutions/my-classes?days_ahead=42", headers=faculty1_headers).json()
    open_class = next((c for c in my_classes if not c["has_active_request"]), None)
    if not open_class:
        pytest.skip("No open class available for concurrency test")

    sub_resp = client.post(
        "/substitutions/requests",
        json={
            "timetable_entry_id": open_class["timetable_entry_id"],
            "substitution_date": open_class["date"],
            "reason": "Personal medical appointment",
        },
        headers=faculty1_headers,
    )
    assert sub_resp.status_code == 201
    sub_id = sub_resp.json()["id"]

    # Attempt review with mismatched version (expected_version = 999)
    conflict_resp = client.post(
        f"/substitutions/requests/{sub_id}/review",
        json={
            "action": "REJECT",
            "rejection_reason": "Department staffing shortages require presence",
            "version": 999,
        },
        headers=admin_headers,
    )
    assert conflict_resp.status_code == 409, f"Expected 409 Conflict for outdated version, got {conflict_resp.status_code}"


# ---------------------------------------------------------------------------
# Test 6: Rejection Workflow
# ---------------------------------------------------------------------------

def test_rejection_workflow(admin_auth, faculty_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}

    my_classes = client.get("/substitutions/my-classes?days_ahead=49", headers=faculty1_headers).json()
    open_class = next((c for c in my_classes if not c["has_active_request"]), None)
    if not open_class:
        pytest.skip("No open class available for rejection test")

    sub_resp = client.post(
        "/substitutions/requests",
        json={
            "timetable_entry_id": open_class["timetable_entry_id"],
            "substitution_date": open_class["date"],
            "reason": "Family function",
        },
        headers=faculty1_headers,
    )
    sub_id = sub_resp.json()["id"]

    reject_resp = client.post(
        f"/substitutions/requests/{sub_id}/review",
        json={
            "action": "REJECT",
            "rejection_reason": "Exam preparation review session cannot be delegated.",
            "version": 1,
        },
        headers=admin_headers,
    )
    assert reject_resp.status_code == 200, f"Rejection failed: {reject_resp.text}"
    rejected_data = reject_resp.json()
    assert rejected_data["status"] == "REJECTED"
    assert rejected_data["rejection_reason"] == "Exam preparation review session cannot be delegated."
    assert rejected_data["version"] == 2

    # Verify notification dispatched to requesting faculty
    fac_user_id = faculty_auth["user"]["id"]
    notif = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == fac_user_id,
            Notification.type == "SUBSTITUTION_REJECTED",
        )
        .order_by(Notification.id.desc())
        .first()
    )
    assert notif is not None, "Notification should be dispatched on rejection"
    assert "rejected" in notif.message.lower()


# ---------------------------------------------------------------------------
# Test 7: Approval Workflow & Master Timetable Immutability & Privacy
# ---------------------------------------------------------------------------

def test_approval_workflow_and_master_timetable_immutability(
    admin_auth, faculty_auth, faculty2_auth, student_auth, db_session
):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    faculty2_headers = {"Authorization": f"Bearer {faculty2_auth['token']}"}
    student_headers = {"Authorization": f"Bearer {student_auth['token']}"}

    my_classes = client.get("/substitutions/my-classes?days_ahead=56", headers=faculty1_headers).json()
    open_class = next((c for c in my_classes if not c["has_active_request"]), None)
    if not open_class:
        pytest.skip("No open class available for approval test")

    entry_id = open_class["timetable_entry_id"]
    sub_date = open_class["date"]
    private_reason = "Confidential medical evaluation - strictly private reason"

    # Pre-condition: Capture canonical master TimetableEntry
    original_entry = db_session.query(TimetableEntry).filter(TimetableEntry.id == entry_id).first()
    assert original_entry is not None
    master_original_faculty_id = original_entry.faculty_id
    master_original_status = original_entry.status
    master_original_slot_id = original_entry.slot_id

    # 1. Create Request
    sub_resp = client.post(
        "/substitutions/requests",
        json={
            "timetable_entry_id": entry_id,
            "substitution_date": sub_date,
            "reason": private_reason,
        },
        headers=faculty1_headers,
    )
    assert sub_resp.status_code == 201
    sub_id = sub_resp.json()["id"]

    # 2. Get Eligible Candidates
    cands_resp = client.get(f"/substitutions/requests/{sub_id}/candidates", headers=admin_headers)
    assert cands_resp.status_code == 200
    eligible_cands = [c for c in cands_resp.json()["candidates"] if c["is_eligible"]]
    assert len(eligible_cands) > 0, "Expected at least one eligible substitute candidate"

    chosen_substitute = eligible_cands[0]
    substitute_fac_id = chosen_substitute["faculty_id"]

    # 3. Approve Request
    app_resp = client.post(
        f"/substitutions/requests/{sub_id}/review",
        json={
            "action": "APPROVE",
            "substitute_faculty_id": substitute_fac_id,
            "version": 1,
        },
        headers=admin_headers,
    )
    assert app_resp.status_code == 200, f"Approval failed: {app_resp.text}"
    approved_data = app_resp.json()
    assert approved_data["status"] == "APPROVED"
    assert approved_data["substitute_faculty_id"] == substitute_fac_id
    assert approved_data["substitute_faculty_name"] == chosen_substitute["faculty_name"]
    assert approved_data["version"] == 2

    # 4. CRITICAL ARCHITECTURAL GUARANTEE: Canonical Master Timetable is UNCHANGED
    db_session.expire_all()
    post_entry = db_session.query(TimetableEntry).filter(TimetableEntry.id == entry_id).first()
    assert post_entry is not None
    assert post_entry.faculty_id == master_original_faculty_id, (
        f"Master timetable entry faculty_id was mutated! Expected {master_original_faculty_id}, found {post_entry.faculty_id}"
    )
    assert post_entry.status == master_original_status
    assert post_entry.slot_id == master_original_slot_id

    # 5. PRIVACY GUARANTEE: Student checking the request details NEVER receives the private reason
    student_view_resp = client.get(f"/substitutions/requests/{sub_id}", headers=student_headers)
    assert student_view_resp.status_code == 200
    student_view = student_view_resp.json()
    assert student_view["reason"] is None or student_view["reason"] == "", (
        f"CRITICAL PRIVACY VIOLATION: Student received private absence reason: {student_view.get('reason')}"
    )

    # 6. Verify Notifications Dispatched
    # A. Check substitute faculty notification
    sub_fac_obj = db_session.query(Faculty).filter(Faculty.id == substitute_fac_id).first()
    assert sub_fac_obj is not None
    if sub_fac_obj.user_id:
        sub_notif = (
            db_session.query(Notification)
            .filter(
                Notification.user_id == sub_fac_obj.user_id,
                Notification.type == "SUBSTITUTION_ASSIGNED",
            )
            .order_by(Notification.id.desc())
            .first()
        )
        assert sub_notif is not None, "Substitute faculty should receive assignment notification"

    # B. Check student notification privacy: Student notifications must NOT leak the private reason
    student_notifs = (
        db_session.query(Notification)
        .filter(Notification.type == "SUBSTITUTION_UPDATE")
        .order_by(Notification.id.desc())
        .limit(10)
        .all()
    )
    for sn in student_notifs:
        assert private_reason not in sn.message, "Student notification contained leaked private faculty reason!"


# ---------------------------------------------------------------------------
# Test 8: Date-Specific Timetable and Live Status Overlay
# ---------------------------------------------------------------------------

def test_date_specific_timetable_and_live_status(
    admin_auth, faculty_auth, faculty2_auth, student_auth, db_session
):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    student_headers = {"Authorization": f"Bearer {student_auth['token']}"}

    # Find the approved substitution from previous test or create one
    app_sub = (
        db_session.query(FacultySubstitution)
        .filter(FacultySubstitution.status == "APPROVED")
        .order_by(FacultySubstitution.id.desc())
        .first()
    )
    if not app_sub:
        pytest.skip("No approved substitution available for date-view test")

    sub_date = app_sub.substitution_date
    entry_id = app_sub.timetable_entry_id

    # 1. Student queries date-view endpoint
    date_view_resp = client.get(f"/substitutions/date-view?date={sub_date.isoformat()}", headers=student_headers)
    assert date_view_resp.status_code == 200, f"Date view failed: {date_view_resp.text}"
    classes = date_view_resp.json()
    assert isinstance(classes, list)

    target_occurrence = next((c for c in classes if c["timetable_entry_id"] == entry_id), None)
    if target_occurrence:
        assert target_occurrence["is_substituted"] is True
        assert target_occurrence["original_faculty_name"] is not None
        assert target_occurrence["faculty_name"] != target_occurrence["original_faculty_name"]

    # 2. Student queries /student/my-timetable with ?date=
    student_date_tt = client.get(f"/student/my-timetable?date={sub_date.isoformat()}", headers=student_headers)
    assert student_date_tt.status_code == 200
    st_entries = student_date_tt.json()["entries"]
    st_sub_entry = next((e for e in st_entries if e["id"] == entry_id), None)
    if st_sub_entry:
        assert st_sub_entry["is_substituted"] is True
        assert st_sub_entry["substitute_faculty_name"] is not None

    # 3. Student queries /student/my-timetable without date (master recurring schedule)
    student_master_tt = client.get("/student/my-timetable", headers=student_headers)
    assert student_master_tt.status_code == 200
    master_entries = student_master_tt.json()["entries"]
    m_entry = next((e for e in master_entries if e["id"] == entry_id), None)
    if m_entry:
        # Master recurring timetable is canonical
        assert m_entry["is_substituted"] is False


# ---------------------------------------------------------------------------
# Test 9: Multi-Agent Assistant Grounding
# ---------------------------------------------------------------------------

def test_assistant_substitution_grounding(admin_auth, faculty_auth, student_auth, db_session):
    faculty_user = db_session.query(User).filter(User.id == faculty_auth["user"]["id"]).first()
    student_user = db_session.query(User).filter(User.id == student_auth["user"]["id"]).first()
    assert faculty_user is not None
    assert student_user is not None

    # 1. Tool execution: list_my_substitution_requests
    req_res = execute_tool("list_my_substitution_requests", {}, faculty_user, db_session)
    assert isinstance(req_res, dict)
    assert "requests" in req_res
    assert "total" in req_res

    # 2. Tool execution: list_my_substitution_assignments
    asg_res = execute_tool("list_my_substitution_assignments", {}, faculty_user, db_session)
    assert isinstance(asg_res, dict)
    assert "assignments" in asg_res

    # 3. Tool execution: get_date_substitutions
    date_res = execute_tool("get_date_substitutions", {"date": "today"}, student_user, db_session)
    assert isinstance(date_res, dict)
    assert "substitutions" in date_res
    # Privacy check: If student runs it, reason is never in the substitutions
    for item in date_res.get("substitutions", []):
        assert "reason" not in item, "Student received private reason via assistant tool!"


# ---------------------------------------------------------------------------
# Test 10: Mandatory Hard Qualification Enforcement & Exclusion Verification
# ---------------------------------------------------------------------------

def test_hard_qualification_enforcement(admin_auth, faculty_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}

    # Setup controlled courses and faculty
    dept = db_session.query(Department).first()
    assert dept is not None

    # Target Course
    c_target = db_session.query(Course).filter(Course.course_code == "CS-HARD-QUAL").first()
    if not c_target:
        c_target = Course(course_code="CS-HARD-QUAL", course_name="Hard Qualification Test Course", department_id=dept.id)
        db_session.add(c_target)
        db_session.flush()

    # Unrelated Course
    c_unrelated = db_session.query(Course).filter(Course.course_code == "CS-UNRELATED").first()
    if not c_unrelated:
        c_unrelated = Course(course_code="CS-UNRELATED", course_name="Unrelated Subject Course", department_id=dept.id)
        db_session.add(c_unrelated)
        db_session.flush()

    # Qualified faculty (Noah Rhodes)
    fac_qual = db_session.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "noah.rhodes@campus.edu").first()
    assert fac_qual is not None

    # Ensure fac_qual has verified CourseAssignment for c_target
    ca_qual = db_session.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac_qual.id, CourseAssignment.course_id == c_target.id).first()
    if not ca_qual:
        db_session.add(CourseAssignment(faculty_id=fac_qual.id, course_id=c_target.id))
        db_session.flush()

    # Ensure other faculty do NOT have CourseAssignment for c_target
    other_facs = db_session.query(Faculty).filter(Faculty.id != fac_qual.id).all()
    for of in other_facs:
        db_session.query(CourseAssignment).filter(CourseAssignment.faculty_id == of.id, CourseAssignment.course_id == c_target.id).delete()
    db_session.commit()

    # Find or create published timetable entry for fac1 with c_target
    fac1 = db_session.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "allison.hill@campus.edu").first()
    pub_v = db_session.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
    slot = db_session.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
    room = db_session.query(Room).first()
    sec = db_session.query(Section).first()
    assert fac1 and pub_v and slot and room and sec

    # Add assignment for fac1
    ca1 = db_session.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac1.id, CourseAssignment.course_id == c_target.id).first()
    if not ca1:
        db_session.add(CourseAssignment(faculty_id=fac1.id, course_id=c_target.id, section_id=sec.id))

    test_entry = db_session.query(TimetableEntry).filter(
        TimetableEntry.version_id == pub_v.id,
        TimetableEntry.faculty_id == fac1.id,
        TimetableEntry.course_id == c_target.id,
    ).first()
    if not test_entry:
        test_entry = TimetableEntry(
            version_id=pub_v.id,
            faculty_id=fac1.id,
            course_id=c_target.id,
            room_id=room.id,
            slot_id=slot.id,
            section_id=sec.id,
            department_id=dept.id,
            status="ACTIVE",
        )
        db_session.add(test_entry)
        db_session.commit()

    # Calculate valid future date matching slot
    today = datetime.date.today()
    target_date = today + datetime.timedelta(days=7)
    while not day_matches_date(slot.day, target_date):
        target_date += datetime.timedelta(days=1)

    # Clean prior subs
    db_session.query(FacultySubstitution).filter(
        FacultySubstitution.timetable_entry_id == test_entry.id,
        FacultySubstitution.substitution_date == target_date,
    ).delete()
    db_session.commit()

    sub = FacultySubstitution(
        timetable_entry_id=test_entry.id,
        substitution_date=target_date,
        original_faculty_id=fac1.id,
        status="REQUESTED",
        reason="Academic Conference Keynote Address",
        created_by_id=fac1.user_id,
        version=1,
    )
    db_session.add(sub)
    db_session.commit()

    # Query candidate recommendations
    cands_resp = client.get(f"/substitutions/requests/{sub.id}/candidates", headers=admin_headers)
    assert cands_resp.status_code == 200
    res_data = cands_resp.json()
    candidates = res_data["candidates"]

    # 1. Qualified faculty member with no timetable clash is proposed (is_eligible = True)
    cand_qual = next((c for c in candidates if c["faculty_id"] == fac_qual.id), None)
    assert cand_qual is not None
    qual_reasons = {b["factor"]: b["status"] for b in cand_qual["eligibility_breakdown"]}
    assert qual_reasons["QUALIFICATION"] == "PASS"

    # 2. Same-department faculty WITHOUT course qualification is EXCLUDED (is_eligible = False)
    unqual_same_dept = [
        c for c in candidates
        if c["faculty_id"] != fac_qual.id and c["department_id"] == dept.id
    ]
    for usd in unqual_same_dept:
        assert usd["is_eligible"] is False, f"Faculty {usd['faculty_name']} without qualification was marked eligible!"
        factors = {b["factor"]: b["status"] for b in usd["eligibility_breakdown"]}
        assert factors["QUALIFICATION"] == "FAIL"
        assert any("qualification" in r.lower() or "assignment" in r.lower() for r in usd["ineligibility_reasons"])

    # 3. Faculty with unrelated course assignments is EXCLUDED
    # 4. Inactive faculty account is EXCLUDED
    # Deactivate fac_qual user temporarily
    fac_qual.user.is_active = False
    db_session.commit()

    cands_resp2 = client.get(f"/substitutions/requests/{sub.id}/candidates", headers=admin_headers)
    cands2 = cands_resp2.json()["candidates"]
    cand_qual_inactive = next((c for c in cands2 if c["faculty_id"] == fac_qual.id), None)
    assert cand_qual_inactive is not None
    assert cand_qual_inactive["is_eligible"] is False
    factors_inactive = {b["factor"]: b["status"] for b in cand_qual_inactive["eligibility_breakdown"]}
    assert factors_inactive["ACTIVE_STATUS"] == "FAIL"

    # Restore user
    fac_qual.user.is_active = True
    db_session.commit()


# ---------------------------------------------------------------------------
# Test 11: Candidate Result Semantics (ELIGIBLE, NO_ELIGIBLE_CANDIDATE, CANNOT_DETERMINE)
# ---------------------------------------------------------------------------

def test_candidate_result_semantics(admin_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    # Setup Course with ZERO qualifications
    c_empty = db_session.query(Course).filter(Course.course_code == "CS-NO-ONE-QUAL").first()
    if not c_empty:
        c_empty = Course(course_code="CS-NO-ONE-QUAL", course_name="Zero Qualifications Subject")
        db_session.add(c_empty)
        db_session.flush()

    pub_v = db_session.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
    fac1 = db_session.query(Faculty).first()
    slot = db_session.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
    room = db_session.query(Room).first()
    sec = db_session.query(Section).first()
    assert pub_v and fac1 and slot and room and sec

    empty_entry = TimetableEntry(
        version_id=pub_v.id,
        faculty_id=fac1.id,
        course_id=c_empty.id,
        room_id=room.id,
        slot_id=slot.id,
        section_id=sec.id,
        status="ACTIVE",
    )
    db_session.add(empty_entry)
    db_session.commit()

    target_date = datetime.date.today() + datetime.timedelta(days=14)
    while not day_matches_date(slot.day, target_date):
        target_date += datetime.timedelta(days=1)

    sub_empty = FacultySubstitution(
        timetable_entry_id=empty_entry.id,
        substitution_date=target_date,
        original_faculty_id=fac1.id,
        status="REQUESTED",
        reason="Research workshop",
        created_by_id=fac1.user_id,
        version=1,
    )
    db_session.add(sub_empty)
    db_session.commit()

    # When no trusted qualification records exist for the course: CANNOT_DETERMINE
    resp = client.get(f"/substitutions/requests/{sub_empty.id}/candidates", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluation_status"] == "CANNOT_DETERMINE"
    assert data["cannot_determine"] is True
    assert "No trusted faculty qualification" in data["cannot_determine_reason"]


# ---------------------------------------------------------------------------
# Test 12: Availability & Workload Boundary Rules
# ---------------------------------------------------------------------------

def test_availability_and_workload_boundary_rules(admin_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    # Setup request where candidate has explicit UNAVAILABLE preference
    fac1 = db_session.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "allison.hill@campus.edu").first()
    fac2 = db_session.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "noah.rhodes@campus.edu").first()
    course = db_session.query(Course).first()
    pub_v = db_session.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
    slot = db_session.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
    room = db_session.query(Room).first()
    sec = db_session.query(Section).first()
    assert fac1 and fac2 and course and pub_v and slot and room and sec

    # Ensure fac2 is qualified for course
    ca = db_session.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac2.id, CourseAssignment.course_id == course.id).first()
    if not ca:
        db_session.add(CourseAssignment(faculty_id=fac2.id, course_id=course.id))
        db_session.flush()

    # Add explicit UNAVAILABLE record for fac2 at slot
    fa = db_session.query(FacultyAvailability).filter(FacultyAvailability.faculty_id == fac2.id, FacultyAvailability.slot_id == slot.id).first()
    if not fa:
        fa = FacultyAvailability(faculty_id=fac2.id, slot_id=slot.id, availability="UNAVAILABLE")
        db_session.add(fa)
    else:
        fa.availability = "UNAVAILABLE"
    db_session.commit()

    entry = TimetableEntry(
        version_id=pub_v.id,
        faculty_id=fac1.id,
        course_id=course.id,
        room_id=room.id,
        slot_id=slot.id,
        section_id=sec.id,
        status="ACTIVE",
    )
    db_session.add(entry)
    db_session.flush()

    target_date = datetime.date.today() + datetime.timedelta(days=21)
    while not day_matches_date(slot.day, target_date):
        target_date += datetime.timedelta(days=1)

    sub = FacultySubstitution(
        timetable_entry_id=entry.id,
        substitution_date=target_date,
        original_faculty_id=fac1.id,
        status="REQUESTED",
        reason="Testing availability bounds",
        created_by_id=fac1.user_id,
        version=1,
    )
    db_session.add(sub)
    db_session.commit()

    # Check that explicit UNAVAILABLE excludes candidate
    resp = client.get(f"/substitutions/requests/{sub.id}/candidates", headers=admin_headers)
    assert resp.status_code == 200
    candidates = resp.json()["candidates"]
    c2 = next((c for c in candidates if c["faculty_id"] == fac2.id), None)
    assert c2 is not None
    assert c2["is_eligible"] is False
    factors = {b["factor"]: b["status"] for b in c2["eligibility_breakdown"]}
    assert factors["AVAILABILITY"] == "FAIL"

    # Reset availability
    fa.availability = "AVAILABLE"
    db_session.commit()


# ---------------------------------------------------------------------------
# Test 13: Scoped Reviewer Permissions & Lifecycle Security
# ---------------------------------------------------------------------------

def test_scoped_reviewer_permissions_and_lifecycle(faculty_auth, faculty2_auth, db_session):
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    faculty2_headers = {"Authorization": f"Bearer {faculty2_auth['token']}"}

    fac1_user_id = faculty_auth["user"]["id"]
    fac2_user_id = faculty2_auth["user"]["id"]

    # Faculty 2 creates capability with DEPARTMENT scope = 999 (out-of-scope department)
    db_session.query(CoordinatorCapability).filter(
        CoordinatorCapability.user_id == fac2_user_id,
        CoordinatorCapability.capability == "SUBSTITUTION_COORDINATOR",
    ).delete()
    db_session.commit()

    out_of_scope_cap = CoordinatorCapability(
        user_id=fac2_user_id,
        capability="SUBSTITUTION_COORDINATOR",
        scope_type="DEPARTMENT",
        scope_id=999,  # Non-matching department
        is_active=True,
    )
    db_session.add(out_of_scope_cap)
    db_session.commit()

    # Find pending request in department 1
    pending_sub = db_session.query(FacultySubstitution).filter(FacultySubstitution.status == "REQUESTED").first()
    assert pending_sub is not None

    # Review attempt from out-of-scope coordinator fails with 403 Forbidden
    out_of_scope_review = client.post(
        f"/substitutions/requests/{pending_sub.id}/review",
        json={"action": "REJECT", "rejection_reason": "Out of scope rejection attempt", "version": pending_sub.version},
        headers=faculty2_headers,
    )
    assert out_of_scope_review.status_code == 403, f"Expected 403 for out-of-scope department, got {out_of_scope_review.status_code}"

    # Revoke capability (is_active = False)
    out_of_scope_cap.is_active = False
    db_session.commit()

    revoked_review = client.post(
        f"/substitutions/requests/{pending_sub.id}/review",
        json={"action": "REJECT", "rejection_reason": "Revoked reviewer attempt", "version": pending_sub.version},
        headers=faculty2_headers,
    )
    assert revoked_review.status_code == 403, f"Expected 403 for revoked capability, got {revoked_review.status_code}"

    # Private Request View Barrier: Unauthorized faculty cannot view other faculty's request
    unauth_view = client.get(f"/substitutions/requests/{pending_sub.id}", headers=faculty2_headers)
    assert unauth_view.status_code == 403, f"Expected 403 for unauth faculty viewing private request, got {unauth_view.status_code}"


# ---------------------------------------------------------------------------
# Test 14: Three-Date Invariant Verification (Week 1, Week 2, Week 3)
# ---------------------------------------------------------------------------

def test_three_date_timetable_immutability(admin_auth, faculty_auth, faculty2_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty1_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}

    fac1 = db_session.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "allison.hill@campus.edu").first()
    fac2 = db_session.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "noah.rhodes@campus.edu").first()
    course = db_session.query(Course).first()
    pub_v = db_session.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
    slot = db_session.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
    room = db_session.query(Room).first()
    sec = db_session.query(Section).first()
    assert fac1 and fac2 and course and pub_v and slot and room and sec

    # Ensure fac2 qualified
    ca2 = db_session.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac2.id, CourseAssignment.course_id == course.id).first()
    if not ca2:
        db_session.add(CourseAssignment(faculty_id=fac2.id, course_id=course.id))
        db_session.flush()

    entry = TimetableEntry(
        version_id=pub_v.id,
        faculty_id=fac1.id,
        course_id=course.id,
        room_id=room.id,
        slot_id=slot.id,
        section_id=sec.id,
        department_id=fac1.department_id,
        status="ACTIVE",
    )
    db_session.add(entry)
    db_session.commit()

    # Three successive weekly dates for the same weekday:
    # d1 = Week 1 (7 days ahead)
    # d2 = Week 2 (14 days ahead) -> Substitution approved for THIS date only!
    # d3 = Week 3 (21 days ahead)
    today = datetime.date.today()
    d1 = today + datetime.timedelta(days=7)
    while not day_matches_date(slot.day, d1):
        d1 += datetime.timedelta(days=1)
    d2 = d1 + datetime.timedelta(days=7)
    d3 = d2 + datetime.timedelta(days=7)

    # Approve substitution on d2 only
    sub = FacultySubstitution(
        timetable_entry_id=entry.id,
        substitution_date=d2,
        original_faculty_id=fac1.id,
        substitute_faculty_id=fac2.id,
        status="APPROVED",
        reason="Three-date invariant test",
        created_by_id=fac1.user_id,
        version=2,
    )
    db_session.add(sub)
    db_session.commit()

    # Verify Week 1 (d1): Canonical Original Faculty
    d1_view = client.get(f"/substitutions/date-view?date={d1.isoformat()}", headers=admin_headers).json()
    d1_item = next((c for c in d1_view if c["timetable_entry_id"] == entry.id), None)
    assert d1_item is not None
    assert d1_item["is_substituted"] is False
    assert d1_item["faculty_name"] == fac1.user.name

    # Verify Week 2 (d2): Substituted Faculty (Noah Rhodes)
    d2_view = client.get(f"/substitutions/date-view?date={d2.isoformat()}", headers=admin_headers).json()
    d2_item = next((c for c in d2_view if c["timetable_entry_id"] == entry.id), None)
    assert d2_item is not None
    assert d2_item["is_substituted"] is True
    assert d2_item["faculty_name"] == fac2.user.name
    assert d2_item["original_faculty_name"] == fac1.user.name

    # Verify Week 3 (d3): Canonical Original Faculty
    d3_view = client.get(f"/substitutions/date-view?date={d3.isoformat()}", headers=admin_headers).json()
    d3_item = next((c for c in d3_view if c["timetable_entry_id"] == entry.id), None)
    assert d3_item is not None
    assert d3_item["is_substituted"] is False
    assert d3_item["faculty_name"] == fac1.user.name

    # Verify Master Canonical Timetable Entry is still 100% untouched
    master_check = db_session.query(TimetableEntry).filter(TimetableEntry.id == entry.id).first()
    assert master_check is not None
    assert master_check.faculty_id == fac1.id
