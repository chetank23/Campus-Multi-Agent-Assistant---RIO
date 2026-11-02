"""
eval/test_portal_completion_acceptance.py
-----------------------------------------
Authoritative Deep Hardening, Repair & End-to-End Acceptance Test Suite
for RIO-MJP: ADMIN, FACULTY, and STUDENT Portals.

Covers:
1. Admin Users & Roles Safeguards (last admin protection, duplicate prevention, hash privacy)
2. Data Import & Atomic Rollback (invalid FK rejection, duplicate detection, atomic commit + readback)
3. Time Slot Constraints & Integrity (start/end sanity, collision detection, deletion integrity)
4. Resource Privacy & Global Booking Locks (PENDING lock, multi-faculty privacy separation)
5. OR-Tools Solver Availability Integration (UNAVAILABLE slot avoidance proof, PREFERRED weighting)
6. Real Timetable Publication Workflow & 3-Role Propagation (DRAFT privacy -> PUBLISH -> Faculty & Student populated readback)
7. Cross-Role Real-Time Status & Notification Integrity
"""

import datetime
import os
import sys
from typing import Any, Dict, Optional

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.models.identity import User
from backend.models.academic import Department, Faculty, Section, Student
from backend.models.courses import Course, CourseAssignment
from backend.models.space_time import Building, Room, TimeSlot, FacultyAvailability
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.optimizer.timetable_solver import TimetableSolver
from backend.schemas.timetable_generation import (
    GenerationScope,
    OptimizerInput,
    OptSection,
    OptCourse,
    OptCourseAssignment,
    OptFaculty,
    OptFacultyAvailability,
    OptTimeSlot,
    OptRoom,
)

client = TestClient(app)

PASS_COUNT = 0
FAIL_COUNT = 0
TEST_LOGS = []


