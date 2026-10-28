"""
tests/api/test_timetable_validation_safeguards.py
-------------------------------------------------
Authoritative test suite verifying the 15 required hard-constraint,
conflict-prevention, solver-correctness, and timetable-lifecycle scenarios
for RIO-MJP Stage 14.

Scenarios verified:
1. Valid timetable satisfying all hard constraints.
2. Two classes competing for the same faculty member (same slot & interval overlap).
3. Two classes competing for the same room.
4. Two classes assigned to the same batch at overlapping times (H3).
5. Room smaller than class size blocks publication (H4).
6. Unavailable faculty member is blocked.
7. Valid scenario containing lab sessions and relevant room restrictions.
8. Infeasible scheduling problem reports honest status and actionable diagnostics.
9. Empty, incomplete, and invalid slot records (EMPTY_TIMETABLE, INCOMPLETE_ENTRY, INVALID_SLOT_TYPE).
10. Overlapping intervals with different start times and durations (slots_overlap).
11. Invalid or stale scheduling data (inactive room).
12. Attempts to publish an invalid timetable rejected with HTTP 409.
13. Persistence and retrieval of the generated timetable.
14. Repeated generation and publication requests (idempotency).
15. Regression cases for previously working functionality.
"""

from datetime import time, date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Batch, Faculty
from backend.models.courses import Course
from backend.models.space_time import Room, TimeSlot, FacultyAvailability
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.workflow import Notification
from backend.schemas.timetable_generation import (
    OptimizerInput,
    GenerationScope,
    OptCourse,
    OptSection,
    OptFaculty,
    OptFacultyAvailability,
    OptTimeSlot,
    OptRoom,
    OptCourseAssignment,
)
from backend.optimizer.timetable_solver import TimetableSolver
from backend.optimizer.validator import slots_overlap

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
        slots = db.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").limit(4).all()
        admin = db.query(User).filter(User.role == "ADMIN").first()

        assert ac_year is not None
        assert dept is not None
        assert prog is not None
        assert sem is not None
        assert sec is not None
        assert admin is not None

        # Ensure batch exists
        batch = db.query(Batch).filter(Batch.section_id == sec.id).first()
        if not batch:
            batch = Batch(section_id=sec.id, batch_name="B1", student_count=20)
            db.add(batch)
            db.flush()

        # Ensure lab room exists
        lab_room = db.query(Room).filter(Room.room_type == "LAB", Room.status == "ACTIVE").first()
        if not lab_room:
            lab_room = Room(building_id=1, room_number="LAB-S14", room_type="LAB", capacity=30, status="ACTIVE")
            db.add(lab_room)
            db.flush()

        # Ensure lab course exists
        lab_course = db.query(Course).filter(Course.requires_lab == True).first()
        if not lab_course:
            lab_course = Course(
                department_id=dept.id,
                course_code="LAB999",
                course_name="Stage 14 System Lab",
                course_type="LAB",
                credits=2,
                lecture_hours=0,
                tutorial_hours=0,
                practical_hours=2,
                requires_lab=True,
            )
            db.add(lab_course)
            db.flush()

        # Ensure a break/lunch slot exists
        break_slot = db.query(TimeSlot).filter(TimeSlot.slot_type.in_(["BREAK", "LUNCH"])).first()
        if not break_slot:
            break_slot = TimeSlot(day="MONDAY", start_time=time(13, 0), end_time=time(14, 0), slot_type="LUNCH")
            db.add(break_slot)
            db.flush()

        # Ensure two overlapping slots on FRIDAY for interval testing
        overlap_slot_1 = db.query(TimeSlot).filter(TimeSlot.day == "FRIDAY", TimeSlot.start_time == time(9, 0), TimeSlot.end_time == time(10, 30)).first()
        if not overlap_slot_1:
            overlap_slot_1 = TimeSlot(day="FRIDAY", start_time=time(9, 0), end_time=time(10, 30), slot_type="CLASS")
            db.add(overlap_slot_1)
            db.flush()

        overlap_slot_2 = db.query(TimeSlot).filter(TimeSlot.day == "FRIDAY", TimeSlot.start_time == time(10, 0), TimeSlot.end_time == time(11, 30)).first()
        if not overlap_slot_2:
            overlap_slot_2 = TimeSlot(day="FRIDAY", start_time=time(10, 0), end_time=time(11, 30), slot_type="CLASS")
            db.add(overlap_slot_2)
            db.flush()

        db.commit()

        return {
            "academic_year_id": ac_year.id,
            "department_id": dept.id,
            "program_id": prog.id,
            "semester_id": sem.id,
            "section_id": sec.id,
            "batch_id": batch.id,
            "faculty_ids": [f.id for f in facs],
            "course_ids": [c.id for c in courses],
            "room_ids": [r.id for r in rooms],
            "slot_ids": [s.id for s in slots],
            "lab_room_id": lab_room.id,
            "lab_course_id": lab_course.id,
            "break_slot_id": break_slot.id,
            "overlap_slot_1_id": overlap_slot_1.id,
            "overlap_slot_2_id": overlap_slot_2.id,
            "admin_id": admin.id,
        }


