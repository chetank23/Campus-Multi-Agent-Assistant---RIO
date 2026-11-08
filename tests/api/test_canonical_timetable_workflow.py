"""
tests/api/test_canonical_timetable_workflow.py
---------------------------------------------
Comprehensive tests for the simplified canonical timetable workflow:
Admin selects Academic Year -> Semester -> Department -> Generate Timetable ->
Validate Constraints -> Preview -> Publish.

Validates:
1. Dependent selection endpoints (/timetable/academic-years, semesters, departments, sections)
2. In-memory temporary preview generation (no premature DB persistence)
3. Constraint validation (solver + validator)
4. Publishing to canonical timetable (exactly ONE record per Academic Year + Semester + Section)
5. Student and Faculty schedule access to published canonical timetable
6. Regeneration replacing existing entries transactionally without duplicate canonical records
"""

from __future__ import annotations

from typing import Any, ClassVar
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.core.security import create_access_token
from backend.database import SessionLocal
from backend.main import app
from backend.models.academic import AcademicYear, Department, Section, Semester
from backend.models.identity import User
from backend.models.timetable import Timetable, TimetableEntry
from backend.config import engine
from scripts.import_aids_a_dataset import import_aids_a_dataset

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_dataset():
    """Ensure AIDS-A dataset is imported into the test database."""
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


