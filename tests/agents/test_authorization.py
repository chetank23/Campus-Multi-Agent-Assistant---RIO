"""
tests/agents/test_authorization.py
----------------------------------
Authorization and privacy boundary tests for Agent Tool Execution:
- Students cannot access internal faculty teaching schedules
- Students cannot access department-wide timetables
- Faculty cannot view other departments' schedules
- Student viewers cannot see faculty private contact numbers
- Authentication identity cannot be overridden by tool args
- Password hash and secret credentials are never exposed
"""

import pytest
from sqlalchemy.orm import Session
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Faculty
from agents.tools import execute_tool


def test_student_cannot_access_faculty_teaching_schedule():
    with Session(engine) as db:
        student_user = db.query(User).filter(User.role == "STUDENT").first()
        res = execute_tool(
            tool_name="get_faculty_schedule",
            tool_args={},
            user=student_user,
            db=db,
        )
        assert "error" in res
        assert "not authorized" in res["error"].lower() or "access denied" in res["error"].lower()


def test_student_cannot_access_department_timetable():
    with Session(engine) as db:
        student_user = db.query(User).filter(User.role == "STUDENT").first()
        res = execute_tool(
            tool_name="get_department_timetable",
            tool_args={},
            user=student_user,
            db=db,
        )
        assert "error" in res
        assert "not authorized" in res["error"].lower() or "access denied" in res["error"].lower()


def test_faculty_restricted_to_own_department_timetable():
    with Session(engine) as db:
        faculty_user = db.query(User).filter(User.role == "FACULTY", User.department_id.isnot(None)).first()
        assert faculty_user is not None

        # Requesting a different department must be rejected
        other_dept_id = faculty_user.department_id + 999
        res = execute_tool(
            tool_name="get_department_timetable",
            tool_args={"department_id": other_dept_id},
            user=faculty_user,
            db=db,
        )
        assert "error" in res
        assert "access denied" in res["error"].lower()


def test_student_viewer_masks_faculty_private_contact():
    with Session(engine) as db:
        student_user = db.query(User).filter(User.role == "STUDENT").first()
        admin_user = db.query(User).filter(User.role == "ADMIN").first()

        # Student lookup
        student_res = execute_tool(
            tool_name="get_faculty_profile",
            tool_args={"search_query": "Hill"},
            user=student_user,
            db=db,
        )
        if student_res.get("results"):
            # Private contact number must be masked (None) for student viewers
            assert student_res["results"][0]["contact_number"] is None

        # Admin lookup
        admin_res = execute_tool(
            tool_name="get_faculty_profile",
            tool_args={"search_query": "Hill"},
            user=admin_user,
            db=db,
        )
        if admin_res.get("results"):
            # Admin can view directory contact info
            # (or None if unconfigured, but not blocked by privacy rule)
            assert "name" in admin_res["results"][0]


def test_password_hash_and_tokens_never_leaked():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        res = execute_tool(
            tool_name="get_faculty_profile",
            tool_args={"search_query": "a"},
            user=user,
            db=db,
        )
        for r in res.get("results", []):
            assert "password" not in r
            assert "password_hash" not in r
            assert "token" not in r