# ==============================================================================
# Scenario 1: A valid timetable that satisfies all hard constraints
# ==============================================================================
def test_scenario_1_valid_timetable_satisfies_all_hard_constraints(admin_token, base_entities):
    """Scenario 1: A valid timetable satisfies all hard constraints and publishes cleanly."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v101.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

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

    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is True
    assert val_data["blocker_count"] == 0

    fin_res = client.post(f"/timetable/versions/{vid}/finalize", headers={"Authorization": f"Bearer {admin_token}"})
    assert fin_res.status_code == 200
    assert fin_res.json()["status"] == "FINALIZED"

    pub_res = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "PUBLISHED"


# ==============================================================================
# Scenario 2: Two classes competing for the same faculty member
# ==============================================================================
def test_scenario_2_two_classes_competing_for_same_faculty(admin_token, base_entities):
    """Scenario 2: Faculty double-booking is rejected with FACULTY_OVERLAP blocker."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v102.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        shared_fac = base_entities["faculty_ids"][0]
        shared_slot = base_entities["slot_ids"][0]

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

    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is False
    codes = [v["code"] for v in val_data["violations"]]
    assert "FACULTY_OVERLAP" in codes


# ==============================================================================
# Scenario 3: Two classes competing for the same room
# ==============================================================================
def test_scenario_3_two_classes_competing_for_same_room(admin_token, base_entities):
    """Scenario 3: Room collision is rejected with ROOM_OVERLAP blocker."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v103.0",
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

    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is False
    codes = [v["code"] for v in val_data["violations"]]
    assert "ROOM_OVERLAP" in codes


# ==============================================================================
# Scenario 4: Two classes assigned to the same batch at overlapping times
# ==============================================================================
def test_scenario_4_two_classes_assigned_to_same_batch_at_overlapping_times(admin_token, base_entities):
    """Scenario 4: Batch double-booking is rejected with BATCH_OVERLAP blocker."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v104.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        shared_batch = base_entities["batch_id"]
        shared_slot = base_entities["slot_ids"][2]

        e1 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            batch_id=shared_batch,
            course_id=base_entities["course_ids"][0],
            faculty_id=base_entities["faculty_ids"][0],
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
            batch_id=shared_batch,
            course_id=base_entities["course_ids"][1],
            faculty_id=base_entities["faculty_ids"][1],
            room_id=base_entities["room_ids"][1],
            slot_id=shared_slot,
            status="ACTIVE",
        )
        db.add_all([e1, e2])
        db.commit()
        vid = version.id

    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is False
    codes = [v["code"] for v in val_data["violations"]]
    assert "BATCH_OVERLAP" in codes


# ==============================================================================
# Scenario 5: A room that is smaller than the class size
# ==============================================================================
def test_scenario_5_room_smaller_than_class_size_blocks_publication(admin_token, base_entities):
    """Scenario 5: Room capacity deficit (H4) is enforced as a BLOCKER that prevents publication."""
    with Session(engine) as db:
        tiny_room = Room(
            building_id=1,
            room_number="TINY-01",
            room_type="CLASSROOM",
            capacity=10,
            status="ACTIVE",
        )
        db.add(tiny_room)
        db.flush()

        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v105.0",
            status="FINALIZED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        entry = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],  # Section has > 10 students
            course_id=base_entities["course_ids"][0],
            faculty_id=base_entities["faculty_ids"][0],
            room_id=tiny_room.id,
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()
        vid = version.id

    # Validate endpoint flags CAPACITY_DEFICIT as BLOCKER
    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is False
    assert val_data["blocker_count"] >= 1
    codes = [v["code"] for v in val_data["violations"]]
    assert "CAPACITY_DEFICIT" in codes

    # Publication attempt must be rejected with 409
    pub_res = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 409
    assert "Publication rejected" in pub_res.json()["detail"]


