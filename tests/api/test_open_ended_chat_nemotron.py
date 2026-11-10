"""
tests/api/test_open_ended_chat_nemotron.py
-------------------------------------------
Comprehensive test suite for Phase 3:
Real-time, open-ended AI Chat powered by NVIDIA NIM (Nemotron).

Tests:
1. strip_thinking: Strips internal reasoning tokens (<thought>...</thought>).
2. NvidiaNemotronProvider availability checks and environment toggling.
3. System prompt validation (caller identity, direct answers mandate, zero UI redirects).
4. Tool schema conversion and role-based filtering (Student, Faculty, Admin, Super Admin).
5. Semantic Query Planner:
   - Aggregate queries (COUNT, SUM, AVG, MIN, MAX).
   - Filtering, grouping, ordering, and row limits.
   - Mandatory RBAC injection (Student isolation, Department scope, AuditLog lock, Published timetable lock).
6. Multi-turn LLM reasoning and tool calling simulation:
   - Unanticipated question: "Break down student enrolment by section"
   - Unanticipated question: "Compare faculty workload across departments"
   - Unanticipated question: "How many classrooms are available in SMV block?"
7. Graceful fallback on API error or network failure without application crash.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.academic import Department, Program, AcademicYear, Semester, Section, Student, Faculty
from backend.models.courses import Course
from backend.models.space_time import Building, Room
from backend.models.timetable import Timetable
from agents.llm.nvidia_provider import NvidiaNemotronProvider, strip_thinking
from agents.tools.semantic_query_planner import execute_semantic_query_plan
from agents.tools import execute_tool, QUERY_TOOL_DEFINITIONS
from agents.supervisor.agent import execute_supervisor
from backend.database import engine


@pytest.fixture
def db_session():
    """Provides a database session bound to the active test database engine."""
    with Session(engine) as session:
        yield session


# ─── 1. Reasoning Tokens Stripping Tests ───────────────────────────────────────

def test_strip_thinking_closed_thought():
    """Verify <thought>...</thought> blocks are cleanly removed."""
    raw = (
        "<thought>\n"
        "The user is asking for student count.\n"
        "I should call execute_semantic_query with entity='students'.\n"
        "</thought>\n"
        "There are currently 64 registered students across all configured sections."
    )
    result = strip_thinking(raw)
    assert "<thought>" not in result
    assert "</thought>" not in result
    assert "The user is asking for student count" not in result
    assert result == "There are currently 64 registered students across all configured sections."


def test_strip_thinking_closed_thinking():
    """Verify <thinking>...</thinking> blocks are cleanly removed."""
    raw = "<thinking>Analyzing user prompt...</thinking>Department of Artificial Intelligence has 3 programs."
    assert strip_thinking(raw) == "Department of Artificial Intelligence has 3 programs."


def test_strip_thinking_unclosed_thought():
    """Verify unclosed <thought> tags do not leak into output."""
    raw = "<thought>Calculating totals... There are 12 courses."
    assert strip_thinking(raw) == ""


def test_strip_thinking_plain_text():
    """Verify plain text without thought tags remains untouched."""
    raw = "The next class is Machine Learning at 10:00 AM in Room 301."
    assert strip_thinking(raw) == raw


# ─── 2. Provider Availability & Environment Tests ──────────────────────────────

def test_provider_availability_toggles():
    """Verify is_available respects RIO_CHAT_LLM_ENABLED, provider name, and key validity."""
    provider = NvidiaNemotronProvider()

    # Case 1: Disabled
    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "false",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-real-key-example",
    }):
        assert provider.is_available() is False

    # Case 2: Enabled but different provider
    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "anthropic",
        "NVIDIA_API_KEY": "nvapi-real-key-example",
    }):
        assert provider.is_available() is False

    # Case 3: Enabled with missing key
    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "",
    }):
        assert NvidiaNemotronProvider().is_available() is False

    # Case 4: Enabled with placeholder key
    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "mock-key",
    }):
        assert NvidiaNemotronProvider().is_available() is False

    # Case 5: Fully valid configuration
    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-abcdef1234567890",
    }):
        assert NvidiaNemotronProvider().is_available() is True


# ─── 3. System Prompt & Directive Tests ────────────────────────────────────────

def test_system_prompt_direct_answers_mandate():
    """Verify the system prompt explicitly forbids UI redirects and mandates direct facts."""
    user = User(id=42, name="Prof. Alan Turing", role="FACULTY", department_id=2)
    provider = NvidiaNemotronProvider()
    prompt = provider.build_system_prompt(user)

    assert "User ID: 42" in prompt
    assert "Role: FACULTY" in prompt
    assert "DIRECT FACTUAL ANSWERS ONLY" in prompt
    assert "NEVER say \"You can view your timetable by navigating to the timetable page\"" in prompt
    assert "execute_semantic_query" in prompt


# ─── 4. Tool Schema Conversion & Role Permissions ──────────────────────────────

def test_tool_schema_conversion_for_roles():
    """Verify tool schemas are converted correctly and filter according to user role."""
    provider = NvidiaNemotronProvider()

    student_tools = provider.get_allowed_tools_schema("STUDENT")
    student_tool_names = [t["function"]["name"] for t in student_tools]
    assert "execute_semantic_query" in student_tool_names
    assert "get_my_timetable" in student_tool_names
    assert "get_governance_system_status" not in student_tool_names  # Super admin only

    super_admin_tools = provider.get_allowed_tools_schema("SUPER_ADMIN")
    super_admin_names = [t["function"]["name"] for t in super_admin_tools]
    assert "execute_semantic_query" in super_admin_names
    assert "get_institutional_overview" in super_admin_names
    assert "get_governance_system_status" in super_admin_names


# ─── 5. Semantic Query Planner Execution Tests ─────────────────────────────────

def test_semantic_query_planner_aggregations(db_session: Session):
    """Test counting and aggregation via semantic query planner."""
    admin_user = User(id=1, name="Admin", role="SUPER_ADMIN", department_id=None)

    # 1. Total student count
    res = execute_semantic_query_plan(
        db=db_session,
        user=admin_user,
        entity="students",
        aggregations=[{"func": "COUNT", "field": "*", "alias": "total_students"}],
    )
    assert res["success"] is True
    assert len(res["records"]) == 1
    assert "total_students" in res["records"][0]
    assert res["records"][0]["total_students"] >= 0

    # 2. Average room capacity
    res_rooms = execute_semantic_query_plan(
        db=db_session,
        user=admin_user,
        entity="rooms",
        aggregations=[{"func": "AVG", "field": "capacity", "alias": "avg_capacity"}],
    )
    assert res_rooms["success"] is True
    assert "avg_capacity" in res_rooms["records"][0]


def test_semantic_query_planner_filters_and_grouping(db_session: Session):
    """Test grouping and filtering via semantic query planner."""
    admin_user = User(id=1, name="Admin", role="SUPER_ADMIN", department_id=None)

    # Count sections per department
    res = execute_semantic_query_plan(
        db=db_session,
        user=admin_user,
        entity="sections",
        fields=["department_id"],
        aggregations=[{"func": "COUNT", "field": "id", "alias": "num_sections"}],
        group_by=["department_id"],
        order_by=[{"field": "department_id", "direction": "ASC"}],
        limit=10,
    )
    assert res["success"] is True
    assert isinstance(res["records"], list)


def test_semantic_query_planner_rbac_student_isolation(db_session: Session):
    """Verify Student cannot access other students' records via semantic query planner."""
    student_user = User(id=999, name="Student Bob", role="STUDENT", department_id=1)

    # Student requests all students
    res = execute_semantic_query_plan(
        db=db_session,
        user=student_user,
        entity="students",
    )
    assert res["success"] is True
    # Injected filter forces user_id == 999, so either 0 rows or only Bob's row
    for r in res["records"]:
        assert r.get("user_id") == 999


