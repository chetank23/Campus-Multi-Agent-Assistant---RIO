"""
tests/api/test_aids_a_timetable_generation.py
---------------------------------------------
End-to-end integration test verifying automated timetable generation,
validation, finalization, publication, and student/faculty schedule access
for Department: AI & DS, Section: AIDS-A, Building: SIR M VISHWESH BLOCK.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.core.security import create_access_token
from backend.database import SessionLocal
from backend.main import app
from backend.models.academic import AcademicYear, Department, Program, Section, Semester
from backend.models.identity import User
from backend.models.space_time import Building, Room
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.config import engine
from scripts.import_aids_a_dataset import import_aids_a_dataset

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def ensure_aids_a_dataset():
    """Ensure the AIDS-A dataset is imported into the test database before running tests."""
    with Session(engine) as db:
        import_aids_a_dataset(db, configure_candidate_rooms=True)
    yield


@pytest.fixture
def admin_token():
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        assert admin_user is not None
        return create_access_token(data={"sub": str(admin_user.id), "role": "ADMIN"})


@pytest.fixture
def student_token():
    with SessionLocal() as db:
        student_user = db.query(User).filter(User.email == "r23eh001@rio-mjp.test").first()
        assert student_user is not None
        return create_access_token(data={"sub": str(student_user.id), "role": "STUDENT"})


@pytest.fixture
def faculty_token():
    with SessionLocal() as db:
        faculty_user = db.query(User).filter(User.email == "nimrita.koul@rio-mjp.test").first()
        assert faculty_user is not None
        return create_access_token(data={"sub": str(faculty_user.id), "role": "FACULTY"})


class TestAidsATimetableGeneration:
    """Verifies complete fresh timetable generation workflow for Section AIDS-A."""

    def test_01_generate_fresh_timetable_for_aids_a(self, admin_token):
        with SessionLocal() as db:
            dept = db.query(Department).filter(Department.department_code == "AIDS").first()
            assert dept is not None
            prog = db.query(Program).filter(Program.department_id == dept.id).first()
            assert prog is not None
            ay = db.query(AcademicYear).filter(AcademicYear.name == "2026-2027").first()
            assert ay is not None
            sem = db.query(Semester).filter(
                Semester.academic_year_id == ay.id,
                Semester.semester_number == 7,
            ).first()
            assert sem is not None
            sec = db.query(Section).filter(Section.section_name == "AIDS-A").first()
            assert sec is not None
            bldg = db.query(Building).filter(Building.code == "SMV-BLK-01").first()
            assert bldg is not None

            candidate_rooms = (
                db.query(Room)
                .filter(
                    Room.building_id == bldg.id,
                    Room.status == "ACTIVE",
                    ((Room.room_type == "CLASSROOM") & (Room.capacity >= 60))
                    | ((Room.room_type == "LAB") & (Room.capacity >= 40)),
                )
                .limit(10)
                .all()
            )
            room_ids = [r.id for r in candidate_rooms]

            scope = {
                "academic_year_id": ay.id,
                "semester_id": sem.id,
                "department_id": dept.id,
                "program_id": prog.id,
                "section_ids": [sec.id],
                "building_ids": [bldg.id],
                "room_ids": room_ids,
            }

        response = client.post(
            "/timetable/generate",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=scope,
        )

        assert response.status_code == 200, f"Generate failed: {response.text}"
        data = response.json()
        assert data["version_id"] is not None
        assert data["status"] in ("OPTIMAL", "FEASIBLE")
        assert data["loaded_sections"] >= 1
        assert data["loaded_courses"] >= 1
        assert data["loaded_rooms"] >= 1

        # Save version_id for subsequent tests
        TestAidsATimetableGeneration.generated_version_id = data["version_id"]

    def test_02_validate_generated_timetable_version(self, admin_token):
        version_id = getattr(TestAidsATimetableGeneration, "generated_version_id", None)
        assert version_id is not None, "Previous generation test must set generated_version_id"

        response = client.post(
            f"/timetable/versions/{version_id}/validate",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Validate failed: {response.text}"
        data = response.json()
        assert data["is_valid"] is True
        assert data.get("blocker_count", 0) == 0

    def test_03_finalize_generated_timetable_version(self, admin_token):
        version_id = getattr(TestAidsATimetableGeneration, "generated_version_id", None)
        assert version_id is not None

        response = client.post(
            f"/timetable/versions/{version_id}/finalize",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Finalize failed: {response.text}"
        data = response.json()
        assert data["status"] == "FINALIZED"

    def test_04_publish_generated_timetable_version(self, admin_token):
        version_id = getattr(TestAidsATimetableGeneration, "generated_version_id", None)
        assert version_id is not None

        response = client.post(
            f"/timetable/versions/{version_id}/publish",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200, f"Publish failed: {response.text}"
        data = response.json()
        assert data["status"] == "PUBLISHED"

    def test_05_student_views_published_timetable(self, student_token):
        response = client.get(
            "/student/my-timetable",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert response.status_code == 200, f"Student timetable failed: {response.text}"
        data = response.json()
        assert data["academic_year_name"] == "2026-2027"
        assert data["class_teacher_name"] == "Dr. Nimrita Koul"
        assert len(data["entries"]) > 0

    def test_06_faculty_views_published_schedule_and_class_teacher_role(self, faculty_token):
        response = client.get(
            "/faculty/my-timetable",
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert response.status_code == 200, f"Faculty timetable failed: {response.text}"
        data = response.json()
        assert "AIDS-A" in data.get("sections_as_class_teacher", [])
        assert len(data["entries"]) > 0
