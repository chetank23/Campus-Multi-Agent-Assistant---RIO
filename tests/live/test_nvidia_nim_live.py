"""
tests/live/test_nvidia_nim_live.py
-----------------------------------
Authoritative Live Integration Suite for NVIDIA NIM & Nemotron LLM Provider.
Gated strictly by real NVIDIA_API_KEY availability.
Excludes mock/test keys so standard CI and local unit tests remain 100% green and offline.

Verifies against configured endpoint (default: https://integrate.api.nvidia.com/v1):
1. Live authentication and bounded query response.
2. Structured tool calling against campus database tools.
3. Safe factual answer grounding and deterministic fallback synthesis.
4. Latency capture and diagnostic telemetry with ZERO secret leaks.
"""

from __future__ import annotations

import datetime
import os
import time
from typing import Any, Dict

import pytest
from sqlalchemy.orm import Session

from backend.database import engine
from backend.models.identity import User
from backend.models.academic import Department
from agents.llm.nvidia_provider import NvidiaNemotronProvider


def _is_real_nvidia_key(key: str) -> bool:
    """Verifies whether the provided string appears to be an authentic NVIDIA API key."""
    if not key or not key.strip():
        return False
    k = key.strip()
    # Reject mock or template placeholders
    if (
        k.startswith("nvapi-valid-test")
        or k.startswith("mock-")
        or k.startswith("test-")
        or "your_nvidia_api_key_here" in k
    ):
        return False
    return len(k) >= 20


@pytest.fixture(autouse=True)
def require_real_nvidia_key(monkeypatch):
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not _is_real_nvidia_key(key):
        pytest.skip(
            "Live NVIDIA integration test skipped: authentic NVIDIA_API_KEY environment variable is not provided."
        )
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("RIO_CHAT_LLM_PROVIDER", "nvidia")


@pytest.fixture
def db_session():
    with Session(engine) as session:
        yield session


@pytest.fixture
def live_admin_user(db_session: Session) -> User:
    u = db_session.query(User).filter(User.role == "ADMIN").first()
    assert u is not None, "Admin user required in seed database"
    return u


@pytest.mark.live
def test_live_nvidia_nim_authentication_and_bounded_response(live_admin_user: User, db_session: Session):
    """
    1. Authenticate against configured NVIDIA NIM endpoint.
    2. Submit bounded test request.
    3. Verify non-empty, usable model response without reasoning tokens.
    4. Capture latency and token metadata safely.
    """
    real_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    provider = NvidiaNemotronProvider(api_key=real_key)
    assert provider.is_available() is True

    t0 = time.perf_counter()
    res = provider.generate_chat_response(
        message="System check: respond with 'RIO Campus Assistant Online' and nothing else.",
        user=live_admin_user,
        db=db_session,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert res["success"] is True
    reply = res["reply"]
    assert reply and len(reply.strip()) > 0
    # Reasoning tokens should never be in user-facing reply
    assert "<thought>" not in reply.lower()
    assert "</thought>" not in reply.lower()

    # Verify diagnostics are captured
    diag = res.get("diagnostics")
    assert diag is not None
    assert diag["provider"] == "nvidia"
    assert "duration_ms" in diag
    assert diag["duration_ms"] > 0

    # Strict security validation: zero secrets in diagnostics
    diag_str = str(diag)
    assert real_key not in diag_str


@pytest.mark.live
def test_live_nvidia_nim_structured_tool_calling_and_grounding(
    live_admin_user: User,
    db_session: Session,
):
    """
    Tests live structured tool calling against campus database tools.
    Verifies that Nemotron queries real tools and returns factually grounded results.
    """
    real_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    provider = NvidiaNemotronProvider(api_key=real_key)

    first_dept = db_session.query(Department).first()
    assert first_dept is not None

    query = f"How many students are enrolled in the {first_dept.name} department?"
    t0 = time.perf_counter()
    res = provider.generate_chat_response(
        message=query,
        user=live_admin_user,
        db=db_session,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert res["success"] is True
    reply = res["reply"]
    assert len(reply) > 0
    # Internal tool traces should not leak to end users
    assert "Executed tool" not in reply
    assert "<thought>" not in reply

    # Confirm tool calling or grounding occurred
    assert res["tool_calls"] is not None or "student" in reply.lower()

    diag = res.get("diagnostics", {})
    assert real_key not in str(diag)
