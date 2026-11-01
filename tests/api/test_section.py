import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.academic import Section, Department, Program, Semester, AcademicYear
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
def test_section():
    db = TestingSessionLocal()
    # ensure department, program, semester exist
    dept = db.query(Department).first()
    if not dept:
        dept = Department(department_code="TESTD", name="Test Department")
        db.add(dept)
        db.commit()
        db.refresh(dept)
    prog = db.query(Program).first()
    if not prog:
        prog = Program(department_id=dept.id, program_name="Test Program", degree="B.Tech", duration=4)
        db.add(prog)
        db.commit()
        db.refresh(prog)
    ay = db.query(AcademicYear).first()
    if not ay:
        ay = AcademicYear(name="2025-2026", start_date="2025-08-01", end_date="2026-05-31")
        db.add(ay)
        db.commit()
        db.refresh(ay)
    sem = db.query(Semester).first()
    if not sem:
        sem = Semester(academic_year_id=ay.id, semester_number=1, start_date="2025-08-01", end_date="2025-12-15")
        db.add(sem)
        db.commit()
        db.refresh(sem)
    sec = Section(department_id=dept.id, program_id=prog.id, semester_id=sem.id, section_name="A", student_count=40)
    db.add(sec)
    db.commit()
    db.refresh(sec)
    yield sec
    db.query(Section).filter(Section.id == sec.id).delete()
    db.commit()
    db.close()

def test_create_section(test_section, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    # need valid foreign keys
    db = TestingSessionLocal()
    dept = db.query(Department).first()
    prog = db.query(Program).first()
    sem = db.query(Semester).first()
    db.close()
    assert dept is not None
    assert prog is not None
    assert sem is not None
    response = client_raise.post(
        "/sections/",
        json={
            "department_id": dept.id,
            "program_id": prog.id,
            "semester_id": sem.id,
            "section_name": "B",
            "student_count": 45
        },
        headers=auth_headers
    )
    if response.status_code != 200:
        print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["section_name"] == "B"
    assert data["student_count"] == 45
    assert "id" in data

def test_get_section(test_section, auth_headers):
    response = client.get(
        f"/sections/{test_section.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_section.id
    assert data["department_id"] == test_section.department_id
    assert data["program_id"] == test_section.program_id
    assert data["semester_id"] == test_section.semester_id
    assert data["section_name"] == test_section.section_name
    assert data["student_count"] == test_section.student_count

def test_update_section(test_section, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        f"/sections/{test_section.id}",
        json={
            "department_id": test_section.department_id,
            "program_id": test_section.program_id,
            "semester_id": test_section.semester_id,
            "section_name": "UpdSec",
            "student_count": 50
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["section_name"] == "UpdSec"
    assert data["student_count"] == 50

def test_delete_section(test_section, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.delete(
        f"/sections/{test_section.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/sections/{test_section.id}",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_unauthorized_access():
    response = client.get("/sections/")
    assert response.status_code == 401