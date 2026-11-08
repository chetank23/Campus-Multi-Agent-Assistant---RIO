"""
agents/tools/event_tools.py
---------------------------
LangGraph agent tools for Campus Events & Club Activity Coordination:
Directly backed by the authoritative event_service domain service.
Enforces strict server-side RBAC and audience privacy barriers.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.events import Club, CampusEvent
from backend.schemas.events import (
    EventCreateRequest,
    EventUpdateRequest,
)
from backend.services.event_service import (
    cancel_event,
    check_venue_availability,
    create_event,
    list_clubs,
    list_events_for_user,
    list_faculty_assigned_clubs,
    review_event,
    submit_event_for_approval,
    update_event,
)


def _parse_iso_or_str_datetime(val: Any) -> Optional[datetime.datetime]:
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val
    try:
        return datetime.datetime.fromisoformat(str(val))
    except Exception:
        # Try common format '%Y-%m-%d %H:%M'
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(str(val), fmt)
            except ValueError:
                continue
    return None


def list_visible_events_data(
    db: Session,
    user: User,
    category: Optional[str] = None,
    time_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Lists events visible to caller honoring role barriers."""
    events = list_events_for_user(
        db=db,
        current_user=user,
        category=category,
        time_filter=time_filter,
        search_query=search,
    )
    return {
        "count": len(events),
        "events": events,
    }


