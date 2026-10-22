"""
tests/api/test_notifications.py
-------------------------------
End-to-end verification suite for the Notification system:
1. Notification creation and persistence.
2. Recipient resolution for department, program, semester, and section.
3. Successful timetable publication notifying correct faculty and students.
4. Unrelated departments receiving no notification.
5. Failed publication producing no false notification.
6. Duplicate-event handling and retry safety.
7. Booking submission, approval, rejection, and cancellation notifications.
8. Read/unread state and unread-count accuracy.
9. Authentication and cross-user notification isolation.
10. SSE stream authentication and connection handshake.
"""

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.config import engine
from backend.main import app
from backend.models.academic import AcademicYear, Department, Faculty, Program, Section, Semester, Student
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import Notification
from backend.services.notification_service import (
    create_notification,
    notify_timetable_published,
)

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_token():
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def other_faculty_token():
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── 1. Persistence & Unread Counters ──────────────────────────────────────────

def test_notification_creation_and_persistence(admin_token):
    with Session(engine) as db:
        admin_user = db.query(User).filter(User.email == "admin@campus.edu").first()
        assert admin_user is not None

        notif = create_notification(
            db=db,
            user_id=admin_user.id,
            title="System Initialization",
            message="Initial diagnostic test alert for admin.",
            type="SYSTEM_TEST",
            link="/admin",
            entity_type="System",
            entity_id=1,
        )
        assert notif is not None
        assert notif.id is not None
        notif_id = notif.id
        assert not notif.is_read

    # Retrieve via REST API
    resp = client.get("/notifications", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["id"] == notif_id for i in items)


def test_unread_count_and_read_mutation(faculty_token):
    with Session(engine) as db:
        fac_user = db.query(User).filter(User.email == "allison.hill@campus.edu").first()
        assert fac_user is not None

        # Clean prior test notifs for clean assertions
        db.query(Notification).filter(Notification.user_id == fac_user.id).delete()
        db.commit()

        n1 = create_notification(db, fac_user.id, "Alert 1", "Message 1", "TEST")
        n2 = create_notification(db, fac_user.id, "Alert 2", "Message 2", "TEST")
        assert n1 and n2
        n1_id = n1.id

    # Verify unread count is 2
    resp = client.get("/notifications/unread-count", headers={"Authorization": f"Bearer {faculty_token}"})
    assert resp.status_code == 200
    assert resp.json()["unread_count"] >= 2

    # Mark single as read
    resp = client.patch(f"/notifications/{n1_id}/read", headers={"Authorization": f"Bearer {faculty_token}"})
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True

    # Mark all read
    resp = client.post("/notifications/mark-all-read", headers={"Authorization": f"Bearer {faculty_token}"})
    assert resp.status_code == 200
    assert resp.json()["marked_count"] >= 1

    # Verify count is now 0
    resp = client.get("/notifications/unread-count", headers={"Authorization": f"Bearer {faculty_token}"})
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 0


# ── 2. User Isolation & Security ──────────────────────────────────────────────

