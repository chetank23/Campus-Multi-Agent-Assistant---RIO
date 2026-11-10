"""
agents/state/state.py
---------------------
Shared request-scoped AgentState schema and communication contracts
as specified in PROJECT_SPECIFICATION.md Section 8.1.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
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
    proposal: Optional[Dict[str, Any]]
    action_type: Optional[str]
    error: Optional[str]
    sources: Optional[List[str]]
    conversation_id: Optional[int]
    conversation_history: Optional[List[Dict[str, Any]]]


# ── Pydantic Schemas for API Contracts ────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=1500,
        description="The natural language query or instruction submitted by the user.",
    )
    conversation_id: Optional[int] = Field(
        None,
        description="Optional persistent conversation ID to append message to.",
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
    proposal: Optional[Dict[str, Any]] = None
    action_type: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    conversation_id: Optional[int] = None
    diagnostics: Optional[Dict[str, Any]] = None


class ConversationCreateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200, description="Optional title for the conversation.")


class ConversationItemResponse(BaseModel):
    id: int
    title: str
    role: str
    created_at: str
    updated_at: str
    message_count: int


class ChatMessageDetail(BaseModel):
    id: int
    conversation_id: int
    sender: str
    content: str
    intent: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    sources: Optional[List[str]] = None
    created_at: str


class ConversationDetailResponse(BaseModel):
    id: int
    title: str
    role: str
    created_at: str
    updated_at: str
    messages: List[ChatMessageDetail]
