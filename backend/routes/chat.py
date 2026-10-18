"""
backend/routes/chat.py
----------------------
Authenticated REST endpoint for RIO-MJP Multi-Agent Assistant.
Mounts /agents/chat and /chat for natural-language campus queries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.identity import User
from agents.state.state import ChatMessageRequest, ChatMessageResponse
from agents.supervisor.agent import execute_supervisor

router = APIRouter(tags=["AI Agents"])


@router.post(
    "/agents/chat",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit query to RIO Campus Assistant",
)
@router.post(
    "/chat",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def chat_with_campus_assistant(
    payload: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    """
    Submits a natural language message to the Supervisor Agent.
    - Resolves caller identity securely via JWT session.
    - Routes queries to the Query Agent using server-side tool execution.
    - Enforces strict role boundaries and published-only timetable constraints.
    - Gracefully handles unsupported intents (e.g. conversational scheduling / booking mutations).
    """
    clean_message = payload.message.strip()
    if not clean_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty or whitespace only.",
        )

    result = execute_supervisor(
        message=clean_message,
        user=current_user,
        db=db,
    )

    return ChatMessageResponse(
        reply=result["reply"],
        intent=result.get("intent"),
        selected_agent=result.get("selected_agent"),
        tool_calls=result.get("tool_calls", []),
        sources=result.get("sources", []),
        proposal=result.get("proposal"),
        action_type=result.get("action_type"),
        success=result.get("success", True),
        error=result.get("error"),
    )