def get_published_event_details_data(
    db: Session,
    user: User,
    event_id: Optional[int] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieves full details of a specific visible event."""
    events = list_events_for_user(db=db, current_user=user, search_query=title)
    if event_id is not None:
        matched = next((e for e in events if e["id"] == event_id), None)
    elif title:
        matched = next((e for e in events if title.lower() in e["title"].lower()), None)
    else:
        matched = events[0] if events else None

    if not matched:
        return {
            "found": False,
            "message": f"Event #{event_id or title} not found or not published to your audience.",
        }

    return {
        "found": True,
        "event": matched,
    }


def get_ongoing_events_data(db: Session, user: User) -> Dict[str, Any]:
    """Retrieves currently ongoing campus events for caller."""
    events = list_events_for_user(db=db, current_user=user, time_filter="ONGOING")
    return {
        "count": len(events),
        "ongoing_events": events,
    }


def get_upcoming_events_data(
    db: Session,
    user: User,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieves upcoming campus events for caller."""
    events = list_events_for_user(
        db=db, current_user=user, time_filter="UPCOMING", category=category
    )
    return {
        "count": len(events),
        "upcoming_events": events[:15],
    }


def validate_event_data(
    db: Session,
    user: User,
    room_id: int,
    start_time: Any,
    end_time: Any,
    exclude_event_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Checks venue availability and reports any class/booking/event conflicts."""
    st = _parse_iso_or_str_datetime(start_time)
    et = _parse_iso_or_str_datetime(end_time)
    if not st or not et:
        return {"error": "Invalid start_time or end_time format."}

    try:
        is_avail, conflicts = check_venue_availability(
            db=db,
            room_id=room_id,
            start_time=st,
            end_time=et,
            exclude_event_id=exclude_event_id,
        )
        return {
            "room_id": room_id,
            "is_available": is_avail,
            "conflicts_count": len(conflicts),
            "conflicts": conflicts,
        }
    except Exception as exc:
        return {"error": str(exc)}


def create_event_draft_data(
    db: Session,
    user: User,
    title: str,
    category: str,
    start_time: Any,
    end_time: Any,
    room_id: Optional[int] = None,
    building_id: Optional[int] = None,
    venue_name: Optional[str] = None,
    description: Optional[str] = None,
    target_audience: str = "ALL",
    requires_approval: bool = True,
    club_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Creates a new event or club activity draft."""
    st = _parse_iso_or_str_datetime(start_time)
    et = _parse_iso_or_str_datetime(end_time)
    if not st or not et:
        return {"error": "Invalid start_time or end_time format."}

    # Normalize target audience
    aud_cand = target_audience.upper() if target_audience else "ALL"
    aud: Literal["ALL", "STUDENT", "FACULTY", "DEPARTMENT_ONLY", "MEMBERS_ONLY"]
    if aud_cand == "STUDENT":
        aud = "STUDENT"
    elif aud_cand == "FACULTY":
        aud = "FACULTY"
    elif aud_cand == "DEPARTMENT_ONLY":
        aud = "DEPARTMENT_ONLY"
    elif aud_cand == "MEMBERS_ONLY":
        aud = "MEMBERS_ONLY"
    else:
        aud = "ALL"

    try:
        req = EventCreateRequest(
            title=title,
            description=description,
            category=category,
            club_id=club_id,
            start_time=st,
            end_time=et,
            room_id=room_id,
            building_id=building_id,
            venue_name=venue_name,
            target_audience=aud,
            requires_approval=requires_approval,
        )
        ev = create_event(db=db, creator=user, payload=req)
        return {
            "success": True,
            "event_id": ev.id,
            "title": ev.title,
            "category": ev.category,
            "status": ev.status,
            "start_time": ev.start_time.isoformat(),
            "end_time": ev.end_time.isoformat(),
            "requires_approval": ev.requires_approval,
        }
    except Exception as exc:
        return {"error": getattr(exc, "detail", str(exc))}


def update_event_draft_data(
    db: Session,
    user: User,
    event_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    start_time: Any = None,
    end_time: Any = None,
    room_id: Optional[int] = None,
    venue_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates permitted draft or published event details."""
    st = _parse_iso_or_str_datetime(start_time) if start_time else None
    et = _parse_iso_or_str_datetime(end_time) if end_time else None

    try:
        req = EventUpdateRequest(
            title=title,
            description=description,
            start_time=st,
            end_time=et,
            room_id=room_id,
            venue_name=venue_name,
        )
        ev = update_event(db=db, updater=user, event_id=event_id, payload=req)
        return {
            "success": True,
            "event_id": ev.id,
            "title": ev.title,
            "status": ev.status,
            "version": ev.version,
            "start_time": ev.start_time.isoformat(),
            "end_time": ev.end_time.isoformat(),
        }
    except Exception as exc:
        return {"error": getattr(exc, "detail", str(exc))}


def submit_event_for_approval_data(db: Session, user: User, event_id: int) -> Dict[str, Any]:
    """Submits draft event for admin review."""
    try:
        ev = submit_event_for_approval(db=db, submitter=user, event_id=event_id)
        return {
            "success": True,
            "event_id": ev.id,
            "status": ev.status,
            "message": f"Event '{ev.title}' submitted for administrative approval.",
        }
    except Exception as exc:
        return {"error": getattr(exc, "detail", str(exc))}


def approve_event_data(
    db: Session,
    user: User,
    event_id: int,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Admin approves pending event."""
    try:
        ev = review_event(db=db, reviewer=user, event_id=event_id, action="APPROVE", notes=notes)
        return {
            "success": True,
            "event_id": ev.id,
            "status": ev.status,
            "message": f"Event '{ev.title}' approved and published.",
        }
    except Exception as exc:
        return {"error": getattr(exc, "detail", str(exc))}


def reject_event_data(
    db: Session,
    user: User,
    event_id: int,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Admin rejects pending event."""
    try:
        ev = review_event(db=db, reviewer=user, event_id=event_id, action="REJECT", reason=reason)
        return {
            "success": True,
            "event_id": ev.id,
            "status": ev.status,
            "reason": ev.rejection_reason,
            "message": f"Event '{ev.title}' rejected.",
        }
    except Exception as exc:
        return {"error": getattr(exc, "detail", str(exc))}


def publish_event_data(db: Session, user: User, event_id: int) -> Dict[str, Any]:
    """Publishes an approved or authorized event."""
    # If admin, approve/publish directly
    if user.role == "ADMIN":
        return approve_event_data(db=db, user=user, event_id=event_id)
    # If faculty has direct publish capability
    event = db.query(CampusEvent).filter(CampusEvent.id == event_id).first()
    if not event:
        return {"error": f"Event #{event_id} not found."}
    if event.coordinator_id != user.id:
        return {"error": "Access denied: You are not the coordinator for this event."}

    from backend.services.event_service import check_user_has_capability

    has_dp = check_user_has_capability(
        db, user, "EVENT_DIRECT_PUBLISH", "CLUB" if event.club_id else None, event.club_id
    )
    if not has_dp:
        return {"error": "Direct publishing requires EVENT_DIRECT_PUBLISH capability."}

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    event.status = "PUBLISHED"
    event.published_at = now
    db.commit()
    return {
        "success": True,
        "event_id": event.id,
        "status": event.status,
        "message": f"Event '{event.title}' published directly.",
    }


def cancel_event_data(
    db: Session,
    user: User,
    event_id: int,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Cancels a scheduled or published event."""
    try:
        ev = cancel_event(db=db, canceller=user, event_id=event_id, reason=reason)
        return {
            "success": True,
            "event_id": ev.id,
            "status": ev.status,
            "message": f"Event '{ev.title}' cancelled.",
        }
    except Exception as exc:
        return {"error": getattr(exc, "detail", str(exc))}


def list_my_clubs_data(db: Session, user: User) -> Dict[str, Any]:
    """Lists clubs assigned to current user."""
    if user.role == "ADMIN":
        clubs = list_clubs(db=db, status_filter="ACTIVE")
    elif user.role == "FACULTY":
        clubs = list_faculty_assigned_clubs(db=db, faculty_user=user)
    else:
        return {"error": "Students do not have coordinator club assignments."}

    club_list = [
        {
            "id": c.id,
            "name": c.name,
            "code": c.code,
            "category": c.category,
            "description": c.description,
            "status": c.status,
        }
        for c in clubs
    ]
    return {
        "count": len(club_list),
        "clubs": club_list,
    }


def list_club_activities_data(
    db: Session,
    user: User,
    club_id: Optional[int] = None,
    club_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Lists activities of a club honoring role visibility."""
    cid = club_id
    if not cid and club_name:
        club = db.query(Club).filter(Club.name.ilike(f"%{club_name.strip()}%")).first()
        if club:
            cid = club.id

    events = list_events_for_user(db=db, current_user=user, club_id=cid)
    return {
        "club_id": cid,
        "count": len(events),
        "activities": events,
    }


def create_club_activity_data(
    db: Session,
    user: User,
    club_id: int,
    title: str,
    category: str = "CLUB_ACTIVITY",
    start_time: Any = None,
    end_time: Any = None,
    room_id: Optional[int] = None,
    venue_name: Optional[str] = None,
    description: Optional[str] = None,
    requires_approval: bool = True,
) -> Dict[str, Any]:
    """Creates a new activity draft under an assigned club."""
    return create_event_draft_data(
        db=db,
        user=user,
        title=title,
        category=category,
        start_time=start_time,
        end_time=end_time,
        room_id=room_id,
        venue_name=venue_name,
        description=description,
        target_audience="ALL",
        requires_approval=requires_approval,
        club_id=club_id,
    )


def update_club_activity_data(
    db: Session,
    user: User,
    event_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    start_time: Any = None,
    end_time: Any = None,
    room_id: Optional[int] = None,
    venue_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates permitted fields of a club activity."""
    return update_event_draft_data(
        db=db,
        user=user,
        event_id=event_id,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        room_id=room_id,
        venue_name=venue_name,
    )

