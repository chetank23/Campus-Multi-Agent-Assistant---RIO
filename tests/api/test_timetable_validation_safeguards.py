"""
tests/api/test_timetable_validation_safeguards.py
-------------------------------------------------
Comprehensive test suite verifying centralized timetable validation,
rule code enforcement, conflict detection, and server-side publication safeguards.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Faculty
from backend.models.courses import Course
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.workflow import Notification

client = TestClient(app)


@pytest.fixture(scope="module")
def admin_token():
    res = client.post(
        "/auth/login",
        json={"email": "admin@campus.edu", "password": "Test@1234"},
    )
    assert res.status_code == 200, "Admin login failed"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    res = client.post(
        "/auth/login",
        json={"email": "monica.herrera@campus.edu", "password": "Test@1234"},
    )
    assert res.status_code == 200, "Student login failed"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def base_entities():
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        dept = db.query(Department).first()
        prog = db.query(Program).first()
        sem = db.query(Semester).first()
        sec = db.query(Section).first()
        facs = db.query(Faculty).limit(3).all()
        courses = db.query(Course).limit(3).all()
        rooms = db.query(Room).filter(Room.status == "ACTIVE").limit(3).all()
        slots = db.query(TimeSlot).limit(3).all()
        admin = db.query(User).filter(User.role == "ADMIN").first()

        assert all([ac_year, dept, prog, sem, sec, facs, courses, rooms, slots, admin])
        return {
            "academic_year_id": ac_year.id,
            "department_id": dept.id,
            "program_id": prog.id,
            "semester_id": sem.id,
            "section_id": sec.id,
            "faculty_ids": [f.id for f in facs],
            "course_ids": [c.id for c in courses],
            "room_ids": [r.id for r in rooms],
            "slot_ids": [s.id for s in slots],
            "admin_id": admin.id,
        }


def test_empty_timetable_is_rejected_as_blocker(admin_token, base_entities):
    """Empty timetable versions cannot be marked as VALIDATED or FINALIZED."""
    with Session(engine) as db:
        empty_version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v90.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(empty_version)
        db.commit()
        vid = empty_version.id

    res = client.post(
        f"/timetable/versions/{vid}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    val_data = res.json()
    assert val_data["is_valid"] is False
    assert val_data["blocker_count"] >= 1
    codes = [v["code"] for v in val_data["violations"]]
    assert "EMPTY_TIMETABLE" in codes

    # DB status must remain GENERATED / not upgraded to VALIDATED
    with Session(engine) as db:
        v_check = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert v_check.status != "VALIDATED"


def test_faculty_scheduling_conflict_detected(admin_token, base_entities):
    """A faculty member scheduled for two classes in the same slot is a BLOCKER."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v91.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        shared_fac = base_entities["faculty_ids"][0]
        shared_slot = base_entities["slot_ids"][0]

        # Entry 1: faculty in room 0, course 0
        e1 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][0],
            faculty_id=shared_fac,
            room_id=base_entities["room_ids"][0],
            slot_id=shared_slot,
            status="ACTIVE",
        )
        # Entry 2: same faculty in room 1, course 1 at the same slot
        e2 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][1],
            faculty_id=shared_fac,
            room_id=base_entities["room_ids"][1],
            slot_id=shared_slot,
            status="ACTIVE",
        )
        db.add_all([e1, e2])
        db.commit()
        vid = version.id
        e1_id = e1.id
        e2_id = e2.id

    res = client.post(
        f"/timetable/versions/{vid}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    val_data = res.json()
    assert val_data["is_valid"] is False
    assert val_data["blocker_count"] >= 1

    fac_overlaps = [v for v in val_data["violations"] if v.get("code") == "FACULTY_OVERLAP"]
    assert len(fac_overlaps) >= 1
    overlap = fac_overlaps[0]
    assert overlap["severity"] == "BLOCKER"
    assert e1_id in overlap["entry_ids"]
    assert e2_id in overlap["entry_ids"]
    assert overlap.get("suggestion") is not None


def test_room_collision_detected(admin_token, base_entities):
    """Two different faculty scheduled in the same room in the same slot is a BLOCKER."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v92.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        shared_room = base_entities["room_ids"][0]
        shared_slot = base_entities["slot_ids"][1]

        e1 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][0],
            faculty_id=base_entities["faculty_ids"][0],
            room_id=shared_room,
            slot_id=shared_slot,
            status="ACTIVE",
        )
        e2 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][1],
            faculty_id=base_entities["faculty_ids"][1],
            room_id=shared_room,
            slot_id=shared_slot,
            status="ACTIVE",
        )
        db.add_all([e1, e2])
        db.commit()
        vid = version.id

    res = client.post(
        f"/timetable/versions/{vid}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    val_data = res.json()
    assert val_data["is_valid"] is False
    codes = [v["code"] for v in val_data["violations"]]
    assert "ROOM_OVERLAP" in codes


def test_inactive_room_rejected(admin_token, base_entities):
    """Scheduling an entry in an INACTIVE room is detected as a BLOCKER."""
    with Session(engine) as db:
        inactive_room = Room(
            building_id=1,
            room_number="MNT-101",
            room_type="CLASSROOM",
            capacity=40,
            status="MAINTENANCE",
        )
        db.add(inactive_room)
        db.flush()

        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v93.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        entry = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][0],
            faculty_id=base_entities["faculty_ids"][0],
            room_id=inactive_room.id,
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()
        vid = version.id

    res = client.post(
        f"/timetable/versions/{vid}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    val_data = res.json()
    assert val_data["is_valid"] is False
    codes = [v["code"] for v in val_data["violations"]]
    assert "ROOM_INACTIVE" in codes


def test_publication_blocked_when_conflicts_exist(admin_token, base_entities):
    """Server-side publication safeguard rejects invalid/conflict-ridden timetable with HTTP 409."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v94.0",
            status="FINALIZED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        shared_fac = base_entities["faculty_ids"][0]
        shared_slot = base_entities["slot_ids"][2]

        e1 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][0],
            faculty_id=shared_fac,
            room_id=base_entities["room_ids"][0],
            slot_id=shared_slot,
            status="ACTIVE",
        )
        e2 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][1],
            faculty_id=shared_fac,
            room_id=base_entities["room_ids"][1],
            slot_id=shared_slot,
            status="ACTIVE",
        )
        db.add_all([e1, e2])
        db.commit()
        vid = version.id

    # Attempt to publish the conflicting timetable
    pub_res = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_res.status_code == 409, f"Expected 409 Conflict, got {pub_res.status_code}: {pub_res.text}"
    assert "Publication rejected" in pub_res.json()["detail"]

    # Verify that the database record is NOT marked as published
    with Session(engine) as db:
        v_check = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert v_check.status != "PUBLISHED"
        assert v_check.published_at is None


