"""
tests/agents/test_supervisor.py
-------------------------------
Unit tests for RIO-MJP Supervisor Agent:
- Intent classification accuracy
- Routing of supported informational queries to Query Agent
- Blocking of unsupported timetable generation actions (Stage 9A boundary)
- Blocking of unsupported resource booking mutations (Stage 9A boundary)
- Handling of ambiguous or greeting requests
"""

import pytest
from agents.supervisor.agent import (
    classify_intent,
    supervisor_node,
    route_supervisor,
    execute_supervisor,
)
from backend.models.identity import User


def test_intent_classification_supported_queries():
    assert classify_intent("What is my next class?") == "QUERY_AGENT"
    assert classify_intent("Show my timetable for Monday") == "QUERY_AGENT"
    assert classify_intent("Where is Room 101 located?") == "QUERY_AGENT"
    assert classify_intent("Who is teaching Dr. Allison Hill?") == "QUERY_AGENT"
    assert classify_intent("What are the credits for course CS101?") == "QUERY_AGENT"
    assert classify_intent("When are the upcoming academic holidays?") == "QUERY_AGENT"
    assert classify_intent("What is the department schedule?") == "QUERY_AGENT"


def test_intent_classification_unsupported_scheduling_blocked():
    # Stage 9A boundary: Conversational timetable generation must NOT be dispatched
    assert classify_intent("Generate a new semester timetable") == "TIMETABLE_GENERATION"
    assert classify_intent("Create timetable for Department of CSE") == "TIMETABLE_GENERATION"
    assert classify_intent("Run the timetable optimizer solver") == "TIMETABLE_GENERATION"
    assert classify_intent("Auto-generate schedule") == "TIMETABLE_GENERATION"


def test_intent_classification_unsupported_resource_booking_blocked():
    # Stage 9A boundary: Conversational booking mutations must NOT be dispatched
    assert classify_intent("Book the seminar hall for tomorrow") == "RESOURCE_BOOKING"
    assert classify_intent("Reserve lab 301 from 10 to 12") == "RESOURCE_BOOKING"
    assert classify_intent("Cancel booking #4") == "RESOURCE_BOOKING"
    assert classify_intent("Approve booking #10") == "RESOURCE_BOOKING"


def test_supervisor_node_blocks_unsupported_scheduling():
    state = {
        "user_id": 1,
        "role": "ADMIN",
        "department_id": None,
        "message": "Please generate a new timetable for semester 5",
    }
    result = supervisor_node(state)
    assert result["intent"] == "TIMETABLE_GENERATION"
    assert result["selected_agent"] == "scheduling_agent_stub"
    assert "not enabled in Stage 9A" in result["final_response"]
    assert "Admin Timetable Generation workspace" in result["final_response"]


def test_supervisor_node_blocks_unsupported_booking():
    state = {
        "user_id": 2,
        "role": "FACULTY",
        "department_id": 1,
        "message": "Book Seminar Hall A for next Friday",
    }
    result = supervisor_node(state)
    assert result["intent"] == "RESOURCE_BOOKING"
    assert result["selected_agent"] == "resource_agent_stub"
    assert "not enabled in Stage 9A" in result["final_response"]
    assert "Resource Management workspace" in result["final_response"]


def test_supervisor_node_handles_greetings():
    state = {
        "user_id": 3,
        "role": "STUDENT",
        "department_id": 1,
        "message": "Hello, who are you?",
    }
    result = supervisor_node(state)
    assert result["intent"] == "CAMPUS_GREETING"
    assert result["selected_agent"] is None
    assert "RIO Campus Assistant" in result["final_response"]


def test_supervisor_node_handles_unknown_intent():
    state = {
        "user_id": 3,
        "role": "STUDENT",
        "department_id": 1,
        "message": "Tell me a joke about quantum physics",
    }
    result = supervisor_node(state)
    assert result["intent"] == "UNKNOWN"
    assert result["selected_agent"] is None
    assert "could not find a matching campus service" in result["final_response"]


def test_route_supervisor_conditional_edges():
    # Only query_agent routes to query_agent_node
    assert route_supervisor({"selected_agent": "query_agent"}) == "query_agent_node"
    assert route_supervisor({"selected_agent": "scheduling_agent_stub"}) == "end_node"
    assert route_supervisor({"selected_agent": "resource_agent_stub"}) == "end_node"
    assert route_supervisor({"selected_agent": None}) == "end_node"
