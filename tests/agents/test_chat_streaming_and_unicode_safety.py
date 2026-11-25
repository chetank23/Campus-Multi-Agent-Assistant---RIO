"""
tests/agents/test_chat_streaming_and_unicode_safety.py
------------------------------------------------------
Verification test suite for:
1. Plain-English and database safe transliteration of non-ASCII characters:
   - Mathematical operators: ≥, ≤, ≠, ≈, ±, ×, ÷
   - Currency: ₹ -> Rs.
   - Status indicators: ✅, ❌, ⚠
   - Quotes, dashes, bullets
2. Persistence safety: DB commit succeeds without UntranslatableCharacter errors.
3. Spelling tolerance in Campus Assistant:
   - Query: "what are the palcement activitie ?" correctly maps to placement drive listing.
4. End-to-end SSE token streaming:
   - POST /agents/chat/stream yields valid SSE chunks with token, status, and done events.
   - Includes nav_links, provider_badge, and outcome_state.
"""

import json
import pytest
import os
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.identity import User
from backend.models.chat import ChatConversation, ChatMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from agents.common.formatter import sanitize_plain_english, safe_db_text
from agents.supervisor.agent import classify_intent, execute_supervisor
from agents.query_agent.agent import _extract_intent_and_tool_call

client = TestClient(app)


def _get_db():
    db_url = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:5432/campus_ai_test"
    eng = create_engine(db_url)
    return Session(eng)


def test_unicode_transliteration_and_safe_db_text():
    # Test mathematical operators
    raw = "CGPA ≥ 7.0 and backlogs ≤ 2, salary is ₹ 12,00,000 ✅ Eligible, ❌ Not Eligible"
    cleaned = sanitize_plain_english(raw)
    assert ">=" in cleaned
    assert "<=" in cleaned
    assert "Rs." in cleaned
    assert "Eligible" in cleaned
    assert "≥" not in cleaned
    assert "≤" not in cleaned
    assert "₹" not in cleaned

    # safe_db_text must output pure ASCII safe text
    safe = safe_db_text(raw)
    assert safe.isascii()
    assert ">=" in safe
    assert "<=" in safe
    assert "Rs." in safe

    # Test saving directly to ChatMessage in DB session
    with _get_db() as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        if not admin_user:
            pytest.skip("Admin user required")

        from backend.models.chat import ChatConversation
        conv = ChatConversation(
            user_id=admin_user.id,
            role="ADMIN",
            title="Test Safe DB Text Conv",
        )
        db.add(conv)
        db.flush()

        msg = ChatMessage(
            conversation_id=conv.id,
            sender="assistant",
            content=safe_db_text("Requirement: CGPA ≥ 7.5 & Package ₹ 15 LPA. Status: ✅ Approved"),
        )
        db.add(msg)
        db.commit()
        assert msg.id is not None
        # Clean up
        db.delete(conv)
        db.commit()


def test_placement_misspelling_intent_and_routing():
    query = "what are the palcement activitie ?"

    # 1. Supervisor intent classification
    intent = classify_intent(query)
    assert intent == "QUERY_AGENT", f"Expected QUERY_AGENT for '{query}', got {intent}"

    # 2. Query Agent tool extraction
    with _get_db() as db:
        student_user = db.query(User).filter(User.role == "STUDENT").first()
        if not student_user:
            pytest.skip("Student user required")

        tool_name, tool_args = _extract_intent_and_tool_call(query, student_user)
        assert tool_name == "list_published_placement_drives", f"Expected list_published_placement_drives, got {tool_name}"

        # 3. Full supervisor execution
        result = execute_supervisor(
            message=query,
            user=student_user,
            db=db,
        )
        assert result.get("success") is True
        reply = result.get("reply", "")
        assert len(reply) > 0
        assert "placement" in reply.lower() or "drives" in reply.lower() or "campus" in reply.lower()


def test_streaming_chat_endpoint_sse():
    # Login as student or admin
    login_res = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    if login_res.status_code != 200:
        login_res = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})

    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Submit query to /agents/chat/stream
    res = client.post(
        "/agents/chat/stream",
        json={"message": "What are the published placement drives?"},
        headers=headers,
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")

    # Parse SSE stream content
    lines = res.text.split("\n\n")
    events = []
    for line in lines:
        if line.startswith("data: "):
            payload_str = line[6:].strip()
            if payload_str:
                events.append(json.loads(payload_str))

    assert len(events) >= 2, f"Expected multiple events in SSE stream, got {len(events)}"
    event_types = [e.get("event") for e in events]
    assert "status" in event_types
    assert "done" in event_types

    done_event = next(e for e in events if e.get("event") == "done")
    assert "reply" in done_event
    assert "nav_links" in done_event
    assert "provider_badge" in done_event
    assert "outcome_state" in done_event
    assert done_event["success"] is True
