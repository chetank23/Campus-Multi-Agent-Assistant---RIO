"""
tests/agents/test_query_pipeline_remediation.py
-----------------------------------------------
Comprehensive targeted verification for the RIO-MJP Campus Assistant Query Pipeline:
1. Intent classification, typo normalization, and read-only vs mutation separation.
2. Tool registry uniqueness, schema completeness, and dispatcher error handling.
3. Date/time extraction (today, tomorrow, yesterday, weekdays, relative windows, 12h/24h).
4. Multi-turn faculty availability follow-ups (date, time, department, day switch).
5. NVIDIA Nemotron XML <tool_call> parsing and stripping.
6. End-to-end deterministic & API execution across Admin, Faculty, and Student roles.
"""

from __future__ import annotations

import datetime
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.main import app
from backend.models.identity import User
from agents.common.formatter import normalize_query_typos
from agents.common.context_resolver import extract_contextual_follow_up
from agents.llm.nvidia_provider import strip_thinking, _parse_text_tool_calls
from agents.resource_agent.parser import parse_date, parse_time_interval
from agents.supervisor.agent import classify_intent, execute_supervisor
from agents.tools import QUERY_TOOL_DEFINITIONS, execute_tool
from backend.routes.chat import determine_outcome_state

client = TestClient(app)


def _get_db() -> Session:
    eng = create_engine(os.environ["DATABASE_URL"])
    return Session(eng)


def test_intent_classification_and_typo_normalization():
    assert normalize_query_typos("palcement activitie") == "placement activities"
    assert normalize_query_typos("availble faculty") == "available faculty"
    assert normalize_query_typos("avalable rooms") == "available rooms"
    assert normalize_query_typos("faculity timetable") == "faculty timetable"

    read_only_queries = [
        "available faculties",
        "available faculty",
        "Which faculty are free tomorrow from 2 PM to 3 PM?",
        "Show faculty in AI and DS.",
        "Who teaches Artificial Intelligence?",
        "Show the department timetable.",
        "What courses are available?",
        "What are the upcoming placement activities?",
        "Which rooms are free tomorrow?",
        "Show the academic holidays.",
        "palcement activities",
        "availble faculty",
        "avalable rooms",
        "faculity timetable",
    ]
    for q in read_only_queries:
        assert classify_intent(q) == "QUERY_AGENT", f"Expected QUERY_AGENT for '{q}', got {classify_intent(q)}"

    # State-changing faculty availability must still route to TIMETABLE_GENERATION
    assert classify_intent("Mark Dr. Sharma unavailable on Monday afternoon") == "TIMETABLE_GENERATION"


def test_tool_registry_consistency_and_error_handling():
    names = [t["name"] for t in QUERY_TOOL_DEFINITIONS]
    assert len(names) == len(set(names)), "Duplicate tool names found in QUERY_TOOL_DEFINITIONS"

    for t in QUERY_TOOL_DEFINITIONS:
        assert "description" in t and t["description"]
        assert "parameters" in t and isinstance(t["parameters"], dict)
        assert "allowed_roles" in t and len(t["allowed_roles"]) >= 1

    with _get_db() as db:
        admin = db.query(User).filter(User.role == "ADMIN").first()
        assert admin is not None

        # Unknown tool must return explicit error, never silent success
        res_unknown = execute_tool("non_existent_tool_xyz", {}, admin, db)
        assert "error" in res_unknown

        # Missing required args for get_available_faculty must return structured error
        res_missing = execute_tool("get_available_faculty", {}, admin, db)
        assert "error" in res_missing
        assert "Missing required parameter" in res_missing["error"]


def test_date_and_time_extraction_variants():
    base = datetime.date(2026, 11, 25)
    assert parse_date("today", base_date=base) == datetime.date(2026, 11, 25)
    assert parse_date("tomorrow", base_date=base) == datetime.date(2026, 11, 26)
    assert parse_date("yesterday", base_date=base) == datetime.date(2026, 11, 24)
    assert parse_date("next Wednesday", base_date=base) == datetime.date(2026, 12, 2)

    assert parse_time_interval("2 PM to 3 PM") == (datetime.time(14, 0), datetime.time(15, 0))
    assert parse_time_interval("14:00 to 15:00") == (datetime.time(14, 0), datetime.time(15, 0))
    assert parse_time_interval("between 10 and 11 AM") == (datetime.time(10, 0), datetime.time(11, 0))
    assert parse_time_interval("tomorrow afternoon") == (datetime.time(13, 0), datetime.time(17, 0))
    assert parse_time_interval("tomorrow morning") == (datetime.time(9, 0), datetime.time(12, 0))

    st_now, et_now = parse_time_interval("right now")
    assert st_now is not None and et_now is not None


