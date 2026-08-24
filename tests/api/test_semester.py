import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.academic import Semester, AcademicYear
from backend.models.identity import User
from dotenv import load_dotenv
load_dotenv(".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/campus_ai")

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
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
def test_semester():
    db = TestingSessionLocal()
    # ensure an academic year exists
    ay = db.query(AcademicYear).first()
    if not ay:
        ay = AcademicYear(name="2025-2026", start_date="2025-08-01", end_date="2026-05-31")
        db.add(ay)
        db.commit()
        db.refresh(ay)
    sem = Semester(academic_year_id=ay.id, semester_number=1, start_date="2025-08-01", end_date="2025-12-15")
    db.add(sem)
    db.commit()
    db.refresh(sem)
    yield sem
    db.query(Semester).filter(Semester.id == sem.id).delete()
    db.commit()
    db.close()

def test_create_semester(test_semester, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    # get an academic year id from fixture
    db = TestingSessionLocal()
    ay = db.query(AcademicYear).first()
    db.close()
    response = client_raise.post(
        "/semesters/",
        json={
            "academic_year_id": ay.id,
            "semester_number": 2,
            "start_date": "2026-01-10",
            "end_date": "2026-05-31"
        },
        headers=auth_headers
    )
    if response.status_code != 200:
        print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["semester_number"] == 2
    assert data["start_date"] == "2026-01-10"
    assert data["end_date"] == "2026-05-31"
    assert "id" in data

def test_get_semester(test_semester, auth_headers):
    response = client.get(
        f"/semesters/{test_semester.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_semester.id
    assert data["academic_year_id"] == test_semester.academic_year_id
    assert data["semester_number"] == test_semester.semester_number
    assert data["start_date"] == test_semester.start_date.isoformat()
    assert data["end_date"] == test_semester.end_date.isoformat()

def test_update_semester(test_semester, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        f"/semesters/{test_semester.id}",
        json={
            "academic_year_id": test_semester.academic_year_id,
            "semester_number": 2,
            "start_date": "2026-01-10",
            "end_date": "2026-05-31"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["semester_number"] == 2
    assert data["start_date"] == "2026-01-10"
    assert data["end_date"] == "2026-05-31"

def test_delete_semester(test_semester, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.delete(
        f"/semesters/{test_semester.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/semesters/{test_semester.id}",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_unauthorized_access():
    response = client.get("/semesters/")
    assert response.status_code == 401