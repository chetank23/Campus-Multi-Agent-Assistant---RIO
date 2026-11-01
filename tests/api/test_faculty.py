import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.identity import User
from backend.models.academic import Faculty, Department
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
def test_faculty():
    db = TestingSessionLocal()
    
    # ensure department
    dept = db.query(Department).filter(Department.department_code == "TEST_FAC_DEPT").first()
    if not dept:
        dept = Department(department_code="TEST_FAC_DEPT", name="Test Faculty Department")
        db.add(dept)
        db.commit()
        db.refresh(dept)
        
    # ensure no conflict for faculty_id
    existing_fac = db.query(Faculty).filter(Faculty.faculty_id == "FAC001").first()
    if existing_fac:
        db.delete(existing_fac)
        db.commit()

    # create a user for the faculty
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("Test@1234")
    
    # ensure no conflict for user email
    user = db.query(User).filter(User.email == "faculty@test.edu").first()
    if user:
        db.delete(user)
        db.commit()
        
    user = User(name="Test Faculty User", email="faculty@test.edu", password_hash=hashed, role="FACULTY", department_id=dept.id, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    fac = Faculty(user_id=user.id, faculty_id="FAC001", department_id=dept.id, designation="Professor", max_weekly_load=16)
    db.add(fac)
    db.commit()
    db.refresh(fac)
    
    yield fac
    
    # cleanup
    db = TestingSessionLocal()
    db.query(Faculty).filter(Faculty.id == fac.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    # we don't delete the department to avoid cascading FK violations if other tests created users linked to it
    db.commit()
    db.close()

def test_create_faculty(test_faculty, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    db = TestingSessionLocal()
    dept = db.query(Department).filter(Department.department_code == "TEST_FAC_DEPT").first()
    assert dept is not None
    dept_id = dept.id
    
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("Test@1234")
    
    existing_fac2 = db.query(Faculty).filter(Faculty.faculty_id == "FAC002").first()
    if existing_fac2:
        db.delete(existing_fac2)
        db.commit()
        
    # ensure no conflict for new user email
    user = db.query(User).filter(User.email == "newfaculty@test.edu").first()
    if user:
        db.delete(user)
        db.commit()
        
    user = User(name="New Faculty", email="newfaculty@test.edu", password_hash=hashed, role="FACULTY", department_id=dept_id, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    
    response = client_raise.post(
        "/faculty/",
        json={
            "user_id": user_id,
            "faculty_id": "FAC002",
            "department_id": dept_id,
            "designation": "Assistant Professor"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["faculty_id"] == "FAC002"
    assert "id" in data
    
    # Clean up the created faculty to avoid side effects
    db = TestingSessionLocal()
    db.query(Faculty).filter(Faculty.faculty_id == "FAC002").delete()
    db.query(User).filter(User.email == "newfaculty@test.edu").delete()
    db.commit()
    db.close()

def test_get_faculty(test_faculty, auth_headers):
    response = client.get(
        f"/faculty/{test_faculty.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_faculty.id
    assert data["faculty_id"] == test_faculty.faculty_id
    assert data["department_id"] == test_faculty.department_id

def test_update_faculty(test_faculty, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        f"/faculty/{test_faculty.id}",
        json={
            "user_id": test_faculty.user_id,
            "faculty_id": "UPDFAC",
            "department_id": test_faculty.department_id,
            "designation": "Associate Professor"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["faculty_id"] == "UPDFAC"

def test_delete_faculty(test_faculty, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.delete(
        f"/faculty/{test_faculty.id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/faculty/{test_faculty.id}",
        headers=auth_headers
    )
    assert response.status_code == 404

def test_unauthorized_access():
    response = client.get("/faculty/")
    assert response.status_code == 401


def test_update_unknown_faculty_returns_404(auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.put(
        "/faculty/999999",
        json={"faculty_id": "UNKNOWN", "designation": "Professor"},
        headers=auth_headers
    )
    assert response.status_code == 404
    assert "Faculty not found" in response.json()["detail"]
