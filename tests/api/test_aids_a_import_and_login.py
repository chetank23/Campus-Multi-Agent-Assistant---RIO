"""
tests/api/test_aids_a_import_and_login.py
-----------------------------------------
Authoritative tests for AIDS-A Master Dataset Import, All 60 Student Logins,
Faculty Login (Dr. Nimrita Koul), Profile and Timetable endpoints, and Security RBAC.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Department, Program, AcademicYear, Semester, Section, Batch, Student, Faculty
from backend.models.space_time import Building, Room, Lab, TimeSlot
from backend.models.courses import Course, CourseAssignment
from backend.core.security import verify_password
from scripts.import_aids_a_dataset import import_aids_a_dataset, DEFAULT_TEST_PASSWORD

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_aids_a_data():
    """Ensure the AIDS-A dataset is imported into the isolated test database."""
    with Session(engine) as db:
        import_aids_a_dataset(db, configure_candidate_rooms=True)
    yield


class TestAidsAImportAndLogin:
    def test_01_academic_hierarchy_imported(self):
        with Session(engine) as test_db:
            dept = test_db.query(Department).filter(
                (Department.department_code == "AIDS") | (Department.name == "AI & DS")
            ).first()
            assert dept is not None
            assert dept.department_code == "AIDS"
            assert dept.name == "AI & DS"

            prog = test_db.query(Program).filter(Program.department_id == dept.id).first()
            assert prog is not None
            assert prog.program_name is not None and ("Artificial Intelligence" in prog.program_name or "AI & DS" in prog.program_name)

            ay = test_db.query(AcademicYear).filter(AcademicYear.name == "2026-2027").first()
            assert ay is not None

            sem = test_db.query(Semester).filter(
                Semester.academic_year_id == ay.id,
                Semester.semester_number == 7,
            ).first()
            assert sem is not None

            sec = test_db.query(Section).filter(
                Section.department_id == dept.id,
                Section.semester_id == sem.id,
                Section.section_name == "AIDS-A",
            ).first()
            assert sec is not None
            assert sec.student_count == 60

            batch = test_db.query(Batch).filter(
                Batch.section_id == sec.id,
                Batch.batch_name == "2023",
            ).first()
            assert batch is not None

    def test_02_dr_nimrita_koul_faculty_profile_and_class_teacher(self):
        with Session(engine) as test_db:
            fac_user = test_db.query(User).filter(User.email == "nimrita.koul@rio-mjp.test").first()
            assert fac_user is not None
            assert fac_user.name == "Dr. Nimrita Koul"
            assert fac_user.role == "FACULTY"
            assert verify_password(DEFAULT_TEST_PASSWORD, fac_user.password_hash)

            fac_rec = test_db.query(Faculty).filter(Faculty.user_id == fac_user.id).first()
            assert fac_rec is not None
            assert fac_rec.designation == "Associate Professor"
            assert fac_rec.contact_number == "8861097464"
            assert fac_rec.specialization == "Agentic AI"

            # Verify class teacher connection on Section AIDS-A
            sec = test_db.query(Section).filter(Section.section_name == "AIDS-A").first()
            assert sec is not None
            assert sec.class_teacher_id == fac_rec.id

            # Verify assigned hardcore courses
            assignments = test_db.query(CourseAssignment).filter(
                CourseAssignment.section_id == sec.id,
                CourseAssignment.faculty_id == fac_rec.id,
            ).all()
            assigned_codes = [ca.course.course_code for ca in assignments if ca.course]
            assert "B25CS0701" in assigned_codes  # Principles of Federated Learning (PFL)
            assert "B22EF0704" in assigned_codes  # Internship
            assert "B22EH0704" in assigned_codes  # PP-1

        # Test login API for Dr. Nimrita Koul
        res = client.post("/auth/login", json={
            "email": "nimrita.koul@rio-mjp.test",
            "password": DEFAULT_TEST_PASSWORD,
        })
        assert res.status_code == 200, res.text
        data = res.json()
        assert "access_token" in data
        token = data["access_token"]

        me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["role"] == "FACULTY"
        assert me_data["email"] == "nimrita.koul@rio-mjp.test"

    def test_03_all_60_students_imported_and_login_verified(self):
        with Session(engine) as test_db:
            sec = test_db.query(Section).filter(Section.section_name == "AIDS-A").first()
            assert sec is not None

            students = (
                test_db.query(Student)
                .filter(Student.section_id == sec.id)
                .order_by(Student.student_id.asc())
                .all()
            )
            assert len(students) == 60, f"Expected exactly 60 students, found {len(students)}"

            # Verify all 60 SRNs from R23EH001 to R23EH060
            expected_blank_srns = {
                "R23EH004", "R23EH005", "R23EH011", "R23EH021", "R23EH029",
                "R23EH035", "R23EH039", "R23EH044", "R23EH052", "R23EH054",
                "R23EH056", "R23EH060"
            }

            for idx in range(1, 61):
                expected_srn = f"R23EH{idx:03d}"
                stu = next((s for s in students if s.student_id == expected_srn), None)
                assert stu is not None, f"Student {expected_srn} missing from database"
                assert stu.user is not None, f"User missing for student {expected_srn}"
                assert stu.user.email == f"{expected_srn.lower()}@rio-mjp.test"
                assert stu.user.role == "STUDENT"
                assert verify_password(DEFAULT_TEST_PASSWORD, stu.user.password_hash)

                if expected_srn in expected_blank_srns:
                    assert stu.user.name == "", f"Expected blank name for {expected_srn}, got '{stu.user.name}'"
                else:
                    assert len(stu.user.name) > 0, f"Expected non-blank name for {expected_srn}"

        # Test API login specifically for R23EH001, R23EH002, and R23EH060 (blank name student)
        for test_srn in ["R23EH001", "R23EH002", "R23EH060"]:
            test_email = f"{test_srn.lower()}@rio-mjp.test"
            res = client.post("/auth/login", json={
                "email": test_email,
                "password": DEFAULT_TEST_PASSWORD,
            })
            assert res.status_code == 200, f"Login failed for {test_srn}: {res.text}"
            token = res.json()["access_token"]

            me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me_res.status_code == 200
            me_data = me_res.json()
            assert me_data["role"] == "STUDENT"
            assert me_data["email"] == test_email

    def test_04_building_rooms_and_labs_inventory(self):
        with Session(engine) as test_db:
            bldg = test_db.query(Building).filter(Building.code == "SMV-BLK-01").first()
            assert bldg is not None
            assert bldg.name == "SIR M VISHWESH BLOCK"
            assert bldg.number_of_floors == 9

            # Rooms
            total_rooms = test_db.query(Room).filter(Room.building_id == bldg.id).count()
            assert total_rooms == 225, f"Expected 225 rooms, found {total_rooms}"

            # Labs
            labs = (
                test_db.query(Lab)
                .join(Room, Lab.room_id == Room.id)
                .filter(Room.building_id == bldg.id)
                .all()
            )
            assert len(labs) == 18, f"Expected 18 labs, found {len(labs)}"

            # Verify 25 rooms per floor (floors 0 through 8)
            for flr in range(9):
                flr_rooms = test_db.query(Room).filter(
                    Room.building_id == bldg.id,
                    Room.floor_number == flr,
                ).count()
                assert flr_rooms == 25, f"Floor {flr} has {flr_rooms} rooms instead of 25"

                flr_labs = (
                    test_db.query(Lab)
                    .join(Room, Lab.room_id == Room.id)
                    .filter(Room.building_id == bldg.id, Room.floor_number == flr)
                    .count()
                )
                assert flr_labs == 2, f"Floor {flr} has {flr_labs} labs instead of 2"

    def test_05_periods_and_breaks(self):
        with Session(engine) as test_db:
            working_days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
            for day in working_days:
                slots = test_db.query(TimeSlot).filter(TimeSlot.day == day).all()
                assert len(slots) == 9, f"Expected 9 slots on {day}, found {len(slots)}"

                class_slots = [s for s in slots if s.slot_type == "CLASS"]
                break_slots = [s for s in slots if s.slot_type in ("BREAK", "LUNCH")]
                assert len(class_slots) == 7, f"Expected 7 class periods, found {len(class_slots)}"
                assert len(break_slots) == 2, f"Expected 2 breaks (tea + lunch), found {len(break_slots)}"

    def test_06_student_rbac_and_isolation(self):
        # 1. Log in as student R23EH001
        res = client.post("/auth/login", json={
            "email": "r23eh001@rio-mjp.test",
            "password": DEFAULT_TEST_PASSWORD,
        })
        assert res.status_code == 200
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Student cannot access Admin or Super Admin endpoints
        res_admin = client.get("/admin/audit-logs", headers=headers)
        assert res_admin.status_code == 403, "Student must be forbidden from /admin endpoints"

        res_super = client.get("/super-admin/regulations", headers=headers)
        assert res_super.status_code == 403, "Student must be forbidden from /super-admin endpoints"

        # 3. Student can query own timetable
        res_tt = client.get("/student/my-timetable", headers=headers)
        assert res_tt.status_code == 200
        tt_data = res_tt.json()
        assert tt_data["student_code"] == "R23EH001"
        assert tt_data["section_name"] == "AIDS-A"