def test_nvidia_xml_tool_call_parsing_and_stripping():
    raw = (
        "<thought>Thinking...</thought>\n"
        "<tool_call>\n<function=search_faculty_directory>\n"
        "<parameter=department_name>AI & DS</parameter>\n"
        "</function>\n</tool_call>"
    )
    parsed = _parse_text_tool_calls(raw)
    assert parsed == [("search_faculty_directory", {"department_name": "AI & DS"})]
    assert strip_thinking(raw) == ""


def test_outcome_state_does_not_false_positive_on_valid_timetable():
    res_valid = {
        "success": True,
        "intent": "OPEN_ENDED_LLM_QUERY",
        "reply": "Department Timetable - AI & DS\nTotal Entries: 23\n| MON | 08:30 - 09:25 | ...",
    }
    assert determine_outcome_state(res_valid) == "GROUNDED_ANSWER"

    res_empty = {
        "success": True,
        "intent": "QUERY_AGENT",
        "reply": "No scheduled academic holidays are currently recorded.",
    }
    assert determine_outcome_state(res_empty) == "NO_RECORDS_FOUND"

    res_clarify = {
        "success": True,
        "intent": "CLARIFICATION_REQUIRED",
        "reply": "For which date and time interval should I check faculty availability?",
    }
    assert determine_outcome_state(res_clarify) == "CLARIFICATION_REQUIRED"


def test_deterministic_query_agent_and_multi_turn_follow_up(monkeypatch):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "false")
    with _get_db() as db:
        admin = db.query(User).filter(User.role == "ADMIN").first()
        student = db.query(User).filter(User.role == "STUDENT").first()
        assert admin is not None and student is not None

        # 1. Clarification on bare "available faculties"
        r1 = execute_supervisor(message="available faculties", user=admin, db=db, conversation_history=[])
        assert r1["intent"] == "CLARIFICATION_REQUIRED"
        assert "date and time interval" in r1["reply"].lower()

        # 2. Multi-turn follow-up: date & time -> department -> Friday
        hist = [
            {"sender": "user", "content": "available faculties"},
            {"sender": "assistant", "content": r1["reply"], "intent": r1["intent"], "tool_calls": []},
        ]
        r2 = execute_supervisor(message="Tomorrow from 2 PM to 3 PM.", user=admin, db=db, conversation_history=hist)
        assert r2["tool_calls"] and r2["tool_calls"][0]["tool"] == "get_available_faculty"
        assert "Available Faculty" in r2["reply"]

        hist.extend([
            {"sender": "user", "content": "Tomorrow from 2 PM to 3 PM."},
            {"sender": "assistant", "content": r2["reply"], "intent": r2["intent"], "tool_calls": r2["tool_calls"]},
        ])
        r3 = execute_supervisor(message="Only from AI and DS.", user=admin, db=db, conversation_history=hist)
        assert r3["tool_calls"][0]["args"].get("department_name") == "AI & DS"

        hist.extend([
            {"sender": "user", "content": "Only from AI and DS."},
            {"sender": "assistant", "content": r3["reply"], "intent": r3["intent"], "tool_calls": r3["tool_calls"]},
        ])
        r4 = execute_supervisor(message="What about Friday?", user=admin, db=db, conversation_history=hist)
        assert r4["tool_calls"][0]["tool"] == "get_available_faculty"
        assert "FRIDAY" in r4["reply"]

        # 3. RBAC: Student cannot access Admin directory tools directly
        denied = execute_tool("search_student_directory", {}, student, db)
        assert "error" in denied


def test_chat_api_endpoint_admin_queries(monkeypatch):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "false")
    login = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for q, expected_outcome in [
        ("available faculties", ("CLARIFICATION_REQUIRED",)),
        ("Which faculty are free tomorrow from 2 PM to 3 PM?", ("GROUNDED_ANSWER",)),
        ("Show faculty in AI and DS.", ("GROUNDED_ANSWER",)),
        ("What courses are available?", ("GROUNDED_ANSWER",)),
        ("Show the academic holidays.", ("GROUNDED_ANSWER", "NO_RECORDS_FOUND")),
    ]:
        res = client.post("/agents/chat", json={"message": q}, headers=headers)
        assert res.status_code == 200, f"Unexpected status for '{q}': {res.status_code} {res.text}"
        data = res.json()
        assert data["reply"], f"Empty reply for '{q}'"
        assert data["outcome_state"] in expected_outcome, f"For '{q}', expected {expected_outcome}, got {data['outcome_state']}"
