"""
tests/test_stage13_e2e_acceptance.py
------------------------------------
Stage 13: Real End-to-End Functional Acceptance & Verification Suite.
Executes and asserts every required workflow against real APIs, PostgreSQL state,
role boundaries, notifications, resource locks, and the AI assistant.
"""

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config import engine
from backend.main import app
from backend.models.academic import AcademicYear, Department, Faculty, Program, Section, Semester, Student
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import Notification
from backend.services.notification_service import stream_broker

client = TestClient(app)


# ── Fixtures & Tokens ─────────────────────────────────────────────────────────

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


@pytest.fixture(scope="module")
def other_faculty_token():
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Other faculty login failed: {resp.text}"
    return resp.json()["access_token"]


# ── WORKFLOW A: Timetable Lifecycle & Targeted Notification Delivery ──────────

def test_workflow_a_timetable_publication_and_notifications(admin_token, faculty_token, student_token):
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        dept = db.query(Department).first()
        prog = db.query(Program).filter(Program.department_id == dept.id).first() if dept else None
        sem = db.query(Semester).first()
        sec = db.query(Section).filter(Section.semester_id == sem.id).first() if sem else None
        fac = db.query(Faculty).filter(Faculty.user_id.isnot(None)).first()
        student = db.query(Student).filter(Student.section_id == sec.id, Student.user_id.isnot(None)).first() if sec else None
        course = db.query(Course).first()
        room = db.query(Room).first()
        slot = db.query(TimeSlot).first()
        admin_user = db.query(User).filter(User.role == "ADMIN").first()

        assert all([ac_year, dept, prog, sem, sec, fac, student, course, room, slot, admin_user]), "Missing prerequisite seed records"
        assert ac_year and dept and prog and sem and sec and fac and student and course and room and slot and admin_user

        # Create an isolated test timetable version in FINALIZED status
        version = TimetableVersion(
            academic_year_id=ac_year.id,
            version_number="v99.0",
            status="FINALIZED",
            created_by=admin_user.id,
        )
        db.add(version)
        db.flush()

        entry = TimetableEntry(
            version_id=version.id,
            department_id=dept.id,
            program_id=prog.id,
            semester_id=sem.id,
            section_id=sec.id,
            course_id=course.id,
            faculty_id=fac.id,
            room_id=room.id,
            slot_id=slot.id,
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()

        v_id = version.id
        fac_uid = fac.user_id
        stud_uid = student.user_id

    # 1. Publish timetable via API
    resp = client.post(
        f"/timetable/versions/{v_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Publish API failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "PUBLISHED"

    # 2. Assert persisted DB status
    with Session(engine) as db:
        v_db = db.query(TimetableVersion).filter(TimetableVersion.id == v_id).first()
        assert v_db is not None
        assert v_db.status == "PUBLISHED"

        # 3. Assert notifications created for affected faculty and student
        fac_notif = (
            db.query(Notification)
            .filter(
                Notification.user_id == fac_uid,
                Notification.entity_type == "TimetableVersion",
                Notification.entity_id == v_id,
            )
            .first()
        )
        assert fac_notif is not None
        assert fac_notif.title and "Timetable Published" in fac_notif.title
        assert fac_notif.link == "/faculty/timetable"

        stud_notif = (
            db.query(Notification)
            .filter(
                Notification.user_id == stud_uid,
                Notification.entity_type == "TimetableVersion",
                Notification.entity_id == v_id,
            )
            .first()
        )
        assert stud_notif is not None
        assert stud_notif.title and "Timetable Published" in stud_notif.title
        assert stud_notif.link == "/student/timetable"

    # 4. Unauthorized publish attempt by student is rejected
    unauth_resp = client.post(
        f"/timetable/versions/{v_id}/publish",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert unauth_resp.status_code == 403

    # 5. Re-publishing an already published version is rejected by the lifecycle state machine (409 Conflict)
    repub_resp = client.post(
        f"/timetable/versions/{v_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert repub_resp.status_code == 409


# ── WORKFLOW B: Resource Booking & Global Resource Locking Policy ─────────────

def test_workflow_b_resource_booking_and_global_locks(admin_token, faculty_token, other_faculty_token, student_token):
    with Session(engine) as db:
        allison = db.query(User).filter(User.email == "allison.hill@campus.edu").first()
        resource = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        assert allison and resource

        res_id = resource.id
        fac_uid = allison.id
        booking_date = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()

    # 1. Faculty submits booking request
    book_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": booking_date,
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "purpose": "Stage 13 Capstone Verification Session",
        },
    )
    assert book_resp.status_code == 201, f"Booking creation failed: {book_resp.text}"
    booking_data = book_resp.json()
    booking_id = booking_data["id"]
    assert booking_data["status"] == "PENDING"

    # Verify DB persistence of PENDING status
    with Session(engine) as db:
        b_db = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
        assert b_db is not None
        assert b_db.status == "PENDING"
        assert b_db.requested_by == fac_uid

    # 2. Conflicting booking attempt while PENDING is rejected by global lock policy
    conflict_pending_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {other_faculty_token}"},
        json={
            "resource_id": res_id,
            "date": booking_date,
            "start_time": "14:30:00",
            "end_time": "15:30:00",
            "purpose": "Conflicting Booking Attempt during Pending Lock",
        },
    )
    assert conflict_pending_resp.status_code == 409, "Pending booking failed to globally lock resource"

    # 3. Admin approves booking
    appr_resp = client.post(
        f"/resources/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "APPROVED"

    # Verify DB status is APPROVED
    with Session(engine) as db:
        b_db = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
        assert b_db is not None
        assert b_db.status == "APPROVED"

        # Verify approval notification generated for faculty
        appr_notif = (
            db.query(Notification)
            .filter(
                Notification.user_id == fac_uid,
                Notification.entity_type == "ResourceBooking",
                Notification.entity_id == booking_id,
                Notification.type == "BOOKING_APPROVED",
            )
            .first()
        )
        assert appr_notif is not None

    # 4. Conflicting booking attempt while APPROVED is rejected by global lock policy
    conflict_approved_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {other_faculty_token}"},
        json={
            "resource_id": res_id,
            "date": booking_date,
            "start_time": "15:00:00",
            "end_time": "17:00:00",
            "purpose": "Conflicting Booking Attempt during Approved Lock",
        },
    )
    assert conflict_approved_resp.status_code == 409, "Approved booking failed to globally lock resource"

    # 5. Unauthorized approval attempt by student is rejected
    unauth_appr = client.post(
        f"/resources/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert unauth_appr.status_code == 403

    # 6. Faculty cancels booking -> releases lock
    cancel_resp = client.post(
        f"/resources/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"reason": "Session reschedule"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # 7. Verify lock is released: other faculty can now successfully book the slot
    rebook_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {other_faculty_token}"},
        json={
            "resource_id": res_id,
            "date": booking_date,
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "purpose": "Legitimate booking after lock release",
        },
    )
    assert rebook_resp.status_code == 201


# ── WORKFLOW C: AI Assistant Proposal Lifecycle & Confirmation ────────────────

def test_workflow_c_ai_assistant_proposal_and_confirmation(admin_token, faculty_token, student_token):
    # 1. Informational Query: ground schedule from database
    query_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": "Show my schedule for today"},
    )
    assert query_resp.status_code == 200
    data = query_resp.json()
    assert data["success"] is True
    assert data["reply"] and len(data["reply"]) > 0

    # 2. Consequential request: creates an operation proposal for approval
    with Session(engine) as db:
        res = Resource(name="Ops Stage13 Hall", resource_type="SEMINAR_HALL", capacity=80, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        res_id = res.id

    b_date = (datetime.date.today() + datetime.timedelta(days=25)).isoformat()

    # Create pending booking via API
    b_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": b_date,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Faculty Colloquium",
        },
    )
    assert b_resp.status_code == 201
    booking_id = b_resp.json()["id"]

    # Admin prepares approval through assistant
    prep_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"Approve booking #{booking_id}"},
    )
    assert prep_resp.status_code == 200
    prep_data = prep_resp.json()
    proposal = prep_data.get("proposal")
    assert proposal is not None, "Consequential operation did not generate an operation proposal"
    assert proposal["proposal_id"].startswith("op_prop_")
    assert proposal["action_name"] == "APPROVE_RESOURCE_BOOKING"

    # Admin confirms: "Yes, proceed"
    confirm_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Yes, proceed"},
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert "approved successfully" in confirm_data["reply"].lower()

    # Assert underlying DB mutation occurred exactly once
    with Session(engine) as db:
        booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
        assert booking is not None
        assert booking.status == "APPROVED"

    # Re-confirming when no proposal is active reports honest status
    reconfirm_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Yes, proceed"},
    )
    assert reconfirm_resp.status_code == 200
    assert "no pending proposal" in reconfirm_resp.json()["reply"].lower()


