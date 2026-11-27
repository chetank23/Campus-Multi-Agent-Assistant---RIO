"""
tests/api/test_intelligent_assistant_behavior.py
------------------------------------------------
Tests for natural, context-aware conversational intelligence of the RIO Campus Assistant:
1. General conversation & technical help (no unnecessary DB tool calls, no rigid refusal boilerplate)
2. Campus data queries & dynamic tool selection
3. Contextual multi-turn follow-ups (pronouns, comparisons, semester narrowing)
4. Ambiguous queries requesting natural clarification
5. Grounding, security, role isolation, empty-result handling, and markdown preservation
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.config import engine
from backend.main import app
from backend.models import User
from agents.common.formatter import sanitize_conversational_markdown
from agents.llm.nvidia_provider import NvidiaNemotronProvider

client = TestClient(app)


@pytest.fixture(scope="module")
def auth_tokens():
    admin_r = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    fac_r = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    stu_r = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert admin_r.status_code == 200
    assert fac_r.status_code == 200
    assert stu_r.status_code == 200
    return {
        "ADMIN": admin_r.json()["access_token"],
        "FACULTY": fac_r.json()["access_token"],
        "STUDENT": stu_r.json()["access_token"],
    }


def _assert_no_internal_leaks(reply: str):
    assert reply and reply.strip()
    forbidden = [
        "Executed tool",
        "execute_semantic_query",
        "get_published_timetables",
        "GROUNDED_ANSWER",
        "Database records matching your inquiry",
        "I cannot:\n- Use pre-trained knowledge",
        "Answer general-knowledge questions",
    ]
    for f in forbidden:
        assert f not in reply, f"Forbidden internal/restrictive phrase '{f}' found in reply: {reply}"


@pytest.mark.parametrize(
    "prompt_text,mocked_answer",
    [
        ("Hi.", "Hello! I'm RIO, your Campus Assistant. How can I help you today?"),
        (
            "Can you answer everything?",
            "I can help with both general questions—like explaining concepts, writing code, or brainstorming—and live campus information such as timetables, rooms, faculty, and events.",
        ),
        (
            "Explain artificial intelligence.",
            "Artificial intelligence (AI) is the field of computer science focused on building systems capable of tasks that typically require human intelligence, such as reasoning, pattern recognition, and language understanding.",
        ),
        (
            "What is machine learning?",
            "Machine learning is a subset of AI where algorithms learn patterns from data to make predictions or decisions without being explicitly programmed for every rule.",
        ),
        (
            "Help me write Python code.",
            "Here is a clean Python example:\n\n```python\ndef greet(name: str) -> str:\n    return f'Hello, {name}!'\n```",
        ),
    ],
)
def test_general_conversation_with_llm_provider_no_unnecessary_db_calls(
    monkeypatch, auth_tokens, prompt_text, mocked_answer
):
    """General knowledge, greetings, and coding help answer directly without invoking DB tools."""
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    mock_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=mocked_answer, tool_calls=None))]
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
        resp = client.post(
            "/agents/chat",
            headers={"Authorization": f"Bearer {auth_tokens['STUDENT']}"},
            json={"message": prompt_text},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    _assert_no_internal_leaks(data["reply"])
    assert data["tool_calls"] == [], "General conversation must not invoke database tools"
    assert "RIO Database Grounding" not in data["sources"]
    if "```python" in mocked_answer:
        assert "```python" in data["reply"], "Markdown code blocks must be preserved"


def test_offline_greeting_and_general_query_are_natural(monkeypatch, auth_tokens):
    """Offline fallback greeting and unknown responses must be natural, never rigid capability dumps."""
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "false")

    hi_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {auth_tokens['STUDENT']}"},
        json={"message": "Hi."},
    )
    assert hi_resp.status_code == 200
    _assert_no_internal_leaks(hi_resp.json()["reply"])

    gk_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {auth_tokens['STUDENT']}"},
        json={"message": "Explain quantum entanglement."},
    )
    assert gk_resp.status_code == 200
    _assert_no_internal_leaks(gk_resp.json()["reply"])


def test_ambiguous_questions_request_natural_clarification(auth_tokens):
    """Genuinely ambiguous questions without context ask for clarification cleanly."""
    for q in ["Which faculty are available tomorrow?", "Show the timetable."]:
        resp = client.post(
            "/agents/chat",
            headers={"Authorization": f"Bearer {auth_tokens['ADMIN']}"},
            json={"message": q},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        _assert_no_internal_leaks(data["reply"])
        assert "?" in data["reply"]


def test_contextual_followup_conversation_retains_memory(auth_tokens):
    """Multi-turn conversation retains conversation_id and resolves follow-ups."""
    r1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {auth_tokens['ADMIN']}"},
        json={"message": "Show me all published timetables."},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    conv_id = d1["conversation_id"]
    _assert_no_internal_leaks(d1["reply"])

    r2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {auth_tokens['ADMIN']}"},
        json={"message": "Which department has the most?", "conversation_id": conv_id},
    )
    assert r2.status_code == 200
    _assert_no_internal_leaks(r2.json()["reply"])

    r3 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {auth_tokens['ADMIN']}"},
        json={"message": "What about semester 7?", "conversation_id": conv_id},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    _assert_no_internal_leaks(d3["reply"])
    assert any(tc.get("tool") == "get_published_timetables" for tc in d3.get("tool_calls", []))


def test_sanitize_conversational_markdown_preserves_rich_formatting():
    """Preserves Markdown tables, bold, lists, and code blocks while stripping emojis & think tags."""
    raw = (
        "<think>internal</think>"
        "**Summary** 🚀\n\n"
        "| Dept | Status |\n| --- | --- |\n| AI & DS | PUBLISHED |\n\n"
        "```python\nprint('hello')\n```"
    )
    cleaned = sanitize_conversational_markdown(raw)
    assert "<think>" not in cleaned
    assert "🚀" not in cleaned
    assert "**Summary**" in cleaned
    assert "| --- | --- |" in cleaned
    assert "```python" in cleaned


def test_system_prompt_supports_general_and_campus_intelligence():
    provider = NvidiaNemotronProvider(api_key="nvapi-test-key-0001")
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "ADMIN").first()
        assert user is not None
        prompt = provider.build_system_prompt(user)
    assert "GENERAL CONVERSATION" in prompt
    assert "WITHOUT calling any database tool" in prompt
    assert "NEVER mention internal tool names" in prompt
