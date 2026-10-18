"""
tests/agents/test_query_agent.py
--------------------------------
Integration tests for Query Agent:
- Tool execution against isolated test database
- Grounding in PostgreSQL records
- Empty results handling without invented records
- No arbitrary SQL vulnerability
"""

import pytest
from sqlalchemy.orm import Session
from backend.config import engine
from backend.models.identity import User
from agents.tools import execute_tool, QUERY_TOOL_DEFINITIONS
from agents.query_agent.agent import format_grounded_response, _extract_intent_and_tool_call


def test_tool_definitions_structure():
    assert len(QUERY_TOOL_DEFINITIONS) >= 6
    for tool in QUERY_TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert "allowed_roles" in tool
        assert isinstance(tool["allowed_roles"], list)


def test_query_course_details_grounding():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        res = execute_tool(
            tool_name="get_course_details",
            tool_args={"query_str": "CS"},
            user=user,
            db=db,
        )
        assert "results" in res
        # Must return real courses from seed Dataset A or clean message if none match
        if res["results"]:
            assert "code" in res["results"][0]
            assert "credits" in res["results"][0]
            assert "title" in res["results"][0]


def test_query_course_details_not_found():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        res = execute_tool(
            tool_name="get_course_details",
            tool_args={"query_str": "NON_EXISTENT_COURSE_XYZ_999"},
            user=user,
            db=db,
        )
        assert res["results"] == []
        assert "No course matching" in res["message"]

        # Formatter must report missing rather than hallucinate
        formatted, sources = format_grounded_response(
            tool_name="get_course_details",
            tool_args={"query_str": "NON_EXISTENT_COURSE_XYZ_999"},
            tool_result=res,
            user=user,
        )
        assert "No course" in formatted and "found" in formatted


def test_query_room_details():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        res = execute_tool(
            tool_name="get_room_or_lab_details",
            tool_args={"room_query": "1"},
            user=user,
            db=db,
        )
        assert "results" in res


def test_query_academic_calendar():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        res = execute_tool(
            tool_name="get_academic_calendar",
            tool_args={},
            user=user,
            db=db,
        )
        assert "events" in res or "message" in res


def test_query_campus_room_inventory():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "ADMIN").first()
        res = execute_tool(
            tool_name="get_campus_room_inventory",
            tool_args={},
            user=user,
            db=db,
        )
        assert "total_active_rooms" in res
        assert "breakdown" in res
        assert res["total_active_rooms"] >= 0



def test_no_arbitrary_sql_execution():
    """
    Ensures SQL injection payloads in tool args do not execute arbitrary SQL
    or compromise PostgreSQL query parameterization.
    """
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        malicious_input = "'; DROP TABLE users CASCADE; --"
        res = execute_tool(
            tool_name="get_course_details",
            tool_args={"query_str": malicious_input},
            user=user,
            db=db,
        )
        assert res["results"] == []

        # Verify users table is completely intact
        users_count = db.query(User).count()
        assert users_count > 0, "Users table was unexpectedly compromised!"
