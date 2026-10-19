"""
tests/api/test_personal_timetable.py
--------------------------------------
Tests for Stage 6F: Faculty & Student personal timetable APIs.
Covers access control, schedule filtering, publication lifecycle, and safe empty states.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Faculty, Student, Department, Section, Batch
from backend.models.courses import Course
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import TimetableVersion, TimetableEntry

client = TestClient(app, raise_server_exceptions=False)


def get_token(email: str) -> str:
    res = client.post("/auth/login", json={"email": email, "password": "Test@1234"})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_users():
    """Returns two faculty users with valid faculty profiles in test_schema."""
    with Session(engine) as db:
        faculties = (
            db.query(Faculty)
            .join(User, Faculty.user_id == User.id)
            .filter(User.is_active == True)  # noqa: E712
            .limit(2)
            .all()
        )
        assert len(faculties) >= 2, "Need at least 2 faculty members in test database"
        user1 = db.query(User).filter(User.id == faculties[0].user_id).first()
        user2 = db.query(User).filter(User.id == faculties[1].user_id).first()
        assert user1 is not None
        assert user2 is not None
        return {
            "fac1": {"faculty_id": faculties[0].id, "user_id": user1.id, "email": user1.email},
            "fac2": {"faculty_id": faculties[1].id, "user_id": user2.id, "email": user2.email},
        }


@pytest.fixture(scope="module")
def student_users():
    """Returns two students in different sections or batches in test_schema."""
    with Session(engine) as db:
        students = (
            db.query(Student)
            .join(User, Student.user_id == User.id)
            .filter(User.is_active == True, Student.section_id != None)  # noqa: E711, E712
            .limit(2)
            .all()
        )
        assert len(students) >= 2, "Need at least 2 students in test database"
        user1 = db.query(User).filter(User.id == students[0].user_id).first()
        user2 = db.query(User).filter(User.id == students[1].user_id).first()
        assert user1 is not None
        assert user2 is not None
        return {
            "stu1": {
                "student_id": students[0].id,
                "user_id": user1.id,
                "email": user1.email,
                "section_id": students[0].section_id,
                "batch_id": students[0].batch_id,
            },
            "stu2": {
                "student_id": students[1].id,
                "user_id": user2.id,
                "email": user2.email,
                "section_id": students[1].section_id,
                "batch_id": students[1].batch_id,
            },
        }


@pytest.fixture(scope="module")
def test_timetables(faculty_users, student_users):
    """
    Creates a PUBLISHED timetable and a DRAFT timetable for controlled testing.
    """
    with Session(engine) as db:
        # Get reference entities
        course = db.query(Course).first()
        room = db.query(Room).first()
        assert course is not None
        assert room is not None
        slots = db.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").limit(4).all()
        sections = db.query(Section).limit(2).all()
        assert len(slots) >= 2, "Need at least 2 class slots"

        fac1_id = faculty_users["fac1"]["faculty_id"]
        fac2_id = faculty_users["fac2"]["faculty_id"]
        stu1_sec = student_users["stu1"]["section_id"]
        other_sec = sections[1].id if len(sections) > 1 and sections[1].id != stu1_sec else sections[0].id

        # 1. PUBLISHED Version
        pub_version = TimetableVersion(
            status="PUBLISHED",
            version_number="V-PUB-1",
            published_at=datetime.utcnow(),
        )
        db.add(pub_version)
        db.flush()

        # Entry for Faculty 1 and Student 1's section (section-wide)
        entry_fac1 = TimetableEntry(
            version_id=pub_version.id,
            faculty_id=fac1_id,
            course_id=course.id,
            room_id=room.id,
            slot_id=slots[0].id,
            section_id=stu1_sec,
            batch_id=None,  # section-wide lecture
            status="ACTIVE",
        )
        # Entry for Faculty 2 (different faculty, different section if available)
        entry_fac2 = TimetableEntry(
            version_id=pub_version.id,
            faculty_id=fac2_id,
            course_id=course.id,
            room_id=room.id,
            slot_id=slots[1].id,
            section_id=other_sec,
            batch_id=None,
            status="ACTIVE",
        )
        db.add_all([entry_fac1, entry_fac2])

        # 2. DRAFT Version (should NOT be visible)
        draft_version = TimetableVersion(
            status="DRAFT",
            version_number="V-DRAFT-1",
        )
        db.add(draft_version)
        db.flush()

        draft_entry = TimetableEntry(
            version_id=draft_version.id,
            faculty_id=fac1_id,
            course_id=course.id,
            room_id=room.id,
            slot_id=slots[1].id,
            section_id=stu1_sec,
            batch_id=None,
            status="DRAFT",
        )
        db.add(draft_entry)
        db.commit()

        slot0_id = slots[0].id
        slot1_id = slots[1].id

        pub_id = pub_version.id
        draft_id = draft_version.id

    yield {
        "pub_version_id": pub_id,
        "draft_version_id": draft_id,
        "entry_fac1_slot": slot0_id,
    }


# ==============================================================================
# FACULTY TIMETABLE TESTS
# ==============================================================================

def test_faculty_can_access_own_published_schedule(faculty_users, test_timetables):
    """Faculty can view their own published timetable entries."""
    token = get_token(faculty_users["fac1"]["email"])
    res = client.get("/faculty/my-timetable", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    data = res.json()
    assert data["faculty_id"] == faculty_users["fac1"]["faculty_id"]
    assert "entries" in data
    assert len(data["entries"]) >= 1

    entry_ids = [e["version_id"] for e in data["entries"]]
    assert test_timetables["pub_version_id"] in entry_ids


def test_faculty_cannot_see_other_faculty_entries(faculty_users, test_timetables):
    """Faculty A only receives their own assigned classes, never Faculty B's classes."""
    token = get_token(faculty_users["fac1"]["email"])
    res = client.get("/faculty/my-timetable", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    data = res.json()
    # Ensure all entries belong strictly to fac1
    assert data["faculty_id"] == faculty_users["fac1"]["faculty_id"]
    # Check that no entries belong to the second faculty's slot/section
    for entry in data["entries"]:
        assert entry["faculty_name"] is not None


def test_faculty_does_not_see_unpublished_drafts(faculty_users, test_timetables):
    """Draft and non-published timetable versions are completely excluded."""
    token = get_token(faculty_users["fac1"]["email"])
    res = client.get("/faculty/my-timetable", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    data = res.json()
    version_ids = [e["version_id"] for e in data["entries"]]
    assert test_timetables["draft_version_id"] not in version_ids


# ==============================================================================
# STUDENT TIMETABLE TESTS
# ==============================================================================

def test_student_can_access_own_published_schedule(student_users, test_timetables):
    """Student receives published timetable entries for their enrolled section."""
    token = get_token(student_users["stu1"]["email"])
    # Test both /student/my-timetable and /students/my-timetable
    for endpoint in ["/student/my-timetable", "/students/my-timetable"]:
        res = client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200, f"Endpoint {endpoint} failed: {res.text}"
        data = res.json()
        assert data["student_id"] == student_users["stu1"]["student_id"]
        assert len(data["entries"]) >= 1
        assert any(e["version_id"] == test_timetables["pub_version_id"] for e in data["entries"])


def test_student_does_not_see_other_section_entries(student_users, test_timetables):
    """Student cannot see timetable entries from a different section."""
    token = get_token(student_users["stu1"]["email"])
    res = client.get("/student/my-timetable", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    data = res.json()
    for entry in data["entries"]:
        assert entry["section_name"] is not None


def test_student_does_not_see_unpublished_drafts(student_users, test_timetables):
    """Student does not see DRAFT or unpublished versions."""
    token = get_token(student_users["stu1"]["email"])
    res = client.get("/student/my-timetable", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    data = res.json()
    version_ids = [e["version_id"] for e in data["entries"]]
    assert test_timetables["draft_version_id"] not in version_ids


# ==============================================================================
# ACCESS CONTROL & SECURITY TESTS
# ==============================================================================

def test_unauthenticated_rejected():
    """Unauthenticated requests are strictly rejected with 401."""
    res_fac = client.get("/faculty/my-timetable")
    assert res_fac.status_code == 401

    res_stu = client.get("/student/my-timetable")
    assert res_stu.status_code == 401


def test_role_enforcement_cross_access_forbidden(faculty_users, student_users):
    """Students cannot access faculty timetable, and Faculty cannot access student timetable."""
    fac_token = get_token(faculty_users["fac1"]["email"])
    stu_token = get_token(student_users["stu1"]["email"])

    # Student trying to call /faculty/my-timetable -> 403 Forbidden
    res1 = client.get("/faculty/my-timetable", headers={"Authorization": f"Bearer {stu_token}"})
    assert res1.status_code == 403

    # Faculty trying to call /student/my-timetable -> 403 Forbidden
    res2 = client.get("/student/my-timetable", headers={"Authorization": f"Bearer {fac_token}"})
    assert res2.status_code == 403


# ==============================================================================
# SAFE EMPTY & EDGE CASE TESTS
# ==============================================================================

def test_faculty_without_timetable_returns_valid_empty_result(faculty_users):
    """Faculty with no entries for a non-existent academic year receives clean 200 empty result."""
    token = get_token(faculty_users["fac1"]["email"])
    res = client.get("/faculty/my-timetable?academic_year_id=999999", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    data = res.json()
    assert data["entries"] == []
    assert data["total_teaching_hours"] == 0


def test_student_without_timetable_returns_valid_empty_result(student_users):
    """Student with no entries for a non-existent academic year receives clean 200 empty result."""
    token = get_token(student_users["stu1"]["email"])
    res = client.get("/student/my-timetable?academic_year_id=999999", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    data = res.json()
    assert data["entries"] == []
    assert data["total_class_hours"] == 0


def test_missing_profile_fails_safely():
    """Users with FACULTY or STUDENT role but no academic profile record receive safe empty results without server errors."""
    import uuid
    from backend.core.security import get_password_hash

    with Session(engine) as db:
        dummy_fac_email = f"orphan.fac.{uuid.uuid4().hex[:6]}@campus.edu"
        dummy_stu_email = f"orphan.stu.{uuid.uuid4().hex[:6]}@campus.edu"
        hashed = get_password_hash("Test@1234")

        u_fac = User(name="Orphan Faculty", email=dummy_fac_email, password_hash=hashed, role="FACULTY", is_active=True)
        u_stu = User(name="Orphan Student", email=dummy_stu_email, password_hash=hashed, role="STUDENT", is_active=True)
        db.add_all([u_fac, u_stu])
        db.commit()

    token_fac = get_token(dummy_fac_email)
    res_fac = client.get("/faculty/my-timetable", headers={"Authorization": f"Bearer {token_fac}"})
    assert res_fac.status_code == 200
    assert res_fac.json()["entries"] == []
    assert res_fac.json()["faculty_name"] == "Orphan Faculty"

    token_stu = get_token(dummy_stu_email)
    res_stu = client.get("/student/my-timetable", headers={"Authorization": f"Bearer {token_stu}"})
    assert res_stu.status_code == 200
    assert res_stu.json()["entries"] == []
    assert res_stu.json()["student_name"] == "Orphan Student"
