import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.academic import AcademicYear
from backend.models.identity import User
from dotenv import load_dotenv
load_dotenv(".env")

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture
def admin_token():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT email, password_hash FROM users WHERE role = 'ADMIN' LIMIT 1")).fetchone()
        if not result:
            raise Exception("No admin user found")
        email, _ = result
    login_data = {"email": email, "password": "Test@1234"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    return token

@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture
def test_academic_year():
    db = TestingSessionLocal()
    # Clean up specific academic years to avoid foreign key violations
    from backend.models.space_time import AcademicCalendar
    from backend.models.academic import Semester
    from backend.models.courses import ElectiveGroup, ElectiveGroupCourse

    # Delete child objects referencing the years we are about to delete
    years_to_delete = db.query(AcademicYear.id).filter(AcademicYear.name.in_(["9998-9999", "9999-9999", "Updated Test Year"]))
    semesters_to_delete = db.query(Semester.id).filter(Semester.academic_year_id.in_(years_to_delete))
    groups_to_delete = db.query(ElectiveGroup.id).filter(ElectiveGroup.semester_id.in_(semesters_to_delete))

    db.query(AcademicCalendar).filter(AcademicCalendar.academic_year_id.in_(years_to_delete)).delete(synchronize_session=False)
    db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.group_id.in_(groups_to_delete)).delete(synchronize_session=False)
    db.query(ElectiveGroup).filter(ElectiveGroup.semester_id.in_(semesters_to_delete)).delete(synchronize_session=False)
    db.query(Semester).filter(Semester.academic_year_id.in_(years_to_delete)).delete(synchronize_session=False)
    db.query(AcademicYear).filter(AcademicYear.name.in_(["9998-9999", "9999-9999", "Updated Test Year"])).delete(synchronize_session=False)
    db.commit()
    yr = AcademicYear(name="9998-9999", start_date="9998-08-01", end_date="9999-05-31")
    db.add(yr)
    db.commit()
    db.refresh(yr)
    yield yr
    from backend.models.courses import ElectiveGroup, ElectiveGroupCourse
    semesters_to_delete = db.query(Semester.id).filter(Semester.academic_year_id == yr.id)
    groups_to_delete = db.query(ElectiveGroup.id).filter(ElectiveGroup.semester_id.in_(semesters_to_delete))
    db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.group_id.in_(groups_to_delete)).delete(synchronize_session=False)
    db.query(ElectiveGroup).filter(ElectiveGroup.semester_id.in_(semesters_to_delete)).delete(synchronize_session=False)
    db.query(Semester).filter(Semester.academic_year_id == yr.id).delete(synchronize_session=False)
    db.query(AcademicYear).filter(AcademicYear.id == yr.id).delete(synchronize_session=False)
    db.commit()
    db.close()

def test_create_academic_year(test_academic_year, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.post(
        "/academic-years/",
        json={
            "name": "9999-9999",
            "start_date": "9999-08-01",
            "end_date": "9999-05-31"
        },
        headers=auth_headers
    )
    if response.status_code != 200:
        print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "9999-9999"
    assert data["start_date"] == "9999-08-01"
    assert data["end_date"] == "9999-05-31"
    assert "id" in data
    
    # Post-cleanup
    db = TestingSessionLocal()
    db.query(AcademicYear).filter(AcademicYear.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_academic_year(test_academic_year, auth_headers):
    response = client.get(
        f"/academic-years/{test_academic_year.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_academic_year.id
    assert data["name"] == test_academic_year.name
    assert data["start_date"] == test_academic_year.start_date.isoformat()
    assert data["end_date"] == test_academic_year.end_date.isoformat()

def test_update_academic_year(test_academic_year, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        f"/academic-years/{test_academic_year.id}",
        json={
            "name": "Updated Test Year",
            "start_date": "9998-08-01",
            "end_date": "9999-05-31"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Test Year"
    assert data["start_date"] == "9998-08-01"
    assert data["end_date"] == "9999-05-31"

def test_delete_academic_year(test_academic_year, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.delete(
        f"/academic-years/{test_academic_year.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/academic-years/{test_academic_year.id}",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_unauthorized_access():
    response = client.get("/academic-years/")
    assert response.status_code == 401