import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.identity import User
from backend.models.academic import Student, Department, Program, Semester, Section, Batch
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
def test_student():
    db = TestingSessionLocal()
    # ensure dependencies
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
    sem = db.query(Semester).first()
    if not sem:
        sem = Semester(academic_year_id=dept.id, semester_number=1, start_date="2025-08-01", end_date="2025-12-15")
        db.add(sem)
        db.commit()
        db.refresh(sem)
    sec = db.query(Section).first()
    if not sec:
        sec = Section(department_id=dept.id, program_id=prog.id, semester_id=sem.id, section_name="A", student_count=40)
        db.add(sec)
        db.commit()
        db.refresh(sec)
    batch = db.query(Batch).first()
    if not batch:
        batch = Batch(section_id=sec.id, batch_name="B1", student_count=20)
        db.add(batch)
        db.commit()
        db.refresh(batch)
    # create a user for the student
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("Test@1234")
    user = User(name="Test Student", email="student@test.edu", password_hash=hashed, role="STUDENT", department_id=dept.id, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    stu = Student(user_id=user.id, student_id="STU001", department_id=dept.id, program_id=prog.id, semester_id=sem.id, section_id=sec.id, batch_id=batch.id)
    db.add(stu)
    db.commit()
    db.refresh(stu)
    yield stu
    # cleanup
    db.query(Student).filter(Student.id == stu.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    db.query(Batch).filter(Batch.id == batch.id).delete()
    db.query(Section).filter(Section.id == sec.id).delete()
    db.query(Semester).filter(Semester.id == sem.id).delete()
    db.query(Program).filter(Program.id == prog.id).delete()
    db.query(Department).filter(Department.id == dept.id).delete()
    db.commit()
    db.close()

def test_create_student(test_student, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    # need to create a user first
    db = TestingSessionLocal()
    dept = db.query(Department).first()
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("Test@1234")
    user = User(name="New Student", email="newstudent@test.edu", password_hash=hashed, role="STUDENT", department_id=dept.id, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    response = client_raise.post(
        "/students/",
        json={
            "user_id": user.id,
            "student_id": "STU002",
            "department_id": dept.id,
            "program_id": dept.id,  # simplify
            "semester_id": dept.id,
            "section_id": dept.id,
            "batch_id": dept.id
        },
        headers=auth_headers
    )
    if response.status_code != 200:
        print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == "STU002"
    assert "id" in data

def test_get_student(test_student, auth_headers):
    response = client.get(
        f"/students/{test_student.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_student.id
    assert data["student_id"] == test_student.student_id
    assert data["department_id"] == test_student.department_id
    assert data["program_id"] == test_student.program_id
    assert data["semester_id"] == test_student.semester_id
    assert data["section_id"] == test_student.section_id
    assert data["batch_id"] == test_student.batch_id

def test_update_student(test_student, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        f"/students/{test_student.id}",
        json={
            "user_id": test_student.user_id,
            "student_id": "UPDSTU",
            "department_id": test_student.department_id,
            "program_id": test_student.program_id,
            "semester_id": test_student.semester_id,
            "section_id": test_student.section_id,
            "batch_id": test_student.batch_id
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == "UPDSTU"

def test_delete_student(test_student, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.delete(
        f"/students/{test_student.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/students/{test_student.id}",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_unauthorized_access():
    response = client.get("/students/")
    assert response.status_code == 401