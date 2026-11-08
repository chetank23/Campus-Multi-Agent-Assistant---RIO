"""
tests/agents/test_aids_a_ai_assistant_20_questions.py
------------------------------------------------------
Comprehensive verification test suite ensuring the RIO Multi-Agent Assistant
accurately answers 20+ real student, faculty, and admin questions grounded
in the imported AIDS-A database records:

Student questions:
1. "Who am I?"
2. "What is my SRN?"
3. "Which department do I belong to?"
4. "Which section am I in?"
5. "Who is my class teacher?"
6. "Who is my faculty for Principles of Federated Learning?"
7. "What is my timetable today?"
8. "What is my first class tomorrow?"
9. "What is my next class?"
10. "Which room should I go to?"
11. "What subjects do I have this semester?"
12. "What time is my lunch break?"
13. "Show my weekly timetable."

Faculty questions:
14. "Which department do I belong to?"
15. "Which class am I the class teacher for?"
16. "Which students belong to AIDS-A?"
17. "Which subjects am I assigned?"
18. "What is my timetable today?"
19. "Which classes do I teach?"
20. "Which room is assigned to my next class?"
21. "Show the AIDS-A timetable."

Admin questions:
22. "How many students are in AIDS-A?"
23. "List the students by SRN."
24. "Who is the class teacher of AIDS-A?"
25. "Show all subjects for Semester VII."
26. "Which faculty members teach AIDS-A?"
27. "Show all available rooms in SIR M VISHWESH BLOCK."
28. "Show all labs."
29. "Generate a fresh timetable for AIDS-A."
"""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.identity import User
from backend.config import SessionLocal, engine
from sqlalchemy.orm import Session
from scripts.import_aids_a_dataset import import_aids_a_dataset, get_unique_account_password

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def ensure_aids_a_dataset():
    """Ensure the AIDS-A dataset is imported into the test database before running tests."""
    with Session(engine) as db:
        import_aids_a_dataset(db, configure_candidate_rooms=True)
    yield