def test_unauthorized_publication_rejected(student_token, base_entities):
    """Only admins can publish timetables; students receive 403 Forbidden."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v95.0",
            status="FINALIZED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.commit()
        vid = version.id

    res = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 403


def test_valid_timetable_lifecycle_and_publication(admin_token, base_entities):
    """A clean, valid timetable passes validation, can be finalized, and publishes safely with notifications."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v96.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        # Non-overlapping entries across distinct slots
        e1 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][0],
            faculty_id=base_entities["faculty_ids"][0],
            room_id=base_entities["room_ids"][0],
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        e2 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][1],
            faculty_id=base_entities["faculty_ids"][1],
            room_id=base_entities["room_ids"][1],
            slot_id=base_entities["slot_ids"][1],
            status="ACTIVE",
        )
        db.add_all([e1, e2])
        db.commit()
        vid = version.id

    # 1. Validation passes
    val_res = client.post(
        f"/timetable/versions/{vid}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is True
    assert val_data["blocker_count"] == 0

    # Persisted status upgraded to VALIDATED
    with Session(engine) as db:
        v_check = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert v_check.status == "VALIDATED"

    # 2. Finalize version
    fin_res = client.post(
        f"/timetable/versions/{vid}/finalize",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert fin_res.status_code == 200
    assert fin_res.json()["status"] == "FINALIZED"

    # 3. Publish version
    pub_res = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["status"] == "PUBLISHED"
    assert "notifications" in pub_data

    # Persisted status is PUBLISHED
    with Session(engine) as db:
        v_pub = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert v_pub.status == "PUBLISHED"
        assert v_pub.published_at is not None

        # Verify publication notifications were generated
        notifs = db.query(Notification).filter(
            Notification.entity_type == "TimetableVersion",
            Notification.entity_id == vid,
        ).all()
        assert len(notifs) >= 1

    # 4. Idempotency safeguard: re-publishing returns 409
    repub_res = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert repub_res.status_code == 409