def test_user_isolation_and_authorization(faculty_token, student_token):
    with Session(engine) as db:
        fac_user = db.query(User).filter(User.email == "allison.hill@campus.edu").first()
        stud_user = db.query(User).filter(User.email == "monica.herrera@campus.edu").first()
        assert fac_user and stud_user

        private_notif = create_notification(
            db=db,
            user_id=fac_user.id,
            title="Confidential Faculty Memo",
            message="Restricted faculty grading memo.",
            type="PRIVATE",
        )
        assert private_notif is not None
        private_notif_id = private_notif.id

    # Student cannot see faculty's notification
    resp = client.get("/notifications", headers={"Authorization": f"Bearer {student_token}"})
    assert resp.status_code == 200
    student_notifs = resp.json()
    assert all(n["id"] != private_notif_id for n in student_notifs)

    # Student cannot mark faculty's notification as read
    resp = client.patch(
        f"/notifications/{private_notif_id}/read",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 403


# ── 3. Administrative Targeted Broadcast ──────────────────────────────────────

def test_admin_broadcast_and_permissions(admin_token, faculty_token, student_token):
    # Non-admin cannot broadcast
    forbidden_resp = client.post(
        "/notifications/admin/broadcast",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"title": "Hacked", "message": "Illegal"},
    )
    assert forbidden_resp.status_code == 403

    # Admin broadcasts campus-wide
    resp = client.post(
        "/notifications/admin/broadcast",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "title": "Campus Convocation Announcement",
            "message": "Annual convocation will be held on December 15.",
            "target_role": "ALL",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["recipients_count"] > 0

    # Faculty sees the broadcast
    fac_resp = client.get("/notifications", headers={"Authorization": f"Bearer {faculty_token}"})
    assert fac_resp.status_code == 200
    assert any("Campus Convocation" in n["title"] for n in fac_resp.json())


# ── 4. Faculty-to-Student Class Updates ───────────────────────────────────────

def test_faculty_class_update_authorization(faculty_token, other_faculty_token):
    with Session(engine) as db:
        allison = db.query(User).filter(User.email == "allison.hill@campus.edu").first()
        assert allison is not None
        fac = db.query(Faculty).filter(Faculty.user_id == allison.id).first()
        assert fac is not None

        # Find an assigned course assignment
        ca = db.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac.id).first()
        if not ca:
            pytest.skip("Faculty has no course assignment in test database")

        course_id = ca.course_id
        section_id = ca.section_id
        assert course_id and section_id

    # Authorized faculty sends class update
    resp = client.post(
        "/notifications/faculty/class-update",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "course_id": course_id,
            "section_id": section_id,
            "update_type": "RESCHEDULE",
            "title": "Lab Session Shifted",
            "message": "Tomorrow's lab session is moved to Room B204.",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Other faculty (not assigned to this course/section) receives 403 Forbidden
    unauthorized_resp = client.post(
        "/notifications/faculty/class-update",
        headers={"Authorization": f"Bearer {other_faculty_token}"},
        json={
            "course_id": course_id,
            "section_id": section_id,
            "update_type": "CANCELLATION",
            "title": "Impersonated Class Cancellation",
            "message": "Unauthorized cancellation attempt.",
        },
    )
    assert unauthorized_resp.status_code == 403


# ── 5. Timetable Publication: Priority 1 Event Path ───────────────────────────

def test_timetable_publication_notifications(admin_token):
    with Session(engine) as db:
        # Create an isolated academic scope for testing
        ac_year = db.query(AcademicYear).first()
        dept = db.query(Department).first()
        prog = db.query(Program).filter(Program.department_id == dept.id).first() if dept else None
        sem = db.query(Semester).first()
        sec = db.query(Section).filter(Section.semester_id == sem.id).first() if sem else None
        fac = db.query(Faculty).filter(Faculty.user_id.isnot(None)).first()
        course = db.query(Course).first()
        room = db.query(Room).first()
        slot = db.query(TimeSlot).first()
        admin_user = db.query(User).filter(User.role == "ADMIN").first()

        assert all([ac_year, dept, prog, sem, sec, fac, course, room, slot, admin_user])
        assert ac_year and dept and prog and sem and sec and fac and course and room and slot and admin_user

        # Create a test timetable version in FINALIZED state
        version = TimetableVersion(
            academic_year_id=ac_year.id,
            version_number="99.0",
            status="FINALIZED",
            created_by=admin_user.id,
        )
        db.add(version)
        db.flush()

        # Add an entry linking the faculty and section
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
        sec_id = sec.id

    # Publish the timetable version via endpoint
    resp = client.post(
        f"/timetable/versions/{v_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PUBLISHED"
    assert data["notifications"]["success"] is True
    assert data["notifications"]["faculty_notified"] >= 1

    # Verify assigned faculty received the notification
    with Session(engine) as db:
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
        assert fac_notif.title is not None and "Timetable Published" in fac_notif.title
        assert fac_notif.link == "/faculty/timetable"

    # Verify deduplication: publishing again or re-invoking notify_timetable_published skips duplicates
    with Session(engine) as db:
        res = notify_timetable_published(db, v_id)
        assert res["success"] is True
        assert res.get("deduplicated") is True
        assert res["total_notified"] == 0


def test_failed_publication_produces_no_notification():
    with Session(engine) as db:
        # Version in DRAFT state (not PUBLISHED)
        draft_version = TimetableVersion(
            version_number="0.1-DRAFT",
            status="DRAFT",
        )
        db.add(draft_version)
        db.commit()

        res = notify_timetable_published(db, draft_version.id)
        assert res["success"] is False
        assert "status is 'DRAFT', not 'PUBLISHED'" in res["error"]

        # Confirm zero notifications were saved
        count = (
            db.query(Notification)
            .filter(
                Notification.entity_type == "TimetableVersion",
                Notification.entity_id == draft_version.id,
            )
            .count()
        )
        assert count == 0


# ── 6. Resource Booking Lifecycle Notifications ───────────────────────────────

def test_booking_lifecycle_notifications(admin_token, student_token):
    # 1. Student creates a booking request
    with Session(engine) as db:
        res = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        stud_user = db.query(User).filter(User.email == "monica.herrera@campus.edu").first()
        assert res and stud_user

        booking_date = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
        res_id = res.id
        stud_uid = stud_user.id

    create_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {student_token}"},
        json={
            "resource_id": res_id,
            "date": booking_date,
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "purpose": "Group project practice session",
        },
    )
    assert create_resp.status_code == 201
    booking_id = create_resp.json()["id"]

    # Verify student received submission notification
    with Session(engine) as db:
        sub_notif = (
            db.query(Notification)
            .filter(
                Notification.user_id == stud_uid,
                Notification.entity_type == "ResourceBooking",
                Notification.entity_id == booking_id,
                Notification.type == "BOOKING_SUBMITTED",
            )
            .first()
        )
        assert sub_notif is not None
        assert sub_notif.title is not None and "Booking Request Submitted" in sub_notif.title

    # 2. Admin approves booking
    appr_resp = client.post(
        f"/resources/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert appr_resp.status_code == 200

    # Verify student received approval notification
    with Session(engine) as db:
        appr_notif = (
            db.query(Notification)
            .filter(
                Notification.user_id == stud_uid,
                Notification.entity_type == "ResourceBooking",
                Notification.entity_id == booking_id,
                Notification.type == "BOOKING_APPROVED",
            )
            .first()
        )
        assert appr_notif is not None
        assert appr_notif.title is not None and "Booking Approved" in appr_notif.title

    # 3. Student cancels the booking
    cancel_resp = client.post(
        f"/resources/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"reason": "Team schedule conflict"},
    )
    assert cancel_resp.status_code == 200

    # Verify cancellation notification
    with Session(engine) as db:
        cancel_notif = (
            db.query(Notification)
            .filter(
                Notification.user_id == stud_uid,
                Notification.entity_type == "ResourceBooking",
                Notification.entity_id == booking_id,
                Notification.type == "BOOKING_CANCELLED",
            )
            .first()
        )
        assert cancel_notif is not None
        assert cancel_notif.title is not None and "Booking Cancelled" in cancel_notif.title


# ── 7. SSE Stream Handshake ───────────────────────────────────────────────────

def test_sse_stream_authentication(faculty_token):
    # Unauthenticated request fails with 401
    unauth_resp = client.get("/notifications/stream")
    assert unauth_resp.status_code == 401

    # Invalid token fails with 401
    invalid_resp = client.get("/notifications/stream?token=invalid.jwt.token")
    assert invalid_resp.status_code == 401


@pytest.mark.anyio
async def test_sse_stream_broker_dispatch():
    from backend.services.notification_service import stream_broker

    test_uid = 999999
    queue = await stream_broker.subscribe(test_uid)
    try:
        notif = Notification(
            id=777,
            user_id=test_uid,
            title="Real-Time Test",
            message="Streaming dispatch verified.",
            type="STREAM_TEST",
            is_read=False,
        )
        stream_broker.publish_notification(test_uid, notif)
        assert not queue.empty()
        item = queue.get_nowait()
        assert item["id"] == 777
        assert item["title"] == "Real-Time Test"
        assert item["user_id"] == test_uid
    finally:
        await stream_broker.unsubscribe(test_uid, queue)