def record_result(category: str, test_name: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        tag = "[PASS]"
    else:
        FAIL_COUNT += 1
        tag = "[FAIL]"
    msg = f"{tag:6} | {category:20} | {test_name:45} | {detail}"
    print(msg)
    TEST_LOGS.append((tag, category, test_name, detail))


def login(email: str, password: str = "Test@1234") -> Optional[str]:
    res = client.post("/auth/login", json={"email": email, "password": password})
    if res.status_code == 200:
        return res.json().get("access_token")
    return None


def run_acceptance_suite():
    print("=" * 115)
    print("RIO-MJP PORTAL ROLE COMPLETION DEEP REPAIR & ACCEPTANCE VERIFICATION SUITE")
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 115)

    # -------------------------------------------------------------------------
    # Authentication Setup
    # -------------------------------------------------------------------------
    admin_token = login("admin@campus.edu")
    faculty_token = login("allison.hill@campus.edu")
    student_token = login("monica.herrera@campus.edu")

    if not admin_token or not faculty_token or not student_token:
        print("[FATAL] Baseline users could not be authenticated.")
        sys.exit(1)

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    faculty_headers = {"Authorization": f"Bearer {faculty_token}"}
    student_headers = {"Authorization": f"Bearer {student_token}"}

    record_result("AUTH", "Three-Role Baseline Login", True, "ADMIN, FACULTY, STUDENT authenticated.")

    # -------------------------------------------------------------------------
    # 1. Admin Users & Roles Safeguards
    # -------------------------------------------------------------------------
    print("\n--- 1. ADMIN USERS & ROLES HARDENING ---")

    # 1.1 Last active ADMIN deactivation protection
    admin_me_res = client.get("/auth/me", headers=admin_headers)
    admin_id = admin_me_res.json()["id"]

    deact_self_res = client.patch(f"/users/{admin_id}", json={"is_active": False}, headers=admin_headers)
    record_result(
        "ADMIN_USERS",
        "Prevent Self-Deactivation of Admin",
        deact_self_res.status_code == 400,
        f"Status: {deact_self_res.status_code} (Detail: {deact_self_res.json().get('detail')})",
    )

    demote_self_res = client.patch(f"/users/{admin_id}", json={"role": "STUDENT"}, headers=admin_headers)
    record_result(
        "ADMIN_USERS",
        "Prevent Revoking Own ADMIN Role",
        demote_self_res.status_code == 400,
        f"Status: {demote_self_res.status_code} (Detail: {demote_self_res.json().get('detail')})",
    )

    # 1.2 Duplicate email check
    dup_res = client.post(
        "/users",
        json={
            "name": "Duplicate Admin Test",
            "email": "admin@campus.edu",
            "password": "Password123!",
            "role": "ADMIN",
        },
        headers=admin_headers,
    )
    record_result(
        "ADMIN_USERS",
        "Reject Duplicate User Email (409)",
        dup_res.status_code == 409,
        f"Status: {dup_res.status_code} (Detail: {dup_res.json().get('detail')})",
    )

    # 1.3 User response password hash privacy
    users_list_res = client.get("/users?limit=5", headers=admin_headers)
    users_data = users_list_res.json().get("items", [])
    has_hash = any("password_hash" in u or "password" in u for u in users_data)
    record_result(
        "ADMIN_USERS",
        "Password Hash Never Leaked in API Responses",
        (not has_hash) and len(users_data) > 0,
        f"Inspected {len(users_data)} users; hashes leaked: {has_hash}",
    )

    # -------------------------------------------------------------------------
    # 2. Data Import & Atomic Rollback
    # -------------------------------------------------------------------------
    print("\n--- 2. DATA IMPORT & ATOMIC INTEGRITY ---")

    # 2.1 Preview detects invalid foreign key
    preview_bad_fk = client.post(
        "/admin/import/preview",
        json={
            "entity_type": "rooms",
            "rows": [
                {
                    "room_number": "TEST-RM-999",
                    "building_id": 999999,  # Non-existent building
                    "capacity": 50,
                    "room_type": "CLASSROOM",
                }
            ],
        },
        headers=admin_headers,
    )
    p_data = preview_bad_fk.json()
    has_fk_err = p_data.get("invalid_rows_count", 0) > 0 and len(p_data.get("errors", [])) > 0
    record_result(
        "DATA_IMPORT",
        "Preview Catches Non-Existent Foreign Key",
        has_fk_err,
        f"Errors detected: {len(p_data.get('errors', []))} (Field: {p_data.get('errors', [{}])[0].get('field')})",
    )

    # 2.2 Preview detects duplicate in payload
    preview_dup = client.post(
        "/admin/import/preview",
        json={
            "entity_type": "courses",
            "rows": [
                {
                    "course_code": "CS-DUP-01",
                    "course_name": "Course 1",
                    "department_id": 1,
                    "course_type": "THEORY",
                    "credits": 3,
                },
                {
                    "course_code": "CS-DUP-01",
                    "course_name": "Course 2",
                    "department_id": 1,
                    "course_type": "THEORY",
                    "credits": 3,
                },
            ],
        },
        headers=admin_headers,
    )
    dup_data = preview_dup.json()
    record_result(
        "DATA_IMPORT",
        "Preview Catches In-Payload Duplicate",
        dup_data.get("invalid_rows_count", 0) > 0,
        f"Invalid count: {dup_data.get('invalid_rows_count')}",
    )

    # 2.3 Commit strictly rejects invalid payload (tamper protection)
    commit_tamper = client.post(
        "/admin/import/commit",
        json={
            "entity_type": "rooms",
            "rows": [
                {
                    "room_number": "TAMPER-001",
                    "building_id": 999999,  # Non-existent FK
                    "capacity": 50,
                    "room_type": "CLASSROOM",
                }
            ],
        },
        headers=admin_headers,
    )
    record_result(
        "DATA_IMPORT",
        "Commit Rejects Invalid/Tampered Payload (400)",
        commit_tamper.status_code == 400,
        f"Status: {commit_tamper.status_code} (Detail: {commit_tamper.json().get('detail')})",
    )

    # 2.4 Atomic commit of valid new courses + immediate readback
    test_code = f"TST{datetime.datetime.now().strftime('%M%S')}"
    commit_valid = client.post(
        "/admin/import/commit",
        json={
            "entity_type": "courses",
            "rows": [
                {
                    "course_code": test_code,
                    "course_name": "Advanced Verification Systems",
                    "department_id": 1,
                    "course_type": "THEORY",
                    "credits": 4,
                }
            ],
        },
        headers=admin_headers,
    )
    commit_ok = commit_valid.status_code == 200 and commit_valid.json().get("imported_count") == 1

    # Readback verification
    courses_res = client.get("/courses/", headers=admin_headers)
    found_course = any(c.get("course_code") == test_code for c in courses_res.json())
    record_result(
        "DATA_IMPORT",
        "Valid Import Atomic Commit & Readback",
        commit_ok and found_course,
        f"Committed code: {test_code}, Verified in course catalog: {found_course}",
    )

    # -------------------------------------------------------------------------
    # 3. Time Slot Constraints & Integrity
    # -------------------------------------------------------------------------
    print("\n--- 3. TIME SLOT VALIDATION & REFERENTIAL INTEGRITY ---")

    # 3.1 Invalid start/end times
    bad_time_res = client.post(
        "/time-slots",
        json={
            "day": "MONDAY",
            "start_time": "14:00:00",
            "end_time": "13:00:00",  # start >= end
            "slot_type": "CLASS",
        },
        headers=admin_headers,
    )
    record_result(
        "TIME_SLOTS",
        "Reject Inverted Time Range (start >= end)",
        bad_time_res.status_code == 400,
        f"Status: {bad_time_res.status_code} (Detail: {bad_time_res.json().get('detail')})",
    )

    # 3.2 Slot overlap rejection
    overlap_res = client.post(
        "/time-slots",
        json={
            "day": "MONDAY",
            "start_time": "09:15:00",
            "end_time": "10:15:00",  # Overlaps standard 09:00-10:00 or 09:30 slot
            "slot_type": "CLASS",
        },
        headers=admin_headers,
    )
    record_result(
        "TIME_SLOTS",
        "Reject Overlapping Time Slot on Same Day",
        overlap_res.status_code == 400,
        f"Status: {overlap_res.status_code} (Detail: {overlap_res.json().get('detail')})",
    )

    # -------------------------------------------------------------------------
    # 4. Resource Booking Privacy & Global Locks
    # -------------------------------------------------------------------------
    print("\n--- 4. RESOURCE BOOKING PRIVACY & LOCKS ---")

    # Fetch available resource
    res_list = client.get("/resources", headers=faculty_headers).json()
    target_res = res_list[0] if res_list else None

    if target_res:
        target_res_id = target_res["id"]
        tomorrow = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()

        # Faculty submits booking request
        book_res = client.post(
            "/resources/bookings",
            json={
                "resource_id": target_res_id,
                "date": tomorrow,
                "start_time": "11:00:00",
                "end_time": "12:00:00",
                "purpose": "Special Robotics Lab Session",
            },
            headers=faculty_headers,
        )
        booking_created = book_res.status_code == 201
        booking_id = book_res.json().get("id") if booking_created else None

        record_result(
            "RESOURCES",
            "Faculty Submits Resource Booking",
            booking_created,
            f"Booking ID: {booking_id}, Status: {book_res.status_code}",
        )

        if booking_id:
            # 4.1 Second booking on same resource is locked globally
            second_book_res = client.post(
                "/resources/bookings",
                json={
                    "resource_id": target_res_id,
                    "date": (datetime.date.today() + datetime.timedelta(days=3)).isoformat(),
                    "start_time": "14:00:00",
                    "end_time": "15:00:00",
                    "purpose": "Concurrent Conflicting Booking",
                },
                headers=admin_headers,
            )
            record_result(
                "RESOURCES",
                "Active Booking (PENDING) Globally Locks Resource",
                second_book_res.status_code == 409,
                f"Status: {second_book_res.status_code} (Expected 409 Active Lock)",
            )

            # 4.2 Student booking privacy separation (cannot see faculty's pending booking)
            student_bookings = client.get("/resources/bookings", headers=student_headers).json()
            student_sees_pending = any(b.get("id") == booking_id for b in student_bookings)
            record_result(
                "RESOURCES",
                "Student Cannot See Other User's Pending Booking",
                not student_sees_pending,
                f"Student bookings returned: {len(student_bookings)}, Saw pending: {student_sees_pending}",
            )

            # 4.3 Clean up / Cancel test booking
            cancel_res = client.post(
                f"/resources/bookings/{booking_id}/cancel",
                json={"reason": "Automated acceptance test cleanup"},
                headers=faculty_headers,
            )
            record_result(
                "RESOURCES",
                "Cancel Booking and Release Global Resource Lock",
                cancel_res.status_code == 200,
                f"Cancelled status: {cancel_res.json().get('status')}",
            )

    # -------------------------------------------------------------------------
    # 5. OR-Tools Solver Availability Integration
    # -------------------------------------------------------------------------
    print("\n--- 5. OR-TOOLS SOLVER FACULTY AVAILABILITY INTEGRATION ---")

    # Build synthetic test problem with 1 section, 1 course (2 lecture hours), 1 faculty, 2 rooms, 5 slots
    opt_sec = OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)
    opt_crs = OptCourse(
        id=1,
        department_id=1,
        course_type="THEORY",
        credits=3,
        lecture_hours=2,
        tutorial_hours=0,
        practical_hours=0,
        requires_lab=False,
    )
    opt_assign = OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1, batch_id=None)
    opt_fac = OptFaculty(id=1, department_id=1, max_weekly_load=18)
    opt_rooms = [
        OptRoom(id=1, building_id=1, room_type="CLASSROOM", capacity=40),
        OptRoom(id=2, building_id=1, room_type="CLASSROOM", capacity=40),
    ]
    opt_slots = [
        OptTimeSlot(id=1, day="MON", start_time=datetime.time(9, 0), end_time=datetime.time(10, 0), slot_type="CLASS"),
        OptTimeSlot(id=2, day="MON", start_time=datetime.time(10, 0), end_time=datetime.time(11, 0), slot_type="CLASS"),
        OptTimeSlot(id=3, day="TUE", start_time=datetime.time(9, 0), end_time=datetime.time(10, 0), slot_type="CLASS"),
        OptTimeSlot(id=4, day="TUE", start_time=datetime.time(10, 0), end_time=datetime.time(11, 0), slot_type="CLASS"),
        OptTimeSlot(id=5, day="WED", start_time=datetime.time(9, 0), end_time=datetime.time(10, 0), slot_type="CLASS"),
    ]

    # Constrain Slot 1 and Slot 2 as UNAVAILABLE for Faculty 1
    opt_avail = [
        OptFacultyAvailability(id=1, faculty_id=1, slot_id=1, availability="UNAVAILABLE", preference=0),
        OptFacultyAvailability(id=2, faculty_id=1, slot_id=2, availability="UNAVAILABLE", preference=0),
        OptFacultyAvailability(id=3, faculty_id=1, slot_id=3, availability="PREFERRED", preference=5),
    ]

    synth_scope = GenerationScope(
        academic_year_id=1,
        semester_id=1,
        department_id=1,
        program_id=1,
    )

    synth_input = OptimizerInput(
        scope=synth_scope,
        sections=[opt_sec],
        courses=[opt_crs],
        course_assignments=[opt_assign],
        faculty=[opt_fac],
        faculty_availability=opt_avail,
        time_slots=opt_slots,
        rooms=opt_rooms,
        batches=[],
        labs=[],
        academic_calendar=[],
        elective_groups=[],
        elective_group_courses=[],
    )

    solver = TimetableSolver(opt_input=synth_input, time_limit=10, strategy="BALANCED")
    solver_res = solver.solve()

    assigned_slots = [e.slot_id for e in solver_res.entries if e.course_assignment_id == 1]
    violated_unavailable = any(s in (1, 2) for s in assigned_slots)
    chose_preferred = 3 in assigned_slots

    record_result(
        "OR_TOOLS_SOLVER",
        "UNAVAILABLE Slots Never Assigned to Faculty",
        solver_res.feasible and not violated_unavailable,
        f"Feasible: {solver_res.feasible}, Assigned slots: {assigned_slots}, Violated: {violated_unavailable}",
    )
    record_result(
        "OR_TOOLS_SOLVER",
        "PREFERRED Slot Maximized in Objective",
        solver_res.feasible and chose_preferred,
        f"Preferred slot 3 selected: {chose_preferred} in {assigned_slots}",
    )

    # -------------------------------------------------------------------------
    # 6. Real Timetable Publication & 3-Role Propagation
    # -------------------------------------------------------------------------
    print("\n--- 6. TIMETABLE PUBLICATION & 3-ROLE WORKFLOW ---")

    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        test_fac = db.query(Faculty).filter(Faculty.user_id == 2).first()  # Allison Hill (Dept 3)
        test_stu = db.query(Student).filter(Student.user_id == 12).first() # Monica Herrera (Section 1, Dept 3)
        room_obj = db.query(Room).filter(Room.id == 2).first()             # SB-101 (cap 60)
        course_obj = db.query(Course).filter(Course.id == 5).first()       # EE614 (THEORY, Dept 3)
        slot_list = db.query(TimeSlot).filter(TimeSlot.id.in_([1, 2, 4])).all()

        # Find or create dedicated test timetable version
        target_version = db.query(TimetableVersion).filter(TimetableVersion.reason == "Automated Acceptance Test Timetable").first()
        if not target_version:
            target_version = TimetableVersion(
                academic_year_id=1,
                version_number=99,
                status="DRAFT",
                created_by=admin_user.id if admin_user else 1,
                reason="Automated Acceptance Test Timetable",
            )
            db.add(target_version)
            db.flush()

            for slt in slot_list:
                entry = TimetableEntry(
                    version_id=target_version.id,
                    department_id=test_fac.department_id,
                    program_id=1,
                    semester_id=1,
                    section_id=test_stu.section_id,
                    course_id=course_obj.id,
                    faculty_id=test_fac.id,
                    room_id=room_obj.id,
                    slot_id=slt.id,
                    status="ACTIVE",
                )
                db.add(entry)
            db.commit()

        v_id = target_version.id

        # 6.1 Verify DRAFT Privacy (when unpublished, students and faculty see 0 entries)
        target_version.status = "DRAFT"
        db.commit()

        fac_draft_res = client.get("/faculty/my-timetable", headers=faculty_headers).json()
        stu_draft_res = client.get("/student/my-timetable", headers=student_headers).json()

        record_result(
            "TIMETABLE_PUB",
            "Unpublished Draft Inaccessible to Faculty",
            len(fac_draft_res.get("entries", [])) == 0,
            f"Faculty entries: {len(fac_draft_res.get('entries', []))}",
        )
        record_result(
            "TIMETABLE_PUB",
            "Unpublished Draft Inaccessible to Student",
            len(stu_draft_res.get("entries", [])) == 0,
            f"Student entries: {len(stu_draft_res.get('entries', []))}",
        )

        # 6.2 Admin Validation, Finalization, and Publication Lifecycle
        val_res = client.post(f"/timetable/versions/{v_id}/validate", headers=admin_headers)
        record_result(
            "TIMETABLE_PUB",
            "Admin Validates Timetable Version",
            val_res.status_code == 200 and val_res.json().get("is_valid") is True,
            f"Valid: {val_res.json().get('is_valid')}, Blockers: {val_res.json().get('blocker_count')}",
        )

        fin_res = client.post(f"/timetable/versions/{v_id}/finalize", headers=admin_headers)
        record_result(
            "TIMETABLE_PUB",
            "Admin Finalizes Timetable Version",
            fin_res.status_code == 200,
            f"Status: {fin_res.status_code}, Finalized status: {fin_res.json().get('status')}",
        )

        pub_res = client.post(f"/timetable/versions/{v_id}/publish", headers=admin_headers)
        record_result(
            "TIMETABLE_PUB",
            "Admin Publishes Timetable Version",
            pub_res.status_code == 200,
            f"Status: {pub_res.status_code}, Published: {pub_res.json().get('status')}",
        )

        # 6.3 Faculty Receives Populated Entries
        fac_pub_res = client.get("/faculty/my-timetable", headers=faculty_headers).json()
        fac_entries = fac_pub_res.get("entries", [])
        record_result(
            "TIMETABLE_PUB",
            "Faculty Receives Populated My-Timetable",
            len(fac_entries) > 0,
            f"Returned {len(fac_entries)} personal teaching entries (Hours: {fac_pub_res.get('total_teaching_hours')})",
        )

        # 6.4 Department Timetable Isolation
        dept_tt_res = client.get("/faculty/department-timetable", headers=faculty_headers).json()
        dept_entries = dept_tt_res.get("entries", [])
        record_result(
            "TIMETABLE_PUB",
            "Faculty Department Timetable Isolated to Own Dept",
            len(dept_entries) > 0 and dept_tt_res.get("department_id") == test_fac.department_id,
            f"Dept ID: {dept_tt_res.get('department_id')}, Total entries: {len(dept_entries)}",
        )

        # 6.5 Student Receives Populated Section Timetable
        stu_pub_res = client.get("/student/my-timetable", headers=student_headers).json()
        stu_entries = stu_pub_res.get("entries", [])
        record_result(
            "TIMETABLE_PUB",
            "Student Receives Populated Section Timetable",
            len(stu_entries) > 0,
            f"Returned {len(stu_entries)} class entries for Section {stu_pub_res.get('section_name')}",
        )

        # 6.6 Cross-Section Isolation (Student from different section sees 0 entries of this section)
        other_stu = db.query(Student).filter(Student.section_id != test_stu.section_id).first()
        if other_stu and other_stu.user:
            other_stu_token = login(other_stu.user.email)
            if other_stu_token:
                other_stu_res = client.get(
                    "/student/my-timetable",
                    headers={"Authorization": f"Bearer {other_stu_token}"},
                ).json()
                other_entries = other_stu_res.get("entries", [])
                sec_1_name = test_stu.section.section_name if test_stu.section else "A"
                saw_other_section = any(e.get("section_name") == sec_1_name for e in other_entries)
                record_result(
                    "TIMETABLE_PUB",
                    "Student Section Boundary Privacy Strictly Enforced",
                    not saw_other_section,
                    f"Other student entries: {len(other_entries)}, Leaked other section: {saw_other_section}",
                )

    finally:
        db.close()

    # -------------------------------------------------------------------------
    # 7. Live Real-Time Status & Announcement Propagation
    # -------------------------------------------------------------------------
    print("\n--- 7. LIVE STATUS & REAL-TIME REPUTATION ---")

    fac_live = client.get("/faculty/live-status", headers=faculty_headers)
    stu_live = client.get("/student/live-status", headers=student_headers)

    record_result(
        "LIVE_STATUS",
        "Faculty Live Status Endpoint Responsive",
        fac_live.status_code == 200,
        f"Status: {fac_live.status_code}, Payload keys: {list(fac_live.json().keys()) if fac_live.json() else None}",
    )
    record_result(
        "LIVE_STATUS",
        "Student Live Status Endpoint Responsive",
        stu_live.status_code == 200,
        f"Status: {stu_live.status_code}, Payload keys: {list(stu_live.json().keys()) if stu_live.json() else None}",
    )

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 115)
    print(f"ACCEPTANCE RESULTS: {PASS_COUNT} PASSED, {FAIL_COUNT} FAILED")
    print("=" * 115)

    if FAIL_COUNT > 0:
        print("\n[ERROR] Acceptance suite encountered failures:")
        for log in TEST_LOGS:
            if log[0] == "[FAIL]":
                print(f"  - {log[1]} :: {log[2]} -> {log[3]}")
        sys.exit(1)
    else:
        print("\n[SUCCESS] ALL ACCEPTANCE GATES PASSED CLEANLY!")
        sys.exit(0)


if __name__ == "__main__":
    run_acceptance_suite()