# ── WORKFLOW D: Notification Delivery & Read State ────────────────────────────

@pytest.mark.anyio
async def test_workflow_d_notification_delivery_and_read_mutations(faculty_token, student_token):
    # 1. Fetch unread count
    count_resp = client.get("/notifications/unread-count", headers={"Authorization": f"Bearer {faculty_token}"})
    assert count_resp.status_code == 200
    assert "unread_count" in count_resp.json()

    # 2. Fetch notification list
    list_resp = client.get("/notifications?limit=10", headers={"Authorization": f"Bearer {faculty_token}"})
    assert list_resp.status_code == 200
    notifs = list_resp.json()
    assert isinstance(notifs, list)

    if notifs:
        target_notif = notifs[0]
        t_id = target_notif["id"]

        # 3. Mark single notification as read
        patch_resp = client.patch(f"/notifications/{t_id}/read", headers={"Authorization": f"Bearer {faculty_token}"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_read"] is True

        # 4. Cross-user isolation: student cannot mark faculty's notification as read
        cross_resp = client.patch(f"/notifications/{t_id}/read", headers={"Authorization": f"Bearer {student_token}"})
        assert cross_resp.status_code == 403

    # 5. Mark all as read
    mark_all_resp = client.post("/notifications/mark-all-read", headers={"Authorization": f"Bearer {faculty_token}"})
    assert mark_all_resp.status_code == 200

    # 6. Assert unread count is now 0
    zero_count_resp = client.get("/notifications/unread-count", headers={"Authorization": f"Bearer {faculty_token}"})
    assert zero_count_resp.status_code == 200
    assert zero_count_resp.json()["unread_count"] == 0

    # 7. Test SSE stream broker publish & queue reception
    test_uid = 88888
    q = await stream_broker.subscribe(test_uid)
    try:
        notif = Notification(
            id=12345,
            user_id=test_uid,
            title="Stage 13 Stream Test",
            message="Verified live SSE broker delivery",
            type="LIVE_TEST",
            is_read=False,
        )
        stream_broker.publish_notification(test_uid, notif)
        assert not q.empty()
        item = q.get_nowait()
        assert item["id"] == 12345
        assert item["title"] == "Stage 13 Stream Test"
    finally:
        await stream_broker.unsubscribe(test_uid, q)


# ── WORKFLOW E: Role-Based Access Control (RBAC) ──────────────────────────────

def test_workflow_e_role_based_access_control(admin_token, faculty_token, student_token):
    # 1. Admin authorized operations succeed
    admin_get_resp = client.get("/departments/", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_get_resp.status_code == 200

    admin_post_resp = client.post(
        "/notifications/admin/broadcast",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Campus Notice", "message": "Notice content", "target_role": "ALL"},
    )
    assert admin_post_resp.status_code == 200

    # 2. Faculty permitted access succeeds
    fac_timetable_resp = client.get("/faculty/my-timetable", headers={"Authorization": f"Bearer {faculty_token}"})
    assert fac_timetable_resp.status_code == 200

    # 3. Faculty attempting administrative broadcast is forbidden (403)
    fac_forbidden_resp = client.post(
        "/notifications/admin/broadcast",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"title": "Unauthorized Notice", "message": "Illegal"},
    )
    assert fac_forbidden_resp.status_code == 403

    # 4. Student permitted access succeeds
    stud_timetable_resp = client.get("/student/my-timetable", headers={"Authorization": f"Bearer {student_token}"})
    assert stud_timetable_resp.status_code == 200

    # 5. Student attempting timetable publish is forbidden (403)
    stud_forbidden_resp = client.post(
        "/timetable/versions/1/publish",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert stud_forbidden_resp.status_code == 403

    # 6. Student attempting faculty timetable access is forbidden (403)
    cross_role_resp = client.get("/faculty/my-timetable", headers={"Authorization": f"Bearer {student_token}"})
    assert cross_role_resp.status_code == 403

    # 7. Unauthenticated request to protected endpoint is unauthorized (401)
    unauth_resp = client.get("/notifications")
    assert unauth_resp.status_code == 401