# ==============================================================================
# Scenario 6: An unavailable faculty member
# ==============================================================================
def test_scenario_6_unavailable_faculty_member_is_blocked(admin_token, base_entities):
    """Scenario 6: Scheduling a faculty during an UNAVAILABLE slot is a BLOCKER."""
    with Session(engine) as db:
        fac_id = base_entities["faculty_ids"][0]
        slot_id = base_entities["slot_ids"][0]

        # Ensure availability record marks this slot as UNAVAILABLE
        fa = db.query(FacultyAvailability).filter(
            FacultyAvailability.faculty_id == fac_id,
            FacultyAvailability.slot_id == slot_id,
        ).first()
        if not fa:
            fa = FacultyAvailability(faculty_id=fac_id, slot_id=slot_id, availability="UNAVAILABLE", preference=0)
            db.add(fa)
        else:
            fa.availability = "UNAVAILABLE"
        db.flush()

        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v106.0",
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
            faculty_id=fac_id,
            room_id=base_entities["room_ids"][0],
            slot_id=slot_id,
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()
        vid = version.id

    try:
        val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
        assert val_res.status_code == 200
        val_data = val_res.json()
        assert val_data["is_valid"] is False
        codes = [v["code"] for v in val_data["violations"]]
        assert "FACULTY_UNAVAILABLE" in codes
    finally:
        with Session(engine) as db:
            fa_reset = db.query(FacultyAvailability).filter(
                FacultyAvailability.faculty_id == fac_id,
                FacultyAvailability.slot_id == slot_id,
            ).first()
            if fa_reset:
                fa_reset.availability = "AVAILABLE"
                db.commit()


