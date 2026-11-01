import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.identity import User
from backend.models.academic import Department, Program, Semester, Section, Batch, Faculty
from backend.models.courses import Course, CourseAssignment, ElectiveGroup, ElectiveGroupCourse
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
def test_course_data():
    db = TestingSessionLocal()
    
    # Pre-cleanup to ensure no leftover state
    db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.course_id.in_(
        db.query(Course.id).filter(Course.course_code.like('CRS%'))
    )).delete(synchronize_session=False)
    db.query(CourseAssignment).filter(CourseAssignment.course_id.in_(
        db.query(Course.id).filter(Course.course_code.like('CRS%'))
    )).delete(synchronize_session=False)
    db.query(CourseAssignment).filter(CourseAssignment.section_id.in_(
        db.query(Section.id).filter(Section.section_name == 'Z99')
    )).delete(synchronize_session=False)
    db.query(CourseAssignment).filter(CourseAssignment.faculty_id.in_(
        db.query(Faculty.id).filter(Faculty.faculty_id == 'CFAC001')
    )).delete(synchronize_session=False)
    
    # Clean up ElectiveGroupCourse based on semester (since groups belong to semesters)
    db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.group_id.in_(
        db.query(ElectiveGroup.id).filter(ElectiveGroup.semester_id.in_(
            db.query(Semester.id).filter(Semester.semester_number == 99)
        ))
    )).delete(synchronize_session=False)
    
    db.query(ElectiveGroup).filter(ElectiveGroup.semester_id.in_(
        db.query(Semester.id).filter(Semester.semester_number == 99)
    )).delete(synchronize_session=False)
    
    db.query(Course).filter(Course.course_code.like('CRS%')).delete(synchronize_session=False)
    db.query(Faculty).filter(Faculty.faculty_id == "CFAC001").delete(synchronize_session=False)
    db.query(User).filter(User.email.like('%crs_faculty%')).delete(synchronize_session=False)
    db.query(Section).filter(Section.section_name == "Z99").delete(synchronize_session=False)
    db.query(Semester).filter(Semester.semester_number == 99).delete(synchronize_session=False)
    db.query(Department).filter(Department.department_code == "T_CRS_DPT").delete(synchronize_session=False)
    db.commit()

    # 1. Ensure Department
    dept = Department(department_code="T_CRS_DPT", name="Test Course Department")
    db.add(dept)
    db.commit()
    db.refresh(dept)
        
    # Ensure Semester
    sem = Semester(semester_number=99, start_date="2025-01-01", end_date="2025-06-01")
    db.add(sem)
    db.commit()
    db.refresh(sem)
        
    # Ensure Section
    sec = Section(department_id=dept.id, semester_id=sem.id, section_name="Z99", student_count=10)
    db.add(sec)
    db.commit()
    db.refresh(sec)
        
    # Ensure Faculty User
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("Test@1234")
    
    user = User(name="Course Faculty", email="crs_faculty@test.edu", password_hash=hashed, role="FACULTY", department_id=dept.id, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    fac = Faculty(user_id=user.id, faculty_id="CFAC001", department_id=dept.id, designation="Professor")
    db.add(fac)
    db.commit()
    db.refresh(fac)
    
    # Create base records to be yielded
    c = Course(course_code="CRS101", course_name="Test Course 1", department_id=dept.id, course_type="THEORY", credits=3)
    db.add(c)
    db.commit()
    db.refresh(c)
    
    ca = CourseAssignment(course_id=c.id, faculty_id=fac.id, section_id=sec.id)
    db.add(ca)
    db.commit()
    db.refresh(ca)
    
    eg = ElectiveGroup(name="Tech Elective I", semester_id=sem.id, department_id=dept.id)
    db.add(eg)
    db.commit()
    db.refresh(eg)
    
    egc = ElectiveGroupCourse(group_id=eg.id, course_id=c.id)
    db.add(egc)
    db.commit()
    db.refresh(egc)
    
    data = {
        "dept_id": dept.id,
        "fac_id": fac.id,
        "sec_id": sec.id,
        "sem_id": sem.id,
        "course_id": c.id,
        "assignment_id": ca.id,
        "group_id": eg.id,
        "egc_id": egc.id,
        "user_id": user.id
    }
    
    yield data
    
    # Cleanup
    db = TestingSessionLocal()
    db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.course_id.in_(
        db.query(Course.id).filter(Course.course_code.like('CRS%'))
    )).delete(synchronize_session=False)
    db.query(CourseAssignment).filter(CourseAssignment.course_id.in_(
        db.query(Course.id).filter(Course.course_code.like('CRS%'))
    )).delete(synchronize_session=False)
    db.query(CourseAssignment).filter(CourseAssignment.section_id.in_(
        db.query(Section.id).filter(Section.section_name == 'Z99')
    )).delete(synchronize_session=False)
    db.query(CourseAssignment).filter(CourseAssignment.faculty_id.in_(
        db.query(Faculty.id).filter(Faculty.faculty_id == 'CFAC001')
    )).delete(synchronize_session=False)
    
    db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.group_id.in_(
        db.query(ElectiveGroup.id).filter(ElectiveGroup.semester_id.in_(
            db.query(Semester.id).filter(Semester.semester_number == 99)
        ))
    )).delete(synchronize_session=False)
    
    db.query(ElectiveGroup).filter(ElectiveGroup.semester_id.in_(
        db.query(Semester.id).filter(Semester.semester_number == 99)
    )).delete(synchronize_session=False)
    
    db.query(Course).filter(Course.course_code.like('CRS%')).delete(synchronize_session=False)
    
    db.query(Faculty).filter(Faculty.id == data["fac_id"]).delete(synchronize_session=False)
    db.query(User).filter(User.id == data["user_id"]).delete(synchronize_session=False)
    db.query(Section).filter(Section.id == data["sec_id"]).delete(synchronize_session=False)
    db.query(Semester).filter(Semester.id == data["sem_id"]).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_create_course(test_course_data, auth_headers):
    client_raise = TestClient(app, raise_server_exceptions=True)
    db = TestingSessionLocal()
    existing_c = db.query(Course).filter(Course.course_code == "CRS102").first()
    if existing_c:
        db.delete(existing_c)
        db.commit()
    db.close()

    response = client_raise.post(
        "/courses/",
        json={
            "course_code": "CRS102",
            "course_name": "Test Course 2",
            "department_id": test_course_data["dept_id"],
            "course_type": "LAB"
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["course_code"] == "CRS102"
    
    # Clean up
    db = TestingSessionLocal()
    db.query(Course).filter(Course.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_course(test_course_data, auth_headers):
    response = client.get(
        f"/courses/{test_course_data['course_id']}",
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["course_code"] == "CRS101"

def test_update_course(test_course_data, auth_headers):
    response = client.put(
        f"/courses/{test_course_data['course_id']}",
        json={"course_name": "Updated Name"},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["course_name"] == "Updated Name"

def test_create_course_assignment(test_course_data, auth_headers):
    response = client.post(
        "/course-assignments/",
        json={
            "course_id": test_course_data["course_id"],
            "faculty_id": test_course_data["fac_id"],
            "section_id": test_course_data["sec_id"]
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["course_id"] == test_course_data["course_id"]
    
    db = TestingSessionLocal()
    db.query(CourseAssignment).filter(CourseAssignment.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_course_assignment(test_course_data, auth_headers):
    response = client.get(f"/course-assignments/{test_course_data['assignment_id']}", headers=auth_headers)
    assert response.status_code == 200

def test_update_course_assignment(test_course_data, auth_headers):
    response = client.put(
        f"/course-assignments/{test_course_data['assignment_id']}",
        json={"course_id": test_course_data["course_id"]}, # dummy update
        headers=auth_headers
    )
    assert response.status_code == 200

def test_delete_course_assignment(test_course_data, auth_headers):
    # Setup extra assignment for deletion to avoid breaking teardown
    response = client.post(
        "/course-assignments/",
        json={"course_id": test_course_data["course_id"], "faculty_id": test_course_data["fac_id"]},
        headers=auth_headers
    )
    new_ca_id = response.json()["id"]
    
    response = client.delete(f"/course-assignments/{new_ca_id}", headers=auth_headers)
    assert response.status_code == 200

def test_create_elective_group(test_course_data, auth_headers):
    response = client.post(
        "/elective-groups/",
        json={
            "name": "Elective II",
            "semester_id": test_course_data["sem_id"],
            "department_id": test_course_data["dept_id"]
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Elective II"
    
    db = TestingSessionLocal()
    db.query(ElectiveGroup).filter(ElectiveGroup.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_elective_group(test_course_data, auth_headers):
    response = client.get(f"/elective-groups/{test_course_data['group_id']}", headers=auth_headers)
    assert response.status_code == 200

def test_update_elective_group(test_course_data, auth_headers):
    response = client.put(
        f"/elective-groups/{test_course_data['group_id']}",
        json={"name": "Updated EG"},
        headers=auth_headers
    )
    assert response.status_code == 200

def test_delete_elective_group(test_course_data, auth_headers):
    response = client.post(
        "/elective-groups/",
        json={"name": "Temp EG", "semester_id": test_course_data["sem_id"], "department_id": test_course_data["dept_id"]},
        headers=auth_headers
    )
    new_id = response.json()["id"]
    response = client.delete(f"/elective-groups/{new_id}", headers=auth_headers)
    assert response.status_code == 200

def test_create_elective_group_course(test_course_data, auth_headers):
    response = client.post(
        "/elective-group-courses/",
        json={
            "group_id": test_course_data["group_id"],
            "course_id": test_course_data["course_id"]
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["group_id"] == test_course_data["group_id"]
    
    db = TestingSessionLocal()
    db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.id == data["id"]).delete()
    db.commit()
    db.close()

def test_get_elective_group_course(test_course_data, auth_headers):
    response = client.get(f"/elective-group-courses/{test_course_data['egc_id']}", headers=auth_headers)
    assert response.status_code == 200

def test_delete_elective_group_course(test_course_data, auth_headers):
    response = client.post(
        "/elective-group-courses/",
        json={"group_id": test_course_data["group_id"], "course_id": test_course_data["course_id"]},
        headers=auth_headers
    )
    new_id = response.json()["id"]
    response = client.delete(f"/elective-group-courses/{new_id}", headers=auth_headers)
    assert response.status_code == 200

def test_delete_course(test_course_data, auth_headers):
    response = client.post(
        "/courses/",
        json={"course_code": "CRS999", "course_name": "To Delete", "department_id": test_course_data["dept_id"], "course_type": "THEORY"},
        headers=auth_headers
    )
    new_id = response.json()["id"]
    response = client.delete(f"/courses/{new_id}", headers=auth_headers)
    assert response.status_code == 200
