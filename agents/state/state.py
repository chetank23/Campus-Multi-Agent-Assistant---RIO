"""
agents/state/state.py
---------------------
Shared request-scoped AgentState schema and communication contracts
as specified in PROJECT_SPECIFICATION.md Section 8.1.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class AgentState(TypedDict, total=False):
    """
    Shared LangGraph state schema (PROJECT_SPECIFICATION.md §8.1).
    All state is request-scoped; no mutable conversation state is persisted across requests.
    """
    user_id: int
    role: str
    department_id: Optional[int]
    message: str
    intent: Optional[str]
    selected_agent: Optional[str]
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    final_response: Optional[str]
    error: Optional[str]


# ── Pydantic Schemas for API Contracts ────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=1500,
        description="The natural language query or instruction submitted by the user.",
    )


class ChatToolCallRecord(BaseModel):
    tool: str
    args: Dict[str, Any]


class ChatMessageResponse(BaseModel):
    reply: str
    intent: Optional[str] = None
    selected_agent: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
