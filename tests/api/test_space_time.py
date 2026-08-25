import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import get_db
from backend.models.space_time import TimeSlot, FacultyAvailability, AcademicCalendar
from backend.models.academic import Faculty, Department, AcademicYear
from backend.models.identity import User
from sqlalchemy import text, create_engine
from dotenv import load_dotenv
import os
import datetime
from sqlalchemy.orm import sessionmaker

load_dotenv(".env")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://campus_user:campus_password@localhost/campus_ai")
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
        result = conn.execute(text("SELECT email FROM users WHERE role = 'ADMIN' LIMIT 1")).fetchone()
        if not result:
            raise Exception("No admin user found")
        email = result[0]
    login_data = {"email": email, "password": "Test@1234"}
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    return token

@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture
def space_time_data():
    db = TestingSessionLocal()
    
    # Pre-cleanup
    db.query(FacultyAvailability).filter(FacultyAvailability.availability == "AVAILABLE").delete(synchronize_session=False)
    db.query(TimeSlot).filter(TimeSlot.day == "MONDAY").delete(synchronize_session=False)
    db.query(AcademicCalendar).filter(AcademicCalendar.event_type == "EVENT").delete(synchronize_session=False)
    db.query(Faculty).filter(Faculty.faculty_id == "SFAC001").delete(synchronize_session=False)
    db.query(User).filter(User.email == "st_faculty@test.com").delete(synchronize_session=False)
    db.query(Department).filter(Department.department_code == "ST_DPT").delete(synchronize_session=False)
    db.query(AcademicYear).filter(AcademicYear.name == "ST2026").delete(synchronize_session=False)
    db.commit()

    dept = Department(department_code="ST_DPT", name="Space Time Dept")
    db.add(dept)
    db.commit()
    db.refresh(dept)
    
    ay = AcademicYear(name="ST2026", start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 31))
    db.add(ay)
    db.commit()
    db.refresh(ay)

    fac_user = User(name="Faculty User", email="st_faculty@test.com", password_hash="hash", role="FACULTY", department_id=dept.id)
    db.add(fac_user)
    db.commit()
    db.refresh(fac_user)

    fac = Faculty(user_id=fac_user.id, faculty_id="SFAC001", department_id=dept.id, designation="Professor")
    db.add(fac)
    db.commit()
    db.refresh(fac)
    
    ts = TimeSlot(day="MONDAY", start_time=datetime.time(9, 0), end_time=datetime.time(10, 0), slot_type="CLASS")
    db.add(ts)
    db.commit()
    db.refresh(ts)
    
    fa = FacultyAvailability(faculty_id=fac.id, slot_id=ts.id, availability="AVAILABLE")
    db.add(fa)
    db.commit()
    db.refresh(fa)
    
    ac = AcademicCalendar(academic_year_id=ay.id, date=datetime.date(2026, 5, 1), event_type="EVENT", description="Test Event")
    db.add(ac)
    db.commit()
    db.refresh(ac)

    data = {
        "dept_id": dept.id,
        "ay_id": ay.id,
        "fac_id": fac.id,
        "ts_id": ts.id,
        "fa_id": fa.id,
        "ac_id": ac.id,
        "user_id": fac_user.id
    }
    db.close()
    
    yield data
    
    db = TestingSessionLocal()
    db.query(FacultyAvailability).filter(FacultyAvailability.faculty_id == data["fac_id"]).delete(synchronize_session=False)
    db.query(TimeSlot).filter(TimeSlot.day == "MONDAY").delete(synchronize_session=False)
    db.query(AcademicCalendar).filter(AcademicCalendar.academic_year_id == data["ay_id"]).delete(synchronize_session=False)
    db.query(Faculty).filter(Faculty.id == data["fac_id"]).delete(synchronize_session=False)
    db.query(User).filter(User.id == data["user_id"]).delete(synchronize_session=False)
    db.query(Department).filter(Department.id == data["dept_id"]).delete(synchronize_session=False)
    db.query(AcademicYear).filter(AcademicYear.id == data["ay_id"]).delete(synchronize_session=False)
    db.commit()
    db.close()

