import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.academic import Program, Department
from backend.models.identity import User
from dotenv import load_dotenv
load_dotenv(".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/campus_ai")

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
def test_program():
    db = TestingSessionLocal()
    # Ensure a department exists
    dept = db.query(Department).first()
    if not dept:
        dept = Department(department_code="TESTD", name="Test Department")
        db.add(dept)
        db.commit()
        db.refresh(dept)
    prog = Program(department_id=dept.id, program_name="Test Program", degree="B.Tech", duration=4)
    db.add(prog)
    db.commit()
    db.refresh(prog)
    yield prog
    db.query(Program).filter(Program.id == prog.id).delete()
    db.commit()
    db.close()

def test_create_program(test_program, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.post(
        "/programs/",
        json={
            "department_id": test_program.department_id,  # use same dept as fixture
            "program_name": "Test Program 2",
            "degree": "M.Tech",
            "duration": 2
        },
        headers=auth_headers
    )
    if response.status_code != 200:
        print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["program_name"] == "Test Program 2"
    assert data["degree"] == "M.Tech"
    assert data["duration"] == 2
    assert "id" in data

def test_get_program(test_program, auth_headers):
    response = client.get(
        f"/programs/{test_program.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_program.id
    assert data["program_name"] == test_program.program_name
    assert data["degree"] == test_program.degree
    assert data["duration"] == test_program.duration

def test_update_program(test_program, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        f"/programs/{test_program.id}",
        json={
            "department_id": test_program.department_id,
            "program_name": "Updated Program",
            "degree": "PhD",
            "duration": 5
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["program_name"] == "Updated Program"
    assert data["degree"] == "PhD"
    assert data["duration"] == 5

def test_delete_program(test_program, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.delete(
        f"/programs/{test_program.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/programs/{test_program.id}",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_unauthorized_access():
    response = client.get("/programs/")
    assert response.status_code == 401