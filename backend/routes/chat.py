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

import asyncio
import datetime
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import SessionLocal
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.chat import ChatConversation, ChatMessage
from backend.models.identity import User
from agents.common.formatter import sanitize_plain_english, safe_db_text
from agents.state.state import (
    ChatMessageDetail,
    ChatMessageRequest,
    ChatMessageResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationItemResponse,
)
from agents.supervisor.agent import execute_supervisor

logger = logging.getLogger("campus_ai.chat")

router = APIRouter(tags=["AI Agents"])


def get_nav_links_for_response(
    role: str,
    intent: Optional[str],
    tool_calls: List[Dict[str, Any]],
    reply: str,
) -> List[Dict[str, str]]:
    """
    Computes verified contextual navigation links based on verified role and execution results.
    Never relies on fragile client-side keyword guessing.
    """
    links: List[Dict[str, str]] = []
    tc_names = [tc.get("tool", "") for tc in (tool_calls or [])]
    reply_lower = (reply or "").lower()

    # 1. Placement / CDC links
    is_placement = any(
        "placement" in t or "drive" in t for t in tc_names
    ) or any(k in reply_lower for k in ["placement drive", "eligible placement", "placement cell", "recruitment drive", "placement opportunities"])
    if is_placement:
        if role == "STUDENT":
            links.append({"label": "Campus Placements Portal", "to": "/student/placements"})
        elif role in ("ADMIN", "SUPER_ADMIN"):
            links.append({"label": "CDC Placements Workspace", "to": "/admin/placements"})

    # 2. Timetable / Schedule links
    is_timetable = (
        intent in ("TIMETABLE_GENERATION", "TIMETABLE_READINESS")
        or any("timetable" in t or "class" in t for t in tc_names)
        or any(k in reply_lower for k in ["timetable", "class schedule", "lecture schedule", "my classes"])
    )
    if is_timetable:
        if role == "STUDENT":
            links.append({"label": "Open Student Timetable", "to": "/student/timetable"})
        elif role == "FACULTY":
            links.append({"label": "Open Faculty Timetable", "to": "/faculty/timetable"})
        elif role in ("ADMIN", "SUPER_ADMIN"):
            links.append({"label": "Open Timetable Engine", "to": "/admin/timetable"})

    # 3. Resources / Facility booking links
    is_resource = (
        intent in ("RESOURCE_BOOKING", "COMPOSITE_BOOKING_SUPERVISION")
        or any("resource" in t or "room" in t or "facility" in t for t in tc_names)
        or any(k in reply_lower for k in ["booking request", "facility availability", "room reservation"])
    )
    if is_resource:
        if role == "FACULTY":
            links.append({"label": "Campus Resources", "to": "/faculty/resources"})
        elif role in ("ADMIN", "SUPER_ADMIN"):
            links.append({"label": "Manage Resources", "to": "/admin/resources"})

    # 4. Events / Clubs links
    is_events = any("event" in t or "club" in t for t in tc_names) or any(k in reply_lower for k in ["campus event", "club activity", "upcoming event"])
    if is_events:
        if role == "STUDENT":
            links.append({"label": "Campus Events Dashboard", "to": "/student/events"})
        elif role == "FACULTY":
            links.append({"label": "Clubs & Events Management", "to": "/faculty/events"})
        elif role in ("ADMIN", "SUPER_ADMIN"):
            links.append({"label": "Events & Club Coordination", "to": "/admin/events"})

    # 5. Enrolled Courses links
    is_courses = any("course" in t or "subject" in t for t in tc_names) and role == "STUDENT"
    if is_courses:
        links.append({"label": "My Enrolled Courses", "to": "/student/courses"})

    return links


def determine_provider_badge(selected_agent: Optional[str], has_error: bool) -> str:
    if has_error:
        return "System Notice"
    if selected_agent in ("nvidia_nemotron", "nvidia"):
        return "Live Nemotron"
    return "Deterministic Engine"