class TestCanonicalTimetableWorkflow:
    preview_data: ClassVar[dict[str, Any]] = {}
    scope: ClassVar[dict[str, Any]] = {}

    def test_01_dependent_selection_endpoints(self, admin_token):
        """Verify academic years, semesters, departments, and sections dropdown APIs."""
        # 1. Academic Years
        ay_res = client.get(
            "/timetable/academic-years",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert ay_res.status_code == 200
        ay_data = ay_res.json()
        assert len(ay_data) >= 1
        ay_2627 = next((ay for ay in ay_data if "2026" in ay["name"]), ay_data[0])
        ay_id = ay_2627["id"]

        # 2. Semesters for Academic Year
        sem_res = client.get(
            f"/timetable/semesters?academic_year_id={ay_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert sem_res.status_code == 200
        sem_data = sem_res.json()
        assert len(sem_data) >= 1
        sem_7 = next((s for s in sem_data if s["semester_number"] == 7), sem_data[0])
        sem_id = sem_7["id"]

        # 3. Departments for Semester
        dept_res = client.get(
            f"/timetable/departments?academic_year_id={ay_id}&semester_id={sem_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert dept_res.status_code == 200
        dept_data = dept_res.json()
        assert len(dept_data) >= 1
        aids_dept = next((d for d in dept_data if d["department_code"] == "AIDS"), dept_data[0])
        dept_id = aids_dept["id"]

        # 4. Sections for Department & Semester
        sec_res = client.get(
            f"/timetable/sections?department_id={dept_id}&semester_id={sem_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert sec_res.status_code == 200
        sec_data = sec_res.json()
        assert len(sec_data) >= 1
        assert any(s["section_name"] == "AIDS-A" for s in sec_data)

    def test_02_generate_preview_does_not_persist(self, admin_token):
        """Generate Timetable Preview returns in-memory schedules without persisting to DB."""
        with SessionLocal() as db:
            dept = db.query(Department).filter(Department.department_code == "AIDS").first()
            ay = db.query(AcademicYear).filter(AcademicYear.name == "2026-2027").first()
            assert ay is not None
            assert dept is not None
            sem = db.query(Semester).filter(
                Semester.academic_year_id == ay.id,
                Semester.semester_number == 7,
            ).first()
            assert sem is not None
            sec = db.query(Section).filter(Section.section_name == "AIDS-A").first()
            assert sec is not None

            # Record baseline canonical timetables count
            initial_count = db.query(Timetable).count()

        preview_payload = {
            "academic_year_id": ay.id,
            "semester_id": sem.id,
            "department_id": dept.id,
            "section_ids": [sec.id],
        }

        res = client.post(
            "/timetable/generate-preview",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=preview_payload,
        )
        assert res.status_code == 200, f"Preview generation failed: {res.text}"
        data = res.json()

        assert data["status"] in ("OPTIMAL", "FEASIBLE")
        assert data["can_publish"] is True
        assert data["is_valid"] is True
        assert data["blocker_count"] == 0
        assert len(data["sections"]) >= 1
        assert len(data["entries"]) >= 20

        # Verify no break slot was assigned to any subject
        for entry in data["entries"]:
            slot_type = entry.get("slot_type") or ""
            assert slot_type.upper() not in ("BREAK", "LUNCH", "TEA BREAK", "LUNCH BREAK")

        # CRITICAL: Verify DB did NOT gain any new persistent Timetable records from preview!
        with SessionLocal() as db:
            current_count = db.query(Timetable).count()
            assert current_count == initial_count, "Preview generation must NOT persist any timetable records"

        # Cache preview response data for publication test
        TestCanonicalTimetableWorkflow.preview_data = data
        TestCanonicalTimetableWorkflow.scope = preview_payload

    def test_03_publish_canonical_timetable(self, admin_token, student_token, faculty_token):
        """Publish canonical timetable creates or updates the single record and unlocks student/faculty views."""
        preview_data = TestCanonicalTimetableWorkflow.preview_data
        scope = TestCanonicalTimetableWorkflow.scope

        publish_payload = {
            "academic_year_id": scope["academic_year_id"],
            "semester_id": scope["semester_id"],
            "department_id": scope["department_id"],
            "entries": preview_data["entries"],
        }

        pub_res = client.post(
            "/timetable/publish",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=publish_payload,
        )
        assert pub_res.status_code == 200, f"Publish failed: {pub_res.text}"
        pub_json = pub_res.json()
        assert pub_json["success"] is True
        assert pub_json["total_entries_published"] == len(preview_data["entries"])
        assert len(pub_json["published_timetables"]) >= 1
        canonical_tt_id = pub_json["published_timetables"][0]["id"]
        sec_id = scope["section_ids"][0]

        # Verify DB integrity: exactly ONE canonical timetable for this AY + Sem + Section
        with SessionLocal() as db:
            tts = (
                db.query(Timetable)
                .filter(
                    Timetable.academic_year_id == scope["academic_year_id"],
                    Timetable.semester_id == scope["semester_id"],
                    Timetable.section_id == sec_id,
                )
                .all()
            )
            assert len(tts) == 1
            assert tts[0].id == canonical_tt_id
            assert tts[0].status == "PUBLISHED"

            entry_count = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == canonical_tt_id).count()
            assert entry_count == len(preview_data["entries"])

        # Verify Student can see their published canonical timetable
        stu_res = client.get(
            "/student/my-timetable",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert stu_res.status_code == 200
        stu_data = stu_res.json()
        assert len(stu_data["entries"]) == len(preview_data["entries"])

        # Verify Faculty can see their scheduled classes
        fac_res = client.get(
            "/faculty/my-timetable",
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert fac_res.status_code == 200
        fac_data = fac_res.json()
        assert len(fac_data) > 0

    def test_04_regenerate_and_replace_retains_single_canonical_record(self, admin_token):
        """Regenerating and publishing again replaces entries without creating duplicate canonical records."""
        scope = TestCanonicalTimetableWorkflow.scope
        sec_id = scope["section_ids"][0]

        # Fetch canonical timetable before regeneration
        get_res = client.get(
            f"/timetable/canonical?academic_year_id={scope['academic_year_id']}&semester_id={scope['semester_id']}&department_id={scope['department_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert get_res.status_code == 200
        published_list = get_res.json()
        assert len(published_list) >= 1
        original_tt_id = published_list[0]["id"]

        # 1. Generate new preview
        preview_res = client.post(
            "/timetable/generate-preview",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=scope,
        )
        assert preview_res.status_code == 200
        new_preview = preview_res.json()

        # 2. Publish new preview
        repub_res = client.post(
            "/timetable/publish",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "academic_year_id": scope["academic_year_id"],
                "semester_id": scope["semester_id"],
                "department_id": scope["department_id"],
                "entries": new_preview["entries"],
            },
        )
        assert repub_res.status_code == 200
        repub_json = repub_res.json()
        assert repub_json["success"] is True

        # Canonical timetable ID is preserved (or replaced in place)
        assert repub_json["published_timetables"][0]["id"] == original_tt_id

        # Verify in DB: exactly ONE timetable record exists for (AY, Sem, Section)
        with SessionLocal() as db:
            records = (
                db.query(Timetable)
                .filter(
                    Timetable.academic_year_id == scope["academic_year_id"],
                    Timetable.semester_id == scope["semester_id"],
                    Timetable.section_id == sec_id,
                )
                .all()
            )
            assert len(records) == 1, "Must never create duplicate canonical timetable records"
            assert records[0].id == original_tt_id

    def test_05_failed_regeneration_preserves_published_schedule(self, admin_token):
        """If a publish attempt fails with invalid payload, existing canonical timetable remains untouched."""
        scope = TestCanonicalTimetableWorkflow.scope
        sec_id = scope["section_ids"][0]

        with SessionLocal() as db:
            before_tt = (
                db.query(Timetable)
                .filter(
                    Timetable.academic_year_id == scope["academic_year_id"],
                    Timetable.semester_id == scope["semester_id"],
                    Timetable.section_id == sec_id,
                )
                .first()
            )
            assert before_tt is not None
            before_count = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == before_tt.id).count()

        # Send invalid publish request (e.g. non-existent slot_id)
        bad_payload = {
            "academic_year_id": scope["academic_year_id"],
            "semester_id": scope["semester_id"],
            "department_id": scope["department_id"],
            "entries": [
                {
                    "section_id": sec_id,
                    "course_id": 999999,
                    "slot_id": 999999,
                    "day": "MON",
                }
            ],
        }

        bad_res = client.post(
            "/timetable/publish",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=bad_payload,
        )
        assert bad_res.status_code in (400, 404, 422, 500)

        # Verify existing schedule was preserved without corruption
        with SessionLocal() as db:
            after_tt = (
                db.query(Timetable)
                .filter(
                    Timetable.academic_year_id == scope["academic_year_id"],
                    Timetable.semester_id == scope["semester_id"],
                    Timetable.section_id == sec_id,
                )
                .first()
            )
            assert after_tt is not None
            assert after_tt.id == before_tt.id
            after_count = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == after_tt.id).count()
            assert after_count == before_count, "Failed publish must preserve existing canonical entries"

    def test_06_working_days_configuration_persists(self, admin_token):
        """Working days configuration (MON_SAT vs MON_FRI) persists across reloads and publication."""
        scope = TestCanonicalTimetableWorkflow.scope

        # Fetch published canonical timetable
        get_res = client.get(
            f"/timetable/canonical?academic_year_id={scope['academic_year_id']}&semester_id={scope['semester_id']}&department_id={scope['department_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert get_res.status_code == 200
        data = get_res.json()
        assert len(data) >= 1
        assert data[0]["working_days"] in ("MON_SAT", "MON_FRI")