def test_create_time_slot(space_time_data, auth_headers):
    response = client.post(
        "/time-slots/",
        json={
            "day": "MONDAY",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "slot_type": "CLASS"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["day"] == "MONDAY"
    assert data["start_time"] == "10:00:00"

    db = TestingSessionLocal()
    db.query(TimeSlot).filter(TimeSlot.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_time_slot(space_time_data, auth_headers):
    response = client.get(f"/time-slots/{space_time_data['ts_id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["day"] == "MONDAY"

def test_update_time_slot(space_time_data, auth_headers):
    response = client.put(
        f"/time-slots/{space_time_data['ts_id']}",
        json={"slot_type": "BREAK"},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["slot_type"] == "BREAK"

def test_delete_time_slot(space_time_data, auth_headers):
    response = client.post(
        "/time-slots/",
        json={"day": "MONDAY", "start_time": "11:00:00", "end_time": "12:00:00", "slot_type": "BREAK"},
        headers=auth_headers
    )
    new_id = response.json()["id"]
    response = client.delete(f"/time-slots/{new_id}", headers=auth_headers)
    assert response.status_code == 200

def test_create_faculty_availability(space_time_data, auth_headers):
    response = client.post(
        "/faculty-availability/",
        json={
            "faculty_id": space_time_data["fac_id"],
            "slot_id": space_time_data["ts_id"],
            "availability": "UNAVAILABLE"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["availability"] == "UNAVAILABLE"

    db = TestingSessionLocal()
    db.query(FacultyAvailability).filter(FacultyAvailability.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_faculty_availability(space_time_data, auth_headers):
    response = client.get(f"/faculty-availability/{space_time_data['fa_id']}", headers=auth_headers)
    assert response.status_code == 200

def test_update_faculty_availability(space_time_data, auth_headers):
    response = client.put(
        f"/faculty-availability/{space_time_data['fa_id']}",
        json={"availability": "PREFERRED"},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["availability"] == "PREFERRED"

def test_delete_faculty_availability(space_time_data, auth_headers):
    response = client.post(
        "/faculty-availability/",
        json={"faculty_id": space_time_data["fac_id"], "slot_id": space_time_data["ts_id"], "availability": "AVAILABLE"},
        headers=auth_headers
    )
    new_id = response.json()["id"]
    response = client.delete(f"/faculty-availability/{new_id}", headers=auth_headers)
    assert response.status_code == 200

def test_create_academic_calendar(space_time_data, auth_headers):
    response = client.post(
        "/academic-calendar/",
        json={
            "academic_year_id": space_time_data["ay_id"],
            "date": "2026-06-01",
            "event_type": "HOLIDAY",
            "description": "Summer Break"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["event_type"] == "HOLIDAY"

    db = TestingSessionLocal()
    db.query(AcademicCalendar).filter(AcademicCalendar.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_academic_calendar(space_time_data, auth_headers):
    response = client.get(f"/academic-calendar/{space_time_data['ac_id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["event_type"] == "EVENT"

def test_update_academic_calendar(space_time_data, auth_headers):
    response = client.put(
        f"/academic-calendar/{space_time_data['ac_id']}",
        json={"event_type": "VACATION"},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["event_type"] == "VACATION"

def test_delete_academic_calendar(space_time_data, auth_headers):
    response = client.post(
        "/academic-calendar/",
        json={"academic_year_id": space_time_data["ay_id"], "date": "2026-07-01", "event_type": "EVENT"},
        headers=auth_headers
    )
    new_id = response.json()["id"]
    response = client.delete(f"/academic-calendar/{new_id}", headers=auth_headers)
    assert response.status_code == 200
