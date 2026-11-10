"""
backend/routes/chat.py
----------------------
Authenticated REST endpoints for RIO-MJP Multi-Agent Campus Assistant.
Mounts:
- /agents/chat & /chat: Message submission with optional conversation persistence
- /agents/conversations: Conversation history management, listing, inspection, and deletion
Enforces strict JWT identity verification, role boundaries, and conversation ownership.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.chat import ChatConversation, ChatMessage
from backend.models.identity import User
from agents.state.state import (
    ChatMessageDetail,
    ChatMessageRequest,
    ChatMessageResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationItemResponse,
)
from agents.supervisor.agent import execute_supervisor

router = APIRouter(tags=["AI Agents"])


# ── Conversation Management Endpoints ─────────────────────────────────────────

@router.get(
    "/agents/conversations",
    response_model=List[ConversationItemResponse],
    summary="List authenticated user's chat conversations",
)
def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ConversationItemResponse]:
    """
    Returns recent conversations belonging to the authenticated user,
    ordered by most recently updated.
    """
    conversations = (
        db.query(ChatConversation)
        .filter(ChatConversation.user_id == current_user.id)
        .order_by(ChatConversation.updated_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for conv in conversations:
        count = db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).count()
        results.append(
            ConversationItemResponse(
                id=conv.id,
                title=conv.title,
                role=conv.role,
                created_at=conv.created_at.isoformat() if conv.created_at else "",
                updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
                message_count=count,
            )
        )
    return results


@router.post(
    "/agents/conversations",
    response_model=ConversationItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation session",
)
def create_conversation(
    payload: Optional[ConversationCreateRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationItemResponse:
    """Creates a new empty conversation for the authenticated user."""
    title = (payload.title if payload and payload.title else "").strip() or "New Conversation"
    conv = ChatConversation(
        user_id=current_user.id,
        role=current_user.role,
        title=title,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return ConversationItemResponse(
        id=conv.id,
        title=conv.title,
        role=conv.role,
        created_at=conv.created_at.isoformat() if conv.created_at else "",
        updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
        message_count=0,
    )


@router.get(
    "/agents/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation details and message history",
)
def get_conversation_detail(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    """
    Retrieves full message history for a conversation.
    Strictly verifies ownership: non-admin users cannot access other users' conversations.
    """
    conv = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    # Strict owner-only conversation privacy: even administrators cannot read other users' private conversations
    if conv.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to view this conversation.",
        )

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.id.asc())
        .all()
    )

    msg_items = [
        ChatMessageDetail(
            id=m.id,
            conversation_id=m.conversation_id,
            sender=m.sender,
            content=m.content,
            intent=m.intent,
            tool_calls=m.tool_calls,
            sources=m.sources,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in messages
    ]

    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        role=conv.role,
        created_at=conv.created_at.isoformat() if conv.created_at else "",
        updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
        messages=msg_items,
    )


@router.delete(
    "/agents/conversations/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a conversation session",
)
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deletes a conversation and its messages.
    Strictly enforces ownership.
    """
    conv = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    # Strict owner-only conversation privacy
    if conv.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to delete this conversation.",
        )

    db.delete(conv)
    db.commit()
    return {"ok": True, "detail": f"Conversation #{conversation_id} deleted successfully."}


# ── Chat Submission Endpoint ──────────────────────────────────────────────────

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
    - Manages conversation persistence and ownership.
    - Routes queries to the Query Agent using server-side tool execution.
    - Enforces strict role boundaries and published-only timetable constraints.
    - Gracefully handles unsupported intents.
    """
    clean_message = payload.message.strip()
    if not clean_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty or whitespace only.",
        )

    conv: Optional[ChatConversation] = None
    if payload.conversation_id:
        conv = db.query(ChatConversation).filter(ChatConversation.id == payload.conversation_id).first()
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation #{payload.conversation_id} was not found.",
            )
        # Strict owner-only conversation privacy
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to post to this conversation.",
            )
    else:
        # Auto-create conversation with summary title
        title_snippet = clean_message[:35].strip()
        if len(clean_message) > 35:
            title_snippet += "..."
        conv = ChatConversation(
            user_id=current_user.id,
            role=current_user.role,
            title=title_snippet or "New Conversation",
        )
        db.add(conv)
        db.flush()

    # 1. Fetch recent conversation history before adding the new message
    recent_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.id.desc())
        .limit(10)
        .all()
    )
    conversation_history = [
        {
            "id": m.id,
            "sender": m.sender,
            "content": m.content,
            "intent": m.intent,
            "tool_calls": m.tool_calls or [],
            "sources": m.sources or [],
        }
        for m in reversed(recent_msgs)
    ]

    # Record incoming user message
    user_msg_record = ChatMessage(
        conversation_id=conv.id,
        sender="user",
        content=clean_message,
    )
    db.add(user_msg_record)
    db.flush()

    # 2. Execute Supervisor Agent with conversation context
    result = execute_supervisor(
        message=clean_message,
        user=current_user,
        db=db,
        conversation_id=conv.id,
        conversation_history=conversation_history,
    )

    # 3. Record assistant response
    metadata_payload = {}
    if result.get("proposal"):
        metadata_payload["proposal"] = result["proposal"]
    if result.get("action_type"):
        metadata_payload["action_type"] = result["action_type"]

    assistant_msg_record = ChatMessage(
        conversation_id=conv.id,
        sender="assistant",
        content=result["reply"],
        intent=result.get("intent"),
        tool_calls=result.get("tool_calls", []),
        sources=result.get("sources", []),
        extra_metadata=metadata_payload if metadata_payload else None,
    )
    db.add(assistant_msg_record)

    # 4. Update conversation timestamp
    conv.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    db.commit()

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
        conversation_id=conv.id,
        diagnostics=result.get("diagnostics"),
    )


@router.get(
    "/agents/diagnostics",
    summary="Get AI Assistant and LLM provider diagnostics",
)
def get_assistant_diagnostics(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns development-only operational status of the AI Assistant and NVIDIA LLM integration.
    Never exposes API keys, tokens, or credentials.
    """
    from agents.llm.provider_interface import LLMProviderRegistry
    from agents.llm.nvidia_provider import NvidiaNemotronProvider

    provider = LLMProviderRegistry.get_provider()
    is_avail = provider.is_available()
    model_name = getattr(provider, "model", "N/A")
    provider_name = "nvidia" if isinstance(provider, NvidiaNemotronProvider) else "deterministic"
    llm_enabled = os.environ.get("RIO_CHAT_LLM_ENABLED", "false").strip().lower() in ("true", "1", "yes")

    return {
        "provider_configured": is_avail,
        "llm_mode_enabled": llm_enabled,
        "active_provider": provider_name,
        "active_model": model_name,
        "status": "ready" if is_avail else "offline",
    }
