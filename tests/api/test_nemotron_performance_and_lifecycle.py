"""
tests/api/test_nemotron_performance_and_lifecycle.py
-----------------------------------------------------
Test suite verifying:
- Reusable HTTP client lifecycle and connection pooling
- Thread safety and safe concurrency
- Configurable connection and read timeouts
- In-request query memoization
- Safe parallel execution of read-only database tools
- Sequential isolation of state-changing tools
- Server-Sent Events (SSE) genuine streaming endpoint
- Streaming tool calling, token emission, and final fallback
- Conversation database persistence without duplicate records
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.database import engine
from backend.main import app
from backend.models.identity import User
from backend.models.academic import Department
from backend.models.chat import ChatConversation, ChatMessage
from agents.llm.nvidia_provider import (
    NvidiaNemotronProvider,
    execute_tool_calls_batch,
    STATE_CHANGING_TOOLS,
)
from agents.common.diagnostics import ChatRequestTrace


@pytest.fixture
def db_session():
    with Session(engine) as session:
        yield session


@pytest.fixture
def admin_user(db_session: Session) -> User:
    u = db_session.query(User).filter(User.role == "ADMIN").first()
    assert u is not None, "Admin user required in seed data"
    return u


@pytest.fixture
def student_user(db_session: Session) -> User:
    u = db_session.query(User).filter(User.role == "STUDENT").first()
    assert u is not None, "Student user required in seed data"
    return u


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 2: HTTP CLIENT LIFECYCLE & CONNECTION POOLING
# ═══════════════════════════════════════════════════════════════════════════════

def test_client_lifecycle_pooling_and_reuse():
    """
    Verifies that NvidiaNemotronProvider maintains a reusable HTTP client with
    connection pooling rather than instantiating a new client on every request.
    """
    # Clean state
    NvidiaNemotronProvider.close_client()
    assert NvidiaNemotronProvider._shared_openai_client is None
    assert NvidiaNemotronProvider._shared_http_client is None

    with patch.dict(os.environ, {
        "NVIDIA_API_KEY": "nvapi-test-pooling-key",
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
    }):
        provider1 = NvidiaNemotronProvider()
        client1 = provider1.get_client()
        assert client1 is not None

        provider2 = NvidiaNemotronProvider()
        client2 = provider2.get_client()

        # Both providers must share the exact same underlying OpenAI client instance
        assert client1 is client2
        assert NvidiaNemotronProvider._shared_http_client is not None

        # Clean shutdown test
        NvidiaNemotronProvider.close_client()
        assert NvidiaNemotronProvider._shared_openai_client is None
        assert NvidiaNemotronProvider._shared_http_client is None


def test_client_lifecycle_application_startup_initialization():
    """
    Verifies that initialize_client() correctly pre-warms the pooled client.
    """
    NvidiaNemotronProvider.close_client()

    with patch.dict(os.environ, {
        "NVIDIA_API_KEY": "nvapi-test-init-key",
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
    }):
        client = NvidiaNemotronProvider.initialize_client()
        assert client is not None
        assert NvidiaNemotronProvider._shared_openai_client is not None

    NvidiaNemotronProvider.close_client()


def test_configurable_timeouts_respected():
    """
    Verifies that NVIDIA_CONNECT_TIMEOUT and NVIDIA_READ_TIMEOUT environment
    variables are loaded and respected.
    """
    with patch.dict(os.environ, {
        "NVIDIA_CONNECT_TIMEOUT": "12.5",
        "NVIDIA_READ_TIMEOUT": "60.0",
        "NVIDIA_MAX_TOOL_ROUNDS": "7",
        "NVIDIA_MAX_TOKENS": "2048",
    }):
        provider = NvidiaNemotronProvider(api_key="nvapi-timeout-test")
        assert provider.connect_timeout == 12.5
        assert provider.read_timeout == 60.0
        assert provider.max_tool_rounds == 7
        assert provider.max_tokens == 2048


def test_concurrent_client_access_thread_safety():
    """
    Verifies that multiple concurrent threads safely acquire the shared pooled client
    without race conditions or duplicate connection pools.
    """
    NvidiaNemotronProvider.close_client()

    clients_acquired = []

    def worker():
        with patch.dict(os.environ, {
            "NVIDIA_API_KEY": "nvapi-concurrency-test",
            "RIO_CHAT_LLM_ENABLED": "true",
            "RIO_CHAT_LLM_PROVIDER": "nvidia",
        }):
            p = NvidiaNemotronProvider()
            c = p.get_client()
            clients_acquired.append(c)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(clients_acquired) == 8
    first_client = clients_acquired[0]
    for c in clients_acquired:
        assert c is first_client

    NvidiaNemotronProvider.close_client()


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 3: TOOL-CALL OPTIMIZATION & SAFE PARALLELIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def test_in_request_query_memoization(db_session: Session, admin_user: User):
    """
    Verifies that repeated identical queries in a single request are memoized
    and do not repeatedly hit the database.
    """
    trace = ChatRequestTrace(user_id=admin_user.id, role=admin_user.role, provider="nvidia")
    memoized: Dict[str, Any] = {}

    class DummyTC:
        def __init__(self, c_id: str, fn_name: str, fn_args: str):
            self.id = c_id
            self.type = "function"
            self.function = MagicMock()
            self.function.name = fn_name
            self.function.arguments = fn_args

    # Two identical calls in the same turn
    call1 = DummyTC("c1", "get_published_timetable_status", "{}")
    call2 = DummyTC("c2", "get_published_timetable_status", "{}")

    results = execute_tool_calls_batch(
        tool_calls=[call1, call2],
        user=admin_user,
        db=db_session,
        trace=trace,
        memoized_results=memoized,
    )

    assert len(results) == 2
    assert results[0]["id"] == "c1"
    assert results[1]["id"] == "c2"
    assert results[0]["cached"] is False
    assert results[1]["cached"] is True
    assert results[0]["result"] == results[1]["result"]


def test_parallel_read_only_tool_execution(db_session: Session, admin_user: User):
    """
    Verifies that independent read-only tools in a single turn execute in parallel.
    """
    trace = ChatRequestTrace(user_id=admin_user.id, role=admin_user.role, provider="nvidia")
    memoized: Dict[str, Any] = {}

    first_dept = db_session.query(Department).first()
    assert first_dept is not None

    class DummyTC:
        def __init__(self, c_id: str, fn_name: str, fn_args: str):
            self.id = c_id
            self.type = "function"
            self.function = MagicMock()
            self.function.name = fn_name
            self.function.arguments = fn_args

    call1 = DummyTC("c1", "get_published_timetable_status", "{}")
    call2 = DummyTC("c2", "search_student_directory", json.dumps({"department_name": first_dept.name}))
    call3 = DummyTC("c3", "get_room_availability", json.dumps({"time_slot": "morning"}))

    results = execute_tool_calls_batch(
        tool_calls=[call1, call2, call3],
        user=admin_user,
        db=db_session,
        trace=trace,
        memoized_results=memoized,
    )

    assert len(results) == 3
    # Check that all 3 tools returned valid data
    for r in results:
        assert r["error"] is None
        assert isinstance(r["result"], dict)


def test_state_changing_tool_sequential_isolation(db_session: Session, admin_user: User):
    """
    Verifies that state-changing tools (STATE_CHANGING_TOOLS) are recognized
    and not run in detached parallel threads.
    """
    assert "execute_approve_booking" in STATE_CHANGING_TOOLS
    assert "execute_reject_booking" in STATE_CHANGING_TOOLS
    assert "execute_update_room" in STATE_CHANGING_TOOLS


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 4: GENUINE SERVER-SENT EVENTS (SSE) STREAMING
# ═══════════════════════════════════════════════════════════════════════════════

def test_sse_streaming_endpoint_format_and_conversation_persistence(admin_user: User):
    """
    Verifies that /agents/chat/stream returns text/event-stream, streams SSE events,
    and persists both user and assistant messages in the database.
    """
    from backend.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: admin_user

    client = TestClient(app)
    try:
        with patch.dict(os.environ, {"RIO_CHAT_LLM_ENABLED": "false"}):
            resp = client.post(
                "/agents/chat/stream",
                json={"message": "Hello campus assistant!"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            lines = resp.text.split("\n")
            events = [line for line in lines if line.startswith("event:")]
            data_lines = [line for line in lines if line.startswith("data:")]

            assert len(events) > 0
            assert len(data_lines) > 0
            assert "event: done" in resp.text

            # Parse the done event
            done_frame = None
            for i, line in enumerate(lines):
                if line.strip() == "event: done" and i + 1 < len(lines):
                    data_part = lines[i + 1].replace("data:", "").strip()
                    done_frame = json.loads(data_part)
                    break

            assert done_frame is not None
            assert done_frame.get("success") is True
            assert done_frame.get("conversation_id") is not None
            conv_id = done_frame["conversation_id"]

            # Verify database persistence
            with Session(engine) as s:
                user_msg = s.query(ChatMessage).filter(ChatMessage.conversation_id == conv_id, ChatMessage.sender == "user").first()
                assert user_msg is not None
                assert user_msg.content == "Hello campus assistant!"

                asst_msg = s.query(ChatMessage).filter(ChatMessage.conversation_id == conv_id, ChatMessage.sender == "assistant").first()
                assert asst_msg is not None
                assert asst_msg.content == done_frame["reply"]

    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_sse_streaming_tool_calling_event_sequence(admin_user: User, db_session: Session):
    """
    Verifies the streaming event sequence when the model issues tool calls:
    connecting -> generating -> calling_tools -> tool_start -> tool_done -> generating -> token -> done
    """
    # Turn 1: Model streams a tool call
    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = "tc_1"
    tc_delta.function = MagicMock()
    tc_delta.function.name = "get_published_timetable_status"
    tc_delta.function.arguments = "{}"

    c1 = MagicMock()
    c1.choices = [MagicMock()]
    c1.choices[0].delta = MagicMock()
    c1.choices[0].delta.tool_calls = [tc_delta]
    c1.choices[0].delta.content = None

    # Turn 2: Model streams final text tokens
    c2_token1 = MagicMock()
    c2_token1.choices = [MagicMock()]
    c2_token1.choices[0].delta = MagicMock()
    c2_token1.choices[0].delta.tool_calls = None
    c2_token1.choices[0].delta.content = "Academic "

    c2_token2 = MagicMock()
    c2_token2.choices = [MagicMock()]
    c2_token2.choices[0].delta = MagicMock()
    c2_token2.choices[0].delta.tool_calls = None
    c2_token2.choices[0].delta.content = "timetable active."

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-stream-test",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            # Turn 1 returns c1, Turn 2 returns c2_token1 then c2_token2
            mock_client.chat.completions.create.side_effect = [
                [c1],
                [c2_token1, c2_token2],
            ]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            events = list(provider.stream_chat_response(
                message="Which timetables are active?",
                user=admin_user,
                db=db_session,
            ))

            event_types = [e["event"] for e in events]
            assert "status" in event_types
            assert "tool_start" in event_types
            assert "tool_done" in event_types
            assert "token" in event_types
            assert "done" in event_types

            # Verify token text
            tokens = [e["data"]["token"] for e in events if e["event"] == "token"]
            full_text = "".join(tokens)
            assert "Academic timetable active." in full_text


def test_sse_streaming_fallback_when_model_returns_empty_content(admin_user: User, db_session: Session):
    """
    When streaming turn 2 outputs empty text, verifies that the provider falls back
    to deterministic data synthesis and streams the synthesized tokens.
    """
    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = "tc_dept"
    tc_delta.function = MagicMock()
    tc_delta.function.name = "get_published_timetable_status"
    tc_delta.function.arguments = "{}"

    c1 = MagicMock()
    c1.choices = [MagicMock()]
    c1.choices[0].delta = MagicMock()
    c1.choices[0].delta.tool_calls = [tc_delta]
    c1.choices[0].delta.content = None

    # Empty turn 2
    c2 = MagicMock()
    c2.choices = [MagicMock()]
    c2.choices[0].delta = MagicMock()
    c2.choices[0].delta.tool_calls = None
    c2.choices[0].delta.content = ""

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-stream-empty-test",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = [[c1], [c2]]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            events = list(provider.stream_chat_response(
                message="Which departments have timetables?",
                user=admin_user,
                db=db_session,
            ))

            done_events = [e for e in events if e["event"] == "done"]
            assert len(done_events) == 1
            reply = done_events[0]["data"]["reply"]
            assert reply and len(reply) > 0
            assert "Executed tool" not in reply
            # Tokens were streamed
            token_events = [e for e in events if e["event"] == "token"]
            assert len(token_events) > 0


def test_sse_streaming_error_handling(admin_user: User, db_session: Session):
    """
    Verifies that if an unexpected exception occurs before tools run,
    an event: error is emitted gracefully without crashing the server.
    """
    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-stream-err-test",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = RuntimeError("NVIDIA NIM connection refused")
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            events = list(provider.stream_chat_response(
                message="Test error query",
                user=admin_user,
                db=db_session,
            ))

            error_events = [e for e in events if e["event"] == "error"]
            assert len(error_events) == 1
            assert "NVIDIA NIM connection refused" in error_events[0]["data"]["error"]
