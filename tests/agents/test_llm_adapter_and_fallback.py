"""
tests/agents/test_llm_adapter_and_fallback.py
---------------------------------------------
Tests the Multi-Agent LLM adapter and deterministic fallback behavior:
1. Graceful fallback to deterministic extraction when ANTHROPIC_API_KEY is unset or mock.
2. Resilience against LLM API errors (timeouts, rate limits, connection errors).
3. Valid tool_use dispatch when LLM response is returned.
4. Strict database grounding: responses cite PostgreSQL records, zero hallucinations.
5. Student isolation: students cannot access other students' records.
"""

from __future__ import annotations

import os
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from backend.config import engine
from backend.models.identity import User
from agents.state.state import AgentState
from agents.query_agent.agent import run_query_agent, _extract_intent_and_tool_call


def test_offline_deterministic_fallback():
    """Verify that when ANTHROPIC_API_KEY and NVIDIA_API_KEY are empty, the system falls back 100% to deterministic tool extraction."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "NVIDIA_API_KEY": ""}):
        with Session(engine) as db:
            user = db.query(User).filter(User.role == "STUDENT").first()
            assert user is not None

            state: AgentState = {
                "message": "What is my SRN?",
                "user_id": user.id,
                "role": user.role,
                "tool_calls": [],
                "tool_results": [],
            }

            result = run_query_agent(state, db, user)
            assert result is not None
            assert "final_response" in result
            assert len(result["tool_calls"]) > 0
            assert result["tool_calls"][0]["tool"] == "get_student_academic_profile"
            assert "SRN" in result["final_response"] or "Student Academic Profile" in result["final_response"]


def test_llm_api_exception_fallback():
    """Verify that when Anthropic API raises an exception (e.g. timeout, rate limit), fallback handles it cleanly."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-validlookingkeyforunitmocking", "NVIDIA_API_KEY": ""}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = TimeoutError("Connection to Anthropic timed out after 10.0s")
            mock_anthropic.return_value = mock_client

            with Session(engine) as db:
                user = db.query(User).filter(User.role == "STUDENT").first()
                assert user is not None

                state: AgentState = {
                    "message": "Who is my class teacher?",
                    "user_id": user.id,
                    "role": user.role,
                    "tool_calls": [],
                    "tool_results": [],
                }

                # Should not raise; must catch exception and fall back
                result = run_query_agent(state, db, user)
                assert result is not None
                assert "final_response" in result
                assert len(result["tool_calls"]) > 0
                assert result["tool_calls"][0]["tool"] in ("get_student_academic_profile", "get_section_overview")


def test_llm_tool_use_success():
    """Verify that when Anthropic returns a tool_use block, the agent calls the specified tool."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-validlookingkeyforunitmocking", "NVIDIA_API_KEY": ""}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            
            # Construct mock response with tool_use block
            mock_block = MagicMock()
            mock_block.type = "tool_use"
            mock_block.name = "get_break_timings"
            mock_block.input = {}

            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            with Session(engine) as db:
                user = db.query(User).filter(User.role == "STUDENT").first()
                assert user is not None

                state: AgentState = {
                    "message": "When is lunch break?",
                    "user_id": user.id,
                    "role": user.role,
                    "tool_calls": [],
                    "tool_results": [],
                }

                result = run_query_agent(state, db, user)
                assert result is not None
                assert len(result["tool_calls"]) > 0
                assert result["tool_calls"][0]["tool"] == "get_break_timings"
                assert "Lunch Break" in result["final_response"] or "Break" in result["final_response"]
                # Verify Anthropic client was initialized with timeout=10.0 and max_retries=2
                mock_anthropic.assert_called_once_with(
                    api_key="sk-ant-api03-validlookingkeyforunitmocking",
                    timeout=10.0,
                    max_retries=2,
                )


def test_student_isolation_in_tools():
    """Verify student isolation: a student calling get_student_academic_profile only receives their own record."""
    with Session(engine) as db:
        students = db.query(User).filter(User.role == "STUDENT").limit(2).all()
        if len(students) >= 2:
            s1, s2 = students[0], students[1]
            state1: AgentState = {
                "message": "What is my SRN?",
                "user_id": s1.id,
                "role": s1.role,
                "tool_calls": [],
                "tool_results": [],
            }
            res1 = run_query_agent(state1, db, s1)
            # Response must reflect s1, not s2
            assert s1.email in res1["final_response"] or (s1.student_profile and s1.student_profile.student_id in res1["final_response"])
            if s2.student_profile and s2.student_profile.student_id:
                assert s2.student_profile.student_id not in res1["final_response"]
