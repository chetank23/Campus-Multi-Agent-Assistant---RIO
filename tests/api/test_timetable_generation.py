import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Batch, Faculty
from backend.models.courses import Course, CourseAssignment, ElectiveGroup, ElectiveGroupCourse
from backend.models.space_time import Room, Lab, TimeSlot, FacultyAvailability, AcademicCalendar, Building
from sqlalchemy.orm import Session
from datetime import time, date

from backend.config import engine

client = TestClient(app)

@pytest.fixture(scope="module")
def admin_token():
    # This assumes there's an admin user in the db, we login and get token
    response = client.post(
        "/auth/login",
        json={"email": "admin@campus.edu", "password": "Test@1234"}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None

def test_generate_timetable_valid_scope(admin_token):
    if not admin_token:
        pytest.skip("No admin token")
    
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        semester = db.query(Semester).first()
        department = db.query(Department).first()
        program = db.query(Program).first()
        
        if not all([ac_year, semester, department, program]):
            pytest.skip("Missing seed data")

    response = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": ac_year.id,
            "semester_id": semester.id,
            "department_id": department.id,
            "program_id": program.id
        }
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] in ["OPTIMAL", "FEASIBLE"]
    assert data["loaded_sections"] > 0
    assert data["loaded_courses"] >= 0

def test_generate_timetable_invalid_academic_year(admin_token):
    if not admin_token:
        pytest.skip("No admin token")
        
    response = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": 9999,
            "semester_id": 1,
            "department_id": 1,
            "program_id": 1
        }
    )
    assert response.status_code == 400
    assert "Academic year not found" in response.text

def test_generate_timetable_invalid_semester(admin_token):
    if not admin_token:
        pytest.skip("No admin token")
    
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        if not ac_year:
            pytest.skip("Missing seed data")
            
    response = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": ac_year.id,
            "semester_id": 9999,
            "department_id": 1,
            "program_id": 1
        }
    )
    assert response.status_code == 400
    assert "Semester not found or does not belong to the academic year" in response.text

def test_generate_timetable_invalid_sections(admin_token):
    if not admin_token:
        pytest.skip("No admin token")
    
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        semester = db.query(Semester).first()
        department = db.query(Department).first()
        program = db.query(Program).first()

    response = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": ac_year.id,
            "semester_id": semester.id,
            "department_id": department.id,
            "program_id": program.id,
            "section_ids": [999999]
        }
    )
    assert response.status_code == 400
    assert "Invalid section IDs" in response.text or "No valid sections found" in response.text

from unittest.mock import patch

def test_generate_timetable_infeasible(admin_token):
    if not admin_token:
        pytest.skip("No admin token")
    
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        semester = db.query(Semester).first()
        department = db.query(Department).first()
        program = db.query(Program).first()
        if not all([ac_year, semester, department, program]):
            pytest.skip("Missing seed data")

    with patch('backend.routes.timetable.TimetableSolver.solve') as mock_solve:
        from backend.optimizer.timetable_solver import SolverResult
        mock_solve.return_value = SolverResult(
            feasible=False,
            status="INFEASIBLE",
            message="No feasible timetable exists.",
            diagnostics=["Test diagnostic 1", "Test diagnostic 2"]
        )

        response = client.post(
            "/timetable/generate",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "academic_year_id": ac_year.id,
                "semester_id": semester.id,
                "department_id": department.id,
                "program_id": program.id
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "message" in data["detail"]
        assert "diagnostics" in data["detail"]
        assert "Test diagnostic 1" in data["detail"]["diagnostics"]
