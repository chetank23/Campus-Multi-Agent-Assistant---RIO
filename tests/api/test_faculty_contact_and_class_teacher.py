import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.identity import User
from backend.models.academic import Faculty, Department, Section, Program, AcademicYear, Semester
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
        result = conn.execute(text("SELECT email FROM users WHERE role = 'ADMIN' LIMIT 1")).fetchone()
        if not result:
            raise Exception("No admin user found")
        email = result[0]
    # Standard local admin login
    response = client.post("/auth/login", json={"email": email, "password": "TestPassword123!"})
    if response.status_code != 200:
        response = client.post("/auth/login", json={"email": email, "password": "Test@1234"})
    assert response.status_code == 200
    return response.json()["access_token"]

@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

def test_faculty_contact_number_field(auth_headers):
    db = TestingSessionLocal()
    dept = db.query(Department).first()
    user = db.query(User).filter(User.role == "FACULTY").first()
    assert dept is not None
    assert user is not None

    # Test creating faculty with contact_number
    fac_id = f"CT_FAC_{os.urandom(3).hex()}"
    fac = Faculty(
        user_id=user.id,
        faculty_id=fac_id,
        department_id=dept.id,
        designation="Assistant Professor",
        contact_number="+1-555-0199"
    )
    db.add(fac)
    db.commit()
    db.refresh(fac)

    res = client.get(f"/faculty/{fac.id}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["contact_number"] == "+1-555-0199"
    assert data["designation"] == "Assistant Professor"

    # Cleanup
    db.delete(fac)
    db.commit()
    db.close()

def test_section_class_teacher_assignment(auth_headers):
    db = TestingSessionLocal()
    dept = db.query(Department).first()
    assert dept is not None
    prog = db.query(Program).first()
    assert prog is not None
    sem = db.query(Semester).first()
    assert sem is not None
    fac = db.query(Faculty).filter(Faculty.department_id == dept.id).first()
    assert fac is not None

    # Create Section with class_teacher_id
    sec_data = {
        "department_id": dept.id,
        "program_id": prog.id,
        "semester_id": sem.id,
        "section_name": "CT_SEC",
        "student_count": 40,
        "class_teacher_id": fac.id
    }
    res = client.post("/sections/", json=sec_data, headers=auth_headers)
    assert res.status_code == 200
    sec = res.json()
    assert sec["class_teacher_id"] == fac.id
    assert sec["class_teacher"] is not None
    assert sec["class_teacher"]["id"] == fac.id

    # Test update to NULL
    sec_id = sec["id"]
    res_up = client.put(f"/sections/{sec_id}", json={"class_teacher_id": None}, headers=auth_headers)
    assert res_up.status_code == 200
    assert res_up.json()["class_teacher_id"] is None
    assert res_up.json()["class_teacher"] is None

    # Cleanup
    client.delete(f"/sections/{sec_id}", headers=auth_headers)
    db.close()