def determine_outcome_state(result: Dict[str, Any]) -> str:
    if result.get("error") or not result.get("success", True):
        return "PROVIDER_ERROR"
    intent = result.get("intent")
    if intent == "CLARIFICATION_REQUIRED":
        return "CLARIFICATION_REQUIRED"
    if intent in ("UNSUPPORTED_OPERATION", "PERMISSION_DENIED"):
        return "PERMISSION_DENIED"
    reply_lower = (result.get("reply") or "").lower().strip()
    empty_phrases = [
        "no published placement drives found",
        "no records were found",
        "no matching records",
        "no scheduled academic holidays",
        "no upcoming classes",
        "no free periods found",
        "couldn't find any currently published timetable",
        "no published timetable is currently active",
    ]
    if any(phrase in reply_lower for phrase in empty_phrases) or (
        len(reply_lower) < 200 and "no classes scheduled" in reply_lower
    ):
        return "NO_RECORDS_FOUND"
    return "GROUNDED_ANSWER"


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
        content=safe_db_text(clean_message),
    )
    db.add(user_msg_record)
    try:
        db.flush()
    except Exception as flush_err:
        logger.warning("Failed to flush user message: %s", flush_err)
        db.rollback()

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
        content=safe_db_text(result["reply"]),
        intent=result.get("intent"),
        tool_calls=result.get("tool_calls", []),
        sources=result.get("sources", []),
        extra_metadata=metadata_payload if metadata_payload else None,
    )
    db.add(assistant_msg_record)

    # 4. Update conversation timestamp
    try:
        conv.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        db.commit()
    except Exception as commit_err:
        logger.warning("Failed to commit chat messages to database: %s", commit_err)
        db.rollback()

    nav_links = get_nav_links_for_response(
        current_user.role,
        result.get("intent"),
        result.get("tool_calls", []),
        result["reply"],
    )
    provider_badge = determine_provider_badge(
        result.get("selected_agent"),
        not result.get("success", True) or bool(result.get("error")),
    )
    outcome_state = determine_outcome_state(result)

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
        nav_links=nav_links,
        provider_badge=provider_badge,
        outcome_state=outcome_state,
    )