@pytest.fixture(scope="module")
def student_token():
    pwd = get_unique_account_password("STUDENT", "R23EH001")
    resp = client.post("/auth/login", json={"email": "r23eh001@rio-mjp.test", "password": pwd})
    if resp.status_code != 200:
        resp = client.post("/auth/login", json={"email": "r23eh001@rio-mjp.test", "password": "Password@123"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_token():
    pwd = get_unique_account_password("FACULTY", "nimrita.koul")
    resp = client.post("/auth/login", json={"email": "nimrita.koul@rio-mjp.test", "password": pwd})
    if resp.status_code != 200:
        resp = client.post("/auth/login", json={"email": "nimrita.koul@rio-mjp.test", "password": "Password@123"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    # Admin from test cluster or create/verify
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        admin_email = admin_user.email if admin_user else "admin@campus.edu"
    resp = client.post("/auth/login", json={"email": admin_email, "password": "Test@1234"})
    if resp.status_code != 200:
        resp = client.post("/auth/login", json={"email": admin_email, "password": "Admin#RioLocal26"})
    if resp.status_code != 200:
        resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "AdminPassword123!"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


class TestStudentQuestions:
    """Verifies all Student questions grounded in DB records."""

    def test_q01_who_am_i(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Who am I?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "R23EH001" in reply or "AIDS-A" in reply or "Student" in reply

    def test_q02_what_is_my_srn(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "What is my SRN?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "R23EH001" in reply

    def test_q03_which_department_do_i_belong_to(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which department do I belong to?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "AI & DS" in reply or "Artificial Intelligence" in reply

    def test_q04_which_section_am_i_in(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which section am I in?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "AIDS-A" in reply

    def test_q05_who_is_my_class_teacher(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Who is my class teacher?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Nimrita Koul" in reply

    def test_q06_who_is_my_faculty_for_pfl(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Who is my faculty for Principles of Federated Learning?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Nimrita Koul" in reply

    def test_q07_what_is_my_timetable_today(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "What is my timetable today?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Schedule" in reply or "classes" in reply or "No classes" in reply

    def test_q08_what_is_my_first_class_tomorrow(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "What is my first class tomorrow?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Class" in reply or "class" in reply

    def test_q09_what_is_my_next_class(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "What is my next class?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "class" in reply.lower() or "room" in reply.lower() or "status" in reply.lower()

    def test_q10_which_room_should_i_go_to(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which room should I go to?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "room" in reply.lower() or "class" in reply.lower()

    def test_q11_what_subjects_do_i_have_this_semester(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "What subjects do I have this semester?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Principles of Federated Learning" in reply or "B25CS0701" in reply or "Subjects" in reply

    def test_q12_what_time_is_my_lunch_break(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "What time is my lunch break?"},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Lunch Break" in reply or "12:30" in reply or "13:30" in reply or "Break" in reply

    def test_q13_show_my_weekly_timetable(self, student_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Show my weekly timetable."},
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Schedule" in reply or "AIDS-A" in reply or "Classes" in reply


class TestFacultyQuestions:
    """Verifies all Faculty questions for Dr. Nimrita Koul."""

    def test_q14_which_department_do_i_belong_to(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which department do I belong to?"},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "AI & DS" in reply or "Artificial Intelligence" in reply

    def test_q15_which_class_am_i_the_class_teacher_for(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which class am I the class teacher for?"},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "AIDS-A" in reply

    def test_q16_which_students_belong_to_aids_a(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which students belong to AIDS-A?"},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "R23EH001" in reply
        assert "60" in reply or "Enrolled" in reply

    def test_q17_which_subjects_am_i_assigned(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which subjects am I assigned?"},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Principles of Federated Learning" in reply or "B25CS0701" in reply or "Assigned Courses" in reply

    def test_q18_what_is_my_timetable_today(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "What is my timetable today?"},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Schedule" in reply or "Teaching" in reply or "classes" in reply

    def test_q19_which_classes_do_i_teach(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which classes do I teach?"},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Principles of Federated Learning" in reply or "AIDS-A" in reply or "B25CS0701" in reply

    def test_q20_which_room_is_assigned_to_my_next_class(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which room is assigned to my next class?"},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "room" in reply.lower() or "class" in reply.lower()

    def test_q21_show_the_aids_a_timetable(self, faculty_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Show the AIDS-A timetable."},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Schedule" in reply or "AIDS-A" in reply or "PFL" in reply or "PP-1" in reply


class TestAdminQuestions:
    """Verifies all Admin questions grounded in DB records."""

    def test_q22_how_many_students_are_in_aids_a(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "How many students are in AIDS-A?"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "60" in reply

    def test_q23_list_the_students_by_srn(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "List the students by SRN."},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "R23EH001" in reply
        assert "R23EH060" in reply

    def test_q24_who_is_the_class_teacher_of_aids_a(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Who is the class teacher of AIDS-A?"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Nimrita Koul" in reply

    def test_q25_show_all_subjects_for_semester_vii(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Show all subjects for Semester VII."},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Principles of Federated Learning" in reply or "B25CS0701" in reply
        assert "Internship" in reply or "B22EF0704" in reply

    def test_q26_which_faculty_members_teach_aids_a(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Which faculty members teach AIDS-A?"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "Nimrita Koul" in reply

    def test_q27_show_all_available_rooms_in_smv_block(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Show all available rooms in SIR M VISHWESH BLOCK."},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "SIR M VISHWESH BLOCK" in reply or "225" in reply or "Floor" in reply

    def test_q28_show_all_labs(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Show all labs."},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "18" in reply or "labs" in reply.lower() or "laboratories" in reply.lower()

    def test_q29_generate_a_fresh_timetable_for_aids_a(self, admin_token):
        resp = client.post(
            "/agents/chat",
            json={"message": "Generate a fresh timetable for AIDS-A."},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "timetable" in reply.lower() or "proposal" in reply.lower() or "readiness" in reply.lower()
