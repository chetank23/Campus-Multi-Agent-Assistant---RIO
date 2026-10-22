"""
backend/routes/notifications.py
-------------------------------
REST API & SSE streaming endpoints for the RIO-MJP Notification system.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, List, Optional
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.config import ALGORITHM, SECRET_KEY
from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models.identity import User
from backend.models.workflow import Notification
from backend.schemas.notification import (
    BroadcastAnnouncementRequest,
    FacultyClassUpdateRequest,
    NotificationMarkAllReadResponse,
    NotificationMarkReadResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from backend.services.notification_service import (
    broadcast_announcement,
    notify_faculty_class_update,
    stream_broker,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _resolve_stream_user(
    token: Optional[str],
    db: Session,
    request: Request,
) -> User:
    """
    Resolves the authenticated user for SSE streaming from either query param ?token=...
    or Authorization: Bearer <token> header.
    """
    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required for notification stream",
        )

    try:
        payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user_id = int(sub)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")
    return user


# ── Notification Retrieval & Status ───────────────────────────────────────────

@router.get("", response_model=List[NotificationResponse])
def get_user_notifications(
    unread_only: bool = Query(False, description="Filter only unread notifications"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves notifications strictly for the authenticated user.
    Enforces privacy: no user can query another user's notifications.
    """
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read == False)

    notifications = (
        query.order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return notifications


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the exact unread notification count for the authenticated user.
    """
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
        .count()
    )
    return NotificationUnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", response_model=NotificationMarkReadResponse)
@router.post("/{notification_id}/read", response_model=NotificationMarkReadResponse)
def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Marks a specific notification as read.
    Enforces ownership: users can only mark their own notifications as read.
    """
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification #{notification_id} not found",
        )

    if notif.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to modify another user's notification.",
        )

    if not notif.is_read:
        notif.is_read = True
        db.commit()

    return NotificationMarkReadResponse(id=notif.id, is_read=True)


@router.post("/mark-all-read", response_model=NotificationMarkAllReadResponse)
def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Marks all unread notifications for the authenticated user as read.
    """
    updated_rows = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
        .update({Notification.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return NotificationMarkAllReadResponse(marked_count=updated_rows)


# ── Real-Time SSE Stream Endpoint ─────────────────────────────────────────────

@router.get("/stream")
async def notification_stream(
    request: Request,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Server-Sent Events (SSE) streaming endpoint.
    Pushes newly created notifications in real time directly to authenticated clients.
    Falls back gracefully with keep-alive heartbeat pings.
    """
    user = _resolve_stream_user(token, db, request)
    queue = await stream_broker.subscribe(user.id)

    # Initial unread count query
    initial_unread = (
        db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.is_read == False,
        )
        .count()
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial connected handshake
            init_data = json.dumps({"connected": True, "unread_count": initial_unread})
            yield f"event: connected\ndata: {init_data}\n\n"

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                try:
                    # Wait for up to 15 seconds for a notification payload
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    data = json.dumps(payload)
                    yield f"event: notification\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send periodic keep-alive heartbeat comment to prevent proxy timeout
                    yield ": ping\n\n"
        finally:
            await stream_broker.unsubscribe(user.id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Targeted Announcements & Updates ──────────────────────────────────────────

@router.post("/admin/broadcast")
def admin_broadcast(
    body: BroadcastAnnouncementRequest,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    ADMIN only: Broadcasts an announcement targeted to department, program, section, or campus.
    """
    success, message, count = broadcast_announcement(
        db=db,
        admin_user_id=admin_user.id,
        title=body.title,
        message=body.message,
        target_role=body.target_role,
        department_id=body.department_id,
        program_id=body.program_id,
        section_id=body.section_id,
    )
    return {"success": success, "message": message, "recipients_count": count}


@router.post("/faculty/class-update")
def faculty_class_update(
    body: FacultyClassUpdateRequest,
    faculty_user: User = Depends(require_role("FACULTY")),
    db: Session = Depends(get_db),
):
    """
    FACULTY only: Dispatches a class update/cancellation/room change to enrolled students.
    Enforces authorization: faculty must teach the course/section or be class teacher.
    """
    success, message, count = notify_faculty_class_update(
        db=db,
        faculty_user_id=faculty_user.id,
        course_id=body.course_id,
        section_id=body.section_id,
        update_type=body.update_type,
        title=body.title,
        message=body.message,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)

    return {"success": True, "message": message, "students_notified": count}