@router.post(
    "/agents/chat/stream",
    summary="Submit query to RIO Campus Assistant with real-time SSE streaming",
)
async def stream_chat_with_campus_assistant(
    request: Request,
    payload: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Real-time Server-Sent Events (SSE) token and status streaming for the Campus Assistant.
    Runs supervisor execution in an isolated thread with keepalive heartbeats, disconnect
    cancellation, correlation IDs, bounded timeout, and guaranteed terminal SSE events.
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
        if conv.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to post to this conversation.",
            )
    else:
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

    conv_id = conv.id
    user_id = current_user.id
    user_role = current_user.role
    request_id = uuid.uuid4().hex[:12]

    recent_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv_id)
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

    # Save user message
    user_msg_record = ChatMessage(
        conversation_id=conv_id,
        sender="user",
        content=safe_db_text(clean_message),
    )
    db.add(user_msg_record)
    try:
        db.commit()
    except Exception as e:
        logger.warning("[chat:%s] Failed to commit user message in stream: %s", request_id, e)
        db.rollback()

    cancel_event = threading.Event()

    def _run_supervisor_in_thread() -> Dict[str, Any]:
        with SessionLocal() as worker_db:
            worker_user = worker_db.query(User).filter(User.id == user_id).first()
            if not worker_user:
                return {
                    "reply": "",
                    "intent": "ERROR",
                    "success": False,
                    "error": "Authenticated user record not found.",
                }
            return execute_supervisor(
                message=clean_message,
                user=worker_user,
                db=worker_db,
                conversation_id=conv_id,
                conversation_history=conversation_history,
                cancel_check=cancel_event.is_set,
                request_id=request_id,
            )

    async def event_generator():
        t_start = time.perf_counter()
        logger.info("[chat:%s] Stream started (conv=%s, role=%s)", request_id, conv_id, user_role)
        try:
            # 1. Send initial status event
            yield f"data: {json.dumps({'event': 'status', 'status': 'Understanding your question...', 'request_id': request_id})}\n\n"

            # 2. Run supervisor in worker thread with keepalive heartbeats & disconnect check
            task = asyncio.create_task(asyncio.to_thread(_run_supervisor_in_thread))
            last_heartbeat = time.perf_counter()
            max_wait_seconds = 150.0

            while not task.done():
                if await request.is_disconnected():
                    cancel_event.set()
                    logger.info("[chat:%s] Client disconnected; cancelling worker", request_id)
                    return

                elapsed = time.perf_counter() - t_start
                if elapsed > max_wait_seconds:
                    cancel_event.set()
                    logger.warning("[chat:%s] Stream execution exceeded %.1fs timeout", request_id, max_wait_seconds)
                    yield f"data: {json.dumps({'event': 'error', 'error': 'The assistant took too long to respond. Please try again.', 'request_id': request_id})}\n\n"
                    return

                if time.perf_counter() - last_heartbeat >= 4.0:
                    yield ": keepalive\n\n"
                    last_heartbeat = time.perf_counter()

                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

            result = await task
            if cancel_event.is_set() or result.get("intent") == "CANCELLED":
                logger.info("[chat:%s] Worker cancelled", request_id)
                return

            if not result.get("success", True) and not result.get("reply"):
                err_msg = result.get("error") or "The assistant could not complete your request."
                yield f"data: {json.dumps({'event': 'error', 'error': err_msg, 'request_id': request_id})}\n\n"
                return

            yield f"data: {json.dumps({'event': 'status', 'status': 'Preparing your answer...', 'request_id': request_id})}\n\n"

            # 3. Stream tokens while preserving exact whitespace, indentation, and newlines for Markdown
            reply_text = result.get("reply") or ""
            chunks = re.findall(r"\S+[ \t]*|\n+|[ \t]+", reply_text) or [reply_text]
            for token_chunk in chunks:
                if await request.is_disconnected():
                    cancel_event.set()
                    return
                yield f"data: {json.dumps({'event': 'token', 'token': token_chunk})}\n\n"

            # 4. Save assistant response to DB
            metadata_payload: Dict[str, Any] = {}
            if result.get("proposal"):
                metadata_payload["proposal"] = result["proposal"]
            if result.get("action_type"):
                metadata_payload["action_type"] = result["action_type"]

            assistant_msg_record = ChatMessage(
                conversation_id=conv_id,
                sender="assistant",
                content=safe_db_text(reply_text),
                intent=result.get("intent"),
                tool_calls=result.get("tool_calls", []),
                sources=result.get("sources", []),
                extra_metadata=metadata_payload if metadata_payload else None,
            )
            db.add(assistant_msg_record)
            try:
                c = db.query(ChatConversation).filter(ChatConversation.id == conv_id).first()
                if c:
                    c.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                db.commit()
            except Exception as e:
                logger.warning("[chat:%s] Failed to commit assistant stream message: %s", request_id, e)
                db.rollback()

            nav_links = get_nav_links_for_response(
                user_role,
                result.get("intent"),
                result.get("tool_calls", []),
                reply_text,
            )
            provider_badge = determine_provider_badge(
                result.get("selected_agent"),
                not result.get("success", True) or bool(result.get("error")),
            )
            outcome_state = determine_outcome_state(result)

            # 5. Send terminal done event
            done_payload = {
                "event": "done",
                "request_id": request_id,
                "reply": reply_text,
                "intent": result.get("intent"),
                "selected_agent": result.get("selected_agent"),
                "tool_calls": result.get("tool_calls", []),
                "sources": result.get("sources", []),
                "proposal": result.get("proposal"),
                "action_type": result.get("action_type"),
                "success": result.get("success", True),
                "error": result.get("error"),
                "conversation_id": conv_id,
                "diagnostics": result.get("diagnostics"),
                "nav_links": nav_links,
                "provider_badge": provider_badge,
                "outcome_state": outcome_state,
            }
            logger.info("[chat:%s] Stream completed in %.2fs", request_id, time.perf_counter() - t_start)
            yield f"data: {json.dumps(done_payload)}\n\n"

        except Exception as exc:
            cancel_event.set()
            logger.error("[chat:%s] SSE stream error: %s", request_id, exc, exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'error': str(exc), 'request_id': request_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