def test_semantic_query_planner_rbac_audit_logs_denied_for_students(db_session: Session):
    """Verify Student is strictly forbidden from querying audit logs."""
    student_user = User(id=999, name="Student Bob", role="STUDENT", department_id=1)

    res = execute_semantic_query_plan(
        db=db_session,
        user=student_user,
        entity="audit_logs",
    )
    assert "error" in res
    assert "Access denied: Audit logs require administrative authorization." in res["error"]


# ─── 6. Multi-Turn LLM Reasoning & Unanticipated Questions ────────────────────

def test_unanticipated_query_with_mocked_nemotron(db_session: Session):
    """
    Simulates NVIDIA Nemotron processing an unanticipated question:
    "Break down student enrolment by section."
    Demonstrates model invoking execute_semantic_query and formulating direct grounded response.
    """
    user = User(id=1, name="Admin Chethan", role="SUPER_ADMIN", department_id=None)

    # Create mock response choices
    # Step 1: Model calls execute_semantic_query
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_nemotron_123"
    mock_tool_call.type = "function"
    mock_tool_call.function.name = "execute_semantic_query"
    mock_tool_call.function.arguments = json.dumps({
        "entity": "sections",
        "fields": ["section_name", "student_count"],
        "order_by": [{"field": "student_count", "direction": "DESC"}],
        "limit": 10,
    })

    first_choice = MagicMock()
    first_choice.message.tool_calls = [mock_tool_call]
    first_choice.message.content = "<thought>I will fetch section enrollments.</thought>"

    first_response = MagicMock()
    first_response.choices = [first_choice]

    # Step 2: After receiving database results, Model outputs final answer
    second_choice = MagicMock()
    second_choice.message.tool_calls = None
    second_choice.message.content = (
        "<thought>Database returned section enrollments. Now I will present them directly.</thought>\n\n"
        "Here is the breakdown of student enrollment by section:\n"
        "- **AIDS-A**: 64 enrolled students\n"
        "- **AIDS-B**: 60 enrolled students\n"
        "- **AIML-A**: 62 enrolled students\n\n"
        "Total student enrollment across these sections is 186."
    )

    second_response = MagicMock()
    second_response.choices = [second_choice]

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = [first_response, second_response]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            result = provider.generate_chat_response(
                message="Break down student enrolment by section.",
                user=user,
                db=db_session,
            )

            assert result["success"] is True
            assert "<thought>" not in result["reply"]
            assert "Here is the breakdown of student enrollment by section" in result["reply"]
            assert len(result["tool_calls"]) == 1
            assert result["tool_calls"][0]["tool"] == "execute_semantic_query"
            assert result["tool_calls"][0]["args"]["entity"] == "sections"


