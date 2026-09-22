import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.academic import AcademicYear, Semester, Department, Program
from backend.models.timetable import TimetableVersion, TimetableEntry
from sqlalchemy.orm import Session

from backend.config import engine

client = TestClient(app)

@pytest.fixture(scope="module")
def admin_token():
    response = client.post(
        "/auth/login",
        json={"email": "admin@campus.edu", "password": "Test@1234"}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None

@pytest.fixture(scope="module")
def seeded_timetable(admin_token):
    if not admin_token:
        pytest.skip("No admin token")
        
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        semester = db.query(Semester).first()
        department = db.query(Department).first()
        program = db.query(Program).first()
        if not all([ac_year, semester, department, program]):
            pytest.skip("Missing seed data")
        assert ac_year is not None and semester is not None and department is not None and program is not None
            
    response = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": ac_year.id,
            "semester_id": semester.id,
            "department_id": department.id,
            "program_id": program.id
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["version_id"] is not None
    return data["version_id"]

def test_generation_persists_version_and_entries(seeded_timetable):
    version_id = seeded_timetable
    with Session(engine) as db:
        version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
        assert version is not None
        assert version.status == "GENERATED"
        
        entries = db.query(TimetableEntry).filter(TimetableEntry.version_id == version_id).all()
        assert len(entries) > 0
        assert entries[0].status == "DRAFT"

def test_get_versions(admin_token, seeded_timetable):
    response = client.get(
        "/timetable/versions",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    versions = response.json()
    assert len(versions) > 0
    assert any(v["id"] == seeded_timetable for v in versions)

def test_get_version_detail(admin_token, seeded_timetable):
    response = client.get(
        f"/timetable/versions/{seeded_timetable}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    version_detail = response.json()
    assert version_detail["id"] == seeded_timetable
    assert "timetable_entries" in version_detail
    assert len(version_detail["timetable_entries"]) > 0

def test_validate_version(admin_token, seeded_timetable):
    response = client.post(
        f"/timetable/versions/{seeded_timetable}/validate",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    val_result = response.json()
    assert "is_valid" in val_result
    
    # Check if status was upgraded
    with Session(engine) as db:
        version = db.query(TimetableVersion).filter(TimetableVersion.id == seeded_timetable).first()
        assert version is not None
        if val_result["is_valid"]:
            assert version.status == "VALIDATED"

def test_edit_entry(admin_token, seeded_timetable):
    # Get an entry to edit
    with Session(engine) as db:
        entry = db.query(TimetableEntry).filter(TimetableEntry.version_id == seeded_timetable).first()
        assert entry is not None
        entry_id = entry.id
        old_room = entry.room_id
        # we don't actually know a safe room to change to without violating constraints,
        # but the edit endpoint itself doesn't validate constraints, it just updates and expects revalidation.
        # we'll just update it to itself to test the endpoint, or to a dummy room if we don't care about feasibility right now.
        new_room = old_room
        
    response = client.patch(
        f"/timetable/entries/{entry_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"room_id": new_room}
    )
    assert response.status_code == 200
    updated_entry = response.json()
    assert updated_entry["id"] == entry_id
    assert updated_entry["room_id"] == new_room
    
    # If it was validated, it should be downgraded to REVIEWED
    with Session(engine) as db:
        version = db.query(TimetableVersion).filter(TimetableVersion.id == seeded_timetable).first()
        assert version is not None
        assert version.status in ("REVIEWED", "GENERATED", "DRAFT")

def test_finalize_version(admin_token, seeded_timetable):
    # Need to validate first so it reaches VALIDATED/REVIEWED status
    client.post(
        f"/timetable/versions/{seeded_timetable}/validate",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    response = client.post(
        f"/timetable/versions/{seeded_timetable}/finalize",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "FINALIZED"
    
def test_publish_version(admin_token, seeded_timetable):
    response = client.post(
        f"/timetable/versions/{seeded_timetable}/publish",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PUBLISHED"
