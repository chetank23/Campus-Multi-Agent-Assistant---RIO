import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.academic import Batch, Section, Department, Program, Semester
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
def test_batch():
    db = TestingSessionLocal()
    # ensure section with dependencies
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
    batch = Batch(section_id=sec.id, batch_name="B1", student_count=20)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    yield batch
    db.query(Batch).filter(Batch.id == batch.id).delete()
    db.commit()
    db.close()

def test_create_batch(test_batch, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    # need valid foreign keys
    db = TestingSessionLocal()
    sec = db.query(Section).first()
    db.close()
    response = client_raise.post(
        "/batches/",
        json={
            "section_id": sec.id,
            "batch_name": "B2",
            "student_count": 25
        },
        headers=auth_headers
    )
    if response.status_code != 200:
        print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["batch_name"] == "B2"
    assert data["student_count"] == 25
    assert "id" in data

def test_get_batch(test_batch, auth_headers):
    response = client.get(
        f"/batches/{test_batch.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_batch.id
    assert data["section_id"] == test_batch.section_id
    assert data["batch_name"] == test_batch.batch_name
    assert data["student_count"] == test_batch.student_count

def test_update_batch(test_batch, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        f"/batches/{test_batch.id}",
        json={
            "section_id": test_batch.section_id,
            "batch_name": "UpdB",
            "student_count": 30
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["batch_name"] == "UpdB"
    assert data["student_count"] == 30

def test_delete_batch(test_batch, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.delete(
        f"/batches/{test_batch.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/batches/{test_batch.id}",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_unauthorized_access():
    response = client.get("/batches/")
    assert response.status_code == 401