"""
tests/api/test_chat_resilience_and_sse.py
-----------------------------------------
Comprehensive regression suite for chat pipeline resilience, SSE lifecycle,
bounded Nemotron timeouts, cancellation, authentication, and Markdown preservation.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APITimeoutError
from sqlalchemy.orm import Session

from backend.config import engine
from backend.main import app
from backend.models import Timetable, TimetableEntry, TimetableVersion, User
from agents.llm.nvidia_provider import NvidiaNemotronProvider

client = TestClient(app)


@pytest.fixture(scope="module")
def admin_token():
    r = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert r.status_code == 200
    return r.json()["access_token"]


def _parse_sse(text: str):
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        trimmed = block.strip()
        if not trimmed or trimmed.startswith(":"):
            continue
        if trimmed.startswith("data:"):
            events.append(json.loads(trimmed[5:].strip()))
    return events


def test_sse_simple_greeting_completes(admin_token):
    resp = client.post(
        "/agents/chat/stream",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Hi"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[0]["event"] == "status"
    assert events[-1]["event"] == "done"
    assert events[-1]["success"] is True
    assert events[-1]["reply"].strip()


def test_sse_general_knowledge_mocked_nemotron(monkeypatch, admin_token):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    rich_md = (
        "## Artificial Intelligence\n\n"
        "**Artificial Intelligence (AI)** enables machines to learn and reason.\n\n"
        "- **Healthcare:** Diagnostics\n"
        "- **Education:** Tutoring\n\n"
        "```python\nprint('AI')\n```"
    )
    mock_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=rich_md, tool_calls=None))]
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "Explain artificial intelligence."},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[-1]["event"] == "done"
    streamed_text = "".join(e["token"] for e in events if e.get("event") == "token")
    assert "## Artificial Intelligence" in streamed_text
    assert "**Artificial Intelligence (AI)**" in streamed_text
    assert "```python\nprint('AI')\n```" in streamed_text
    assert events[-1]["reply"] == rich_md


def test_sse_database_query_and_empty_results(admin_token):
    with Session(engine) as db:
        db.query(TimetableEntry).delete()
        db.query(TimetableVersion).delete()
        db.query(Timetable).delete()
        db.commit()

    resp = client.post(
        "/agents/chat/stream",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "How many timetables are published?"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[-1]["event"] == "done"
    assert "couldn't find any currently published timetable" in events[-1]["reply"].lower()


def test_sse_multiple_tool_calls_coherent_answer(monkeypatch, admin_token):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    tc1 = SimpleNamespace(
        id="c1",
        type="function",
        function=SimpleNamespace(name="get_published_timetables", arguments="{}"),
    )
    tc2 = SimpleNamespace(
        id="c2",
        type="function",
        function=SimpleNamespace(name="get_campus_room_inventory", arguments="{}"),
    )
    r1 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc1, tc2]))])
    r2 = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Here is the combined campus summary.", tool_calls=None))]
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [r1, r2]

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "Show published timetables and campus room count."},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    done_ev = events[-1]
    assert done_ev["event"] == "done"
    assert done_ev["reply"] == "Here is the combined campus summary."
    assert len(done_ev["tool_calls"]) == 2


def test_nvidia_api_timeout_falls_back_cleanly_without_retries(monkeypatch, admin_token):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    mock_client = MagicMock()
    req = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=cast(Any, req))

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client) as openai_cls:
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "How many timetables are published?"},
        )

    assert resp.status_code == 200
    # Verify max_retries=0 was enforced so timeouts do not multiply 3x
    assert openai_cls.call_args.kwargs.get("max_retries") == 0
    events = _parse_sse(resp.text)
    assert events[-1]["event"] == "done"
    assert events[-1]["reply"].strip()


def test_tool_exception_recovers_cleanly(monkeypatch, admin_token):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    tc1 = SimpleNamespace(
        id="c1",
        type="function",
        function=SimpleNamespace(name="get_published_timetables", arguments="{}"),
    )
    r1 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc1]))])
    r2 = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="I encountered an issue reading timetable records.", tool_calls=None))]
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [r1, r2]

    with (
        patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client),
        patch("agents.llm.nvidia_provider.execute_tool", return_value={"error": "Database query timed out"}),
    ):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "Show published timetables."},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[-1]["event"] == "done"
    assert events[-1]["reply"].strip()


def test_invalid_auth_rejected_on_stream():
    resp = client.post(
        "/agents/chat/stream",
        headers={"Authorization": "Bearer invalid.jwt.token"},
        json={"message": "Hi"},
    )
    assert resp.status_code == 401


def test_provider_cancellation_stops_loop():
    provider = NvidiaNemotronProvider(api_key="nvapi-test-key-0001")
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "ADMIN").first()
        assert user is not None
        res = provider.generate_chat_response(
            message="Hi",
            user=user,
            db=db,
            cancel_check=lambda: True,
        )
    assert res["success"] is False
    assert res["intent"] == "CANCELLED"


def test_consecutive_messages_work_independently(admin_token):
    r1 = client.post(
        "/agents/chat/stream",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Hi"},
    )
    assert r1.status_code == 200
    e1 = _parse_sse(r1.text)
    assert e1[-1]["event"] == "done"
    conv_id = e1[-1]["conversation_id"]

    r2 = client.post(
        "/agents/chat/stream",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "How many timetables are published?", "conversation_id": conv_id},
    )
    assert r2.status_code == 200
    e2 = _parse_sse(r2.text)
    assert e2[-1]["event"] == "done"
    assert e2[-1]["conversation_id"] == conv_id


def test_slow_response_emits_terminal_done(monkeypatch, admin_token):
    def slow_exec(**kwargs):
        time.sleep(0.6)
        return {
            "reply": "Delayed grounded response.",
            "intent": "QUERY_AGENT",
            "selected_agent": "query_agent",
            "tool_calls": [],
            "sources": ["RIO Database"],
            "success": True,
            "error": None,
        }

    with patch("backend.routes.chat.execute_supervisor", side_effect=slow_exec):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "Slow test"},
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[-1]["event"] == "done"
    assert events[-1]["reply"] == "Delayed grounded response."


def test_live_stream_emits_progress_stages_and_filters_thinking(monkeypatch, admin_token):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    def _chunk(text):
        return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])

    captured_kwargs = {}

    def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return iter([
            _chunk("<think>internal"),
            _chunk(" reasoning</think>"),
            _chunk("Hello! "),
            _chunk("I am **ATHENA**."),
        ])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "Hi"},
        )

    assert resp.status_code == 200
    # General greeting must not send 75 database tool schemas
    assert "tools" not in captured_kwargs
    assert captured_kwargs["stream"] is True

    events = _parse_sse(resp.text)
    statuses = [e.get("status") for e in events if e.get("event") == "status"]
    assert "Connecting to ATHENA..." in statuses
    assert "Preparing a response..." in statuses
    assert "Delivering your answer..." in statuses
    assert "Checking campus records..." not in statuses

    streamed_tokens = "".join(e.get("token", "") for e in events if e.get("event") == "token")
    assert "<think>" not in streamed_tokens
    assert "internal" not in streamed_tokens
    assert "Hello! I am **ATHENA**." in streamed_tokens
    assert events[-1]["event"] == "done"
    assert events[-1]["reply"] == "Hello! I am **ATHENA**."


def test_general_query_timeout_emits_timed_out_error(monkeypatch, admin_token):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    mock_client = MagicMock()
    req = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=cast(Any, req))

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "Hi"},
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert events[-1]["event"] == "error"
    assert events[-1]["lifecycle_state"] == "TIMED_OUT"
    assert "timed out" in events[-1]["error"].lower()


def test_campus_query_uses_focused_tool_subset(monkeypatch, admin_token):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    captured_tools = []

    def fake_create(**kwargs):
        captured_tools.append(kwargs.get("tools"))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="There is **1 published timetable**.", tool_calls=None))]
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": "How many timetables are published?"},
        )

    assert resp.status_code == 200
    assert captured_tools[0] is not None
    assert 5 <= len(captured_tools[0]) <= 20
    tool_names = {t["function"]["name"] for t in captured_tools[0]}
    assert "get_published_timetables" in tool_names
    assert "execute_semantic_query" in tool_names
