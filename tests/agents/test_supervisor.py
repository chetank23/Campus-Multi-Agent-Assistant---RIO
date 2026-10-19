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
from agents.state.state import AgentState
from backend.models.identity import User


def test_intent_classification_supported_queries():
    assert classify_intent("What is my next class?") == "QUERY_AGENT"
    assert classify_intent("Show my timetable for Monday") == "QUERY_AGENT"
    assert classify_intent("Where is Room 101 located?") == "QUERY_AGENT"
    assert classify_intent("Who is teaching Dr. Allison Hill?") == "QUERY_AGENT"
    assert classify_intent("What are the credits for course CS101?") == "QUERY_AGENT"
    assert classify_intent("When are the upcoming academic holidays?") == "QUERY_AGENT"
    assert classify_intent("What is the department schedule?") == "QUERY_AGENT"


def test_intent_classification_supported_scheduling():
    # Stage 9B: Timetable generation requests are classified for Scheduling Agent
    assert classify_intent("Generate a new semester timetable") == "TIMETABLE_GENERATION"
    assert classify_intent("Create timetable for Department of CSE") == "TIMETABLE_GENERATION"
    assert classify_intent("Run the timetable optimizer solver") == "TIMETABLE_GENERATION"
    assert classify_intent("Auto-generate schedule") == "TIMETABLE_GENERATION"
    assert classify_intent("Compare scheduling strategies") == "TIMETABLE_GENERATION"
    assert classify_intent("confirm prop_abc123") == "TIMETABLE_GENERATION"


def test_intent_classification_unsupported_resource_booking_blocked():
    # Conversational booking mutations remain out of scope until Resource Agent stage
    assert classify_intent("Book the seminar hall for tomorrow") == "RESOURCE_BOOKING"
    assert classify_intent("Reserve lab 301 from 10 to 12") == "RESOURCE_BOOKING"
    assert classify_intent("Cancel booking #4") == "RESOURCE_BOOKING"
    assert classify_intent("Approve booking #10") == "RESOURCE_BOOKING"


def test_supervisor_node_routes_scheduling_agent():
    state: AgentState = {
        "user_id": 1,
        "role": "ADMIN",
        "department_id": None,
        "message": "Please generate a new timetable for semester 5",
    }
    result = supervisor_node(state)
    assert result.get("intent") == "TIMETABLE_GENERATION"
    assert result.get("selected_agent") == "scheduling_agent"


def test_supervisor_node_routes_resource_agent():
    state: AgentState = {
        "user_id": 2,
        "role": "FACULTY",
        "department_id": 1,
        "message": "Book Seminar Hall A for tomorrow from 2pm to 4pm",
    }
    result = supervisor_node(state)
    assert result.get("intent") == "RESOURCE_BOOKING"
    assert result.get("selected_agent") == "resource_agent"


def test_supervisor_routes_resource_proposal_confirmation():
    assert classify_intent("confirm res_prop_1234567890abcdef1234567890abcdef") == "RESOURCE_BOOKING"
    state: AgentState = {
        "user_id": 2,
        "role": "FACULTY",
        "department_id": 1,
        "message": "confirm res_prop_1234567890abcdef1234567890abcdef",
    }
    result = supervisor_node(state)
    assert result.get("intent") == "RESOURCE_BOOKING"
    assert result.get("selected_agent") == "resource_agent"
    assert route_supervisor(result) == "resource_agent_node"


def test_supervisor_node_handles_greetings():
    state: AgentState = {
        "user_id": 3,
        "role": "STUDENT",
        "department_id": 1,
        "message": "Hello, who are you?",
    }
    result = supervisor_node(state)
    assert result.get("intent") == "CAMPUS_GREETING"
    assert result.get("selected_agent") is None
    assert "RIO Campus Assistant" in (result.get("final_response") or "")


def test_supervisor_node_handles_unknown_intent():
    state: AgentState = {
        "user_id": 3,
        "role": "STUDENT",
        "department_id": 1,
        "message": "Tell me a joke about quantum physics",
    }
    result = supervisor_node(state)
    assert result.get("intent") == "UNKNOWN"
    assert result.get("selected_agent") is None
    assert "could not find a matching campus service" in (result.get("final_response") or "")


def test_route_supervisor_conditional_edges():
    # query_agent and scheduling_agent route to their dedicated nodes
    assert route_supervisor(AgentState(selected_agent="query_agent")) == "query_agent_node"
    assert route_supervisor(AgentState(selected_agent="scheduling_agent")) == "scheduling_agent_node"
    assert route_supervisor(AgentState(selected_agent="resource_agent_stub")) == "end_node"
    assert route_supervisor(AgentState(selected_agent=None)) == "end_node"