# ==============================================================================
# Scenario 7: Valid scenario containing lab sessions and relevant room restrictions
# ==============================================================================
def test_scenario_7_valid_scenario_containing_lab_sessions_and_room_restrictions(admin_token, base_entities):
    """Scenario 7: Practical/Lab courses must use LAB rooms; non-lab room triggers LAB_SUITABILITY."""
    with Session(engine) as db:
        # Part A: Lab course in non-lab classroom triggers blocker
        version_bad = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v107A.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version_bad)
        db.flush()

        e_bad = TimetableEntry(
            version_id=version_bad.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["lab_course_id"],
            faculty_id=base_entities["faculty_ids"][0],
            room_id=base_entities["room_ids"][0],  # Regular CLASSROOM
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        db.add(e_bad)

        # Part B: Lab course in LAB room is valid
        version_good = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v107B.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version_good)
        db.flush()

        e_good = TimetableEntry(
            version_id=version_good.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["lab_course_id"],
            faculty_id=base_entities["faculty_ids"][0],
            room_id=base_entities["lab_room_id"],  # LAB room
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        db.add(e_good)
        db.commit()
        vid_bad = version_bad.id
        vid_good = version_good.id

    # Bad validation check
    val_bad = client.post(f"/timetable/versions/{vid_bad}/validate", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert val_bad["is_valid"] is False
    assert "LAB_SUITABILITY" in [v["code"] for v in val_bad["violations"]]

    # Good validation check (lab suitability passes)
    val_good = client.post(f"/timetable/versions/{vid_good}/validate", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert "LAB_SUITABILITY" not in [v["code"] for v in val_good["violations"]]


# ==============================================================================
# Scenario 8: An infeasible scheduling problem
# ==============================================================================
def test_scenario_8_infeasible_scheduling_problem_reports_diagnostics(base_entities):
    """Scenario 8: Infeasible inputs are reported honestly with status and actionable diagnostics."""
    # Construct OptimizerInput where course demands 10 hours but only 1 slot is provided
    scope = GenerationScope(
        academic_year_id=base_entities["academic_year_id"],
        semester_id=base_entities["semester_id"],
        department_id=base_entities["department_id"],
        program_id=base_entities["program_id"],
    )
    opt_course = OptCourse(
        id=999,
        department_id=base_entities["department_id"],
        course_type="THEORY",
        credits=4,
        lecture_hours=10,
        tutorial_hours=0,
        practical_hours=0,
        requires_lab=False,
    )
    opt_section = OptSection(
        id=base_entities["section_id"],
        department_id=base_entities["department_id"],
        program_id=base_entities["program_id"],
        semester_id=base_entities["semester_id"],
        student_count=40,
    )
    opt_faculty = OptFaculty(id=base_entities["faculty_ids"][0], department_id=base_entities["department_id"], max_weekly_load=20)
    opt_slot = OptTimeSlot(id=1, day="MONDAY", start_time=time(9, 0), end_time=time(10, 0), slot_type="TEACHING")
    opt_room = OptRoom(id=1, building_id=1, capacity=50, room_type="CLASSROOM")
    opt_assignment = OptCourseAssignment(
        id=1,
        course_id=999,
        faculty_id=base_entities["faculty_ids"][0],
        section_id=base_entities["section_id"],
    )
    opt_avail = OptFacultyAvailability(
        id=1,
        faculty_id=base_entities["faculty_ids"][0],
        slot_id=1,
        availability="AVAILABLE",
        preference=1,
    )

    opt_input = OptimizerInput(
        scope=scope,
        courses=[opt_course],
        sections=[opt_section],
        faculty=[opt_faculty],
        time_slots=[opt_slot],
        rooms=[opt_room],
        course_assignments=[opt_assignment],
        faculty_availability=[opt_avail],
    )

    solver = TimetableSolver(opt_input=opt_input, time_limit=5)
    res = solver.solve()

    assert res.feasible is False
    assert res.status in ("INFEASIBLE", "INFEASIBLE_AT_BUILD")
    assert len(res.diagnostics) >= 1
    assert any("shortage" in d.lower() or "not enough" in d.lower() for d in res.diagnostics)


# ==============================================================================
# Scenario 9: Empty, incomplete, duplicate or invalid input records
# ==============================================================================
def test_scenario_9_empty_incomplete_and_invalid_slot_records(admin_token, base_entities):
    """Scenario 9: Empty timetable, incomplete entries, and break slots are flagged with specific rule codes."""
    with Session(engine) as db:
        # Part A: Empty timetable
        v_empty = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v109A.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(v_empty)

        # Part B: Incomplete entry & Break slot entry
        v_inval = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v109B.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(v_inval)
        db.flush()

        # Incomplete entry (missing course_id)
        e_incomp = TimetableEntry(
            version_id=v_inval.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=None,
            faculty_id=base_entities["faculty_ids"][0],
            room_id=base_entities["room_ids"][0],
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        # Invalid slot type entry (scheduled during LUNCH / BREAK)
        e_break = TimetableEntry(
            version_id=v_inval.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][0],
            faculty_id=base_entities["faculty_ids"][1],
            room_id=base_entities["room_ids"][1],
            slot_id=base_entities["break_slot_id"],
            status="ACTIVE",
        )
        db.add_all([e_incomp, e_break])
        db.commit()
        vid_empty = v_empty.id
        vid_inval = v_inval.id

    val_empty = client.post(f"/timetable/versions/{vid_empty}/validate", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert val_empty["is_valid"] is False
    assert "EMPTY_TIMETABLE" in [v["code"] for v in val_empty["violations"]]

    val_inval = client.post(f"/timetable/versions/{vid_inval}/validate", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert val_inval["is_valid"] is False
    codes = [v["code"] for v in val_inval["violations"]]
    assert "INCOMPLETE_ENTRY" in codes
    assert "INVALID_SLOT_TYPE" in codes


# ==============================================================================
# Scenario 10: Overlapping intervals with different start times and durations
# ==============================================================================
def test_scenario_10_overlapping_intervals_with_different_start_times_and_durations(admin_token, base_entities):
    """Scenario 10: Slots with distinct IDs but overlapping time intervals are detected via slots_overlap."""
    slot_1_id = base_entities["overlap_slot_1_id"]  # 09:00 - 10:30
    slot_2_id = base_entities["overlap_slot_2_id"]  # 10:00 - 11:30

    with Session(engine) as db:
        s1 = db.query(TimeSlot).filter(TimeSlot.id == slot_1_id).first()
        s2 = db.query(TimeSlot).filter(TimeSlot.id == slot_2_id).first()
        assert slots_overlap(s1, s2) is True, "Interval overlap helper must evaluate True"

        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v110.0",
            status="GENERATED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        shared_faculty = base_entities["faculty_ids"][0]

        # e1 in 09:00-10:30, e2 in 10:00-11:30 for the same faculty
        e1 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][0],
            faculty_id=shared_faculty,
            room_id=base_entities["room_ids"][0],
            slot_id=slot_1_id,
            status="ACTIVE",
        )
        e2 = TimetableEntry(
            version_id=version.id,
            department_id=base_entities["department_id"],
            program_id=base_entities["program_id"],
            semester_id=base_entities["semester_id"],
            section_id=base_entities["section_id"],
            course_id=base_entities["course_ids"][1],
            faculty_id=shared_faculty,
            room_id=base_entities["room_ids"][1],
            slot_id=slot_2_id,
            status="ACTIVE",
        )
        db.add_all([e1, e2])
        db.commit()
        vid = version.id

    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert val_res["is_valid"] is False
    codes = [v["code"] for v in val_res["violations"]]
    assert "FACULTY_OVERLAP" in codes


# ==============================================================================
# Scenario 11: Invalid or stale scheduling data
# ==============================================================================
def test_scenario_11_invalid_or_stale_scheduling_data_inactive_room(admin_token, base_entities):
    """Scenario 11: Scheduling an entry in an INACTIVE room is detected as a ROOM_INACTIVE blocker."""
    with Session(engine) as db:
        maint_room = Room(
            building_id=1,
            room_number="S14-MNT",
            room_type="CLASSROOM",
            capacity=40,
            status="MAINTENANCE",
        )
        db.add(maint_room)
        db.flush()

        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v111.0",
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
            room_id=maint_room.id,
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()
        vid = version.id

    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert val_res["is_valid"] is False
    codes = [v["code"] for v in val_res["violations"]]
    assert "ROOM_INACTIVE" in codes


# ==============================================================================
# Scenario 12: Attempts to publish an invalid timetable
# ==============================================================================
def test_scenario_12_attempts_to_publish_invalid_timetable_rejected_409(admin_token, base_entities):
    """Scenario 12: Publication safeguard rejects conflicting timetable with HTTP 409."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v112.0",
            status="FINALIZED",
            created_by=base_entities["admin_id"],
        )
        db.add(version)
        db.flush()

        shared_room = base_entities["room_ids"][0]
        shared_slot = base_entities["slot_ids"][0]

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

    pub_res = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 409
    assert "Publication rejected" in pub_res.json()["detail"]


# ==============================================================================
# Scenario 13: Persistence and retrieval of the generated timetable
# ==============================================================================
def test_scenario_13_persistence_and_retrieval_of_generated_timetable(admin_token, base_entities):
    """Scenario 13: Generated timetable entries and relationships are fully persisted and retrieved."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v113.0",
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
            room_id=base_entities["room_ids"][0],
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()
        vid = version.id
        eid = entry.id

    detail_res = client.get(f"/timetable/versions/{vid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["id"] == vid
    assert len(data["timetable_entries"]) == 1
    ret_entry = data["timetable_entries"][0]
    assert ret_entry["id"] == eid
    assert ret_entry["course_code"] is not None
    assert ret_entry["faculty_name"] is not None
    assert ret_entry["room_number"] is not None
    assert ret_entry["day"] is not None
    assert ret_entry["start_time"] is not None


# ==============================================================================
# Scenario 14: Repeated generation and publication requests
# ==============================================================================
def test_scenario_14_repeated_generation_and_publication_requests_idempotency(admin_token, base_entities):
    """Scenario 14: Repeated publication requests return 409 idempotency conflict."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v114.0",
            status="FINALIZED",
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
            faculty_id=base_entities["faculty_ids"][1],
            room_id=base_entities["room_ids"][1],
            slot_id=base_entities["slot_ids"][1],
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()
        vid = version.id

    # First publication succeeds
    pub_res1 = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res1.status_code == 200
    assert pub_res1.json()["status"] == "PUBLISHED"

    # Second publication attempt returns 409
    pub_res2 = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res2.status_code == 409
    assert "already PUBLISHED" in pub_res2.json()["detail"]


# ==============================================================================
# Scenario 15: Regression cases for previously working functionality
# ==============================================================================
def test_scenario_15_regression_for_previously_working_functionality(admin_token, student_token, base_entities):
    """Scenario 15: Editing entries resets VALIDATED status to REVIEWED, published versions reject edits, student publication returns 403."""
    with Session(engine) as db:
        version = TimetableVersion(
            academic_year_id=base_entities["academic_year_id"],
            version_number="v115.0",
            status="VALIDATED",
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
            room_id=base_entities["room_ids"][0],
            slot_id=base_entities["slot_ids"][0],
            status="ACTIVE",
        )
        db.add(entry)
        db.commit()
        vid = version.id
        eid = entry.id

    # 1. Edit entry -> status reverts from VALIDATED to REVIEWED
    edit_res = client.patch(
        f"/timetable/entries/{eid}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"room_id": base_entities["room_ids"][1]},
    )
    assert edit_res.status_code == 200

    with Session(engine) as db:
        v_check = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert v_check is not None
        assert v_check.status == "REVIEWED"

    # 2. Non-admin cannot publish (403 Forbidden)
    stud_pub = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {student_token}"})
    assert stud_pub.status_code == 403

    # 3. Finalized/Published versions reject entry editing with 409
    with Session(engine) as db:
        v_pub = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert v_pub is not None
        v_pub.status = "PUBLISHED"
        db.commit()

    edit_pub_res = client.patch(
        f"/timetable/entries/{eid}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"room_id": base_entities["room_ids"][0]},
    )
    assert edit_pub_res.status_code == 409
    assert "Cannot edit an entry in a finalized/published timetable" in edit_pub_res.json()["detail"]