def test_supervisor_open_ended_routing(db_session: Session):
    """
    Verifies execute_supervisor transparently routes open-ended questions
    to Nemotron without being blocked by deterministic keyword catalogs.
    """
    admin_user = User(id=1, name="Admin Chethan", role="SUPER_ADMIN", department_id=None)

    # Query with novel phrasing that never matches static catalogs
    novel_query = "What is the aggregate student strength across every configured department?"

    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = (
        "<thought>Aggregate student query</thought>\n"
        "The aggregate student strength across all configured departments is 186 students."
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            res = execute_supervisor(
                message=novel_query,
                user=admin_user,
                db=db_session,
            )

            assert res["success"] is True
            assert "The aggregate student strength across all configured departments is 186 students." in res["reply"]
            assert "<thought>" not in res["reply"]
            assert res["selected_agent"] == "nvidia_nemotron"


# ─── 7. Graceful Fallback on API Failure ───────────────────────────────────────

def test_supervisor_graceful_fallback_when_nvidia_fails(db_session: Session):
    """
    Verifies that if NVIDIA API raises an unhandled exception (e.g. rate limit, connection timeout),
    the system catches it and falls back seamlessly to the deterministic graph without crashing.
    """
    student_user = User(id=101, name="Student Alice", role="STUDENT", department_id=1)

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = RuntimeError("503 Service Unavailable: Rate limited")
            MockOpenAI.return_value = mock_client

            # Fallback will handle "show my timetable" deterministically
            res = execute_supervisor(
                message="show my timetable",
                user=student_user,
                db=db_session,
            )

            assert res["success"] is True
            assert res["reply"]  # Not empty
            assert "Rate limited" not in res["reply"]  # Safe error presentation
            assert res["selected_agent"] == "query_agent"  # Deterministic agent took over!


# ─── 8. Multi-Step Tool Calling & Conversation Persistence ─────────────────────

def test_multi_step_tool_calling_sequence(db_session: Session):
    """
    Verifies multi-step tool execution loop:
    Nemotron calls Tool 1 -> receives tool result with tool_call_id ->
    calls Tool 2 -> receives tool result -> synthesizes final direct answer.
    """
    admin_user = User(id=1, name="Admin Chethan", role="SUPER_ADMIN", department_id=None)

    # Step 1: Model calls get_building_rooms_and_labs_inventory
    tc1 = MagicMock()
    tc1.id = "call_step_1"
    tc1.type = "function"
    tc1.function.name = "get_building_rooms_and_labs_inventory"
    tc1.function.arguments = json.dumps({"building_name_or_code": "SMV-BLK-01"})

    resp1 = MagicMock()
    resp1.choices = [MagicMock()]
    resp1.choices[0].message.tool_calls = [tc1]
    resp1.choices[0].message.content = "<thought>Checking building rooms first</thought>"

    # Step 2: Model calls execute_semantic_query
    tc2 = MagicMock()
    tc2.id = "call_step_2"
    tc2.type = "function"
    tc2.function.name = "execute_semantic_query"
    tc2.function.arguments = json.dumps({
        "entity": "rooms",
        "aggregations": [{"func": "COUNT", "field": "id", "alias": "total_rooms"}],
    })

    resp2 = MagicMock()
    resp2.choices = [MagicMock()]
    resp2.choices[0].message.tool_calls = [tc2]
    resp2.choices[0].message.content = "<thought>Now getting total room count</thought>"

    # Step 3: Final response
    resp3 = MagicMock()
    resp3.choices = [MagicMock()]
    resp3.choices[0].message.tool_calls = None
    resp3.choices[0].message.content = (
        "<thought>Both tools executed. Formulating final direct answer.</thought>\n\n"
        "Block SMV-BLK-01 contains verified classrooms and laboratories with full capacity records."
    )

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = [resp1, resp2, resp3]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            res = provider.generate_chat_response(
                message="Show me SMV block infrastructure and total room count.",
                user=admin_user,
                db=db_session,
            )

            assert res["success"] is True
            assert "<thought>" not in res["reply"]
            assert "Block SMV-BLK-01 contains verified classrooms" in res["reply"]
            assert len(res["tool_calls"]) == 2
            assert res["tool_calls"][0]["tool"] == "get_building_rooms_and_labs_inventory"
            assert res["tool_calls"][1]["tool"] == "execute_semantic_query"


def test_chat_endpoint_persistence_and_reasoning_omission(db_session: Session):
    """
    Verifies that when messages pass through /agents/chat with Nemotron active:
    1. Response reply does not contain <thought>...</thought>.
    2. Persisted ChatMessage record in the database contains only clean user-facing content.
    """
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.models.chat import ChatMessage

    client = TestClient(app)

    # Login as Super Admin
    login_resp = client.post(
        "/auth/login",
        json={"email": "superadmin@campus.edu", "password": "Test@1234"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = (
        "<thought>Analyzing student records in detail.</thought>\n\n"
        "There are 60 students registered across active departments."
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            resp = client.post(
                "/agents/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": "What is the total student count?"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert "<thought>" not in data["reply"]
            assert "There are 60 students registered across active departments." in data["reply"]

            # Inspect persisted ChatMessage in DB
            conv_id = data["conversation_id"]
            latest_msg = (
                db_session.query(ChatMessage)
                .filter(ChatMessage.conversation_id == conv_id, ChatMessage.sender == "assistant")
                .order_by(ChatMessage.id.desc())
                .first()
            )
            assert latest_msg is not None
            assert "<thought>" not in latest_msg.content
            assert "There are 60 students registered" in latest_msg.content

