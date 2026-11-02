"""
backend/routes/events.py
------------------------
REST API routes for Campus Events & Activities:
1. Public / Student / Faculty / Admin Event Discovery (Live, Today, Ongoing, Upcoming, Category)
2. Coordinator Event Creation & Draft Lifecycle (with venue conflict validation)
3. Approval Workflow (Submit -> Admin Approve/Reject with feedback)
4. Event Cancellation and Updates with Optimistic Locking
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.identity import User
from backend.models.events import CampusEvent
from backend.routes.auth import get_current_user
from backend.schemas.events import (
    EventApprovalRequest,
    EventCancelRequest,
    EventCreateRequest,
    EventResponse,
    EventUpdateRequest,
    EventVenueCheckRequest,
    EventVenueCheckResponse,
    EventVenueConflictItem,
)
from backend.services.event_service import (
    cancel_event,
    check_venue_availability,
    create_event,
    list_events_for_user,
    review_event,
    submit_event_for_approval,
    update_event,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "",
    response_model=List[EventResponse],
    summary="List visible campus events and club activities",
)
def get_events(
    category: Optional[str] = Query(None, description="Event category filter"),
    club_id: Optional[int] = Query(None, description="Filter by club"),
    time_filter: Optional[str] = Query(
        None, description="TODAY, ONGOING, THIS_WEEK, UPCOMING, COMPLETED"
    ),
    status: Optional[str] = Query(None, description="Status filter (Admin/Coordinator only)"),
    search: Optional[str] = Query(None, description="Text search title/description"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Retrieves events strictly honoring server-side RBAC and audience boundaries:
    - Students see only PUBLISHED events matching their department/audience.
    - Faculty see published events plus their own drafts/pending items.
    - Admin has visibility across all statuses including pending approvals.
    """
    return list_events_for_user(
        db=db,
        current_user=current_user,
        category=category,
        club_id=club_id,
        time_filter=time_filter,
        status_filter=status,
        search_query=search,
    )


@router.get(
    "/live",
    response_model=Dict[str, Any],
    summary="Live & Ongoing Events Dashboard Feed",
)
@router.get(
    "/live-dashboard",
    response_model=Dict[str, Any],
    include_in_schema=False,
)
def get_live_events_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns today's, ongoing, and upcoming campus events tailored to the caller.
    """
    ongoing = list_events_for_user(db=db, current_user=current_user, time_filter="ONGOING")
    today = list_events_for_user(db=db, current_user=current_user, time_filter="TODAY")
    upcoming = list_events_for_user(db=db, current_user=current_user, time_filter="UPCOMING")
    this_week = list_events_for_user(db=db, current_user=current_user, time_filter="THIS_WEEK")

    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ongoing_count": len(ongoing),
        "ongoing_events": ongoing,
        "today_count": len(today),
        "today_events": today,
        "upcoming_count": len(upcoming),
        "upcoming_events": upcoming[:10],
        "this_week_count": len(this_week),
        "this_week_events": this_week,
    }


@router.post(
    "/venue-check",
    response_model=EventVenueCheckResponse,
    summary="Verify room venue availability for a proposed time window",
)
def check_venue(
    payload: EventVenueCheckRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EventVenueCheckResponse:
    """
    Checks room conflicts against:
    1. Published timetable classes
    2. Active/pending resource bookings
    3. Other scheduled campus events
    """
    is_avail, raw_conflicts = check_venue_availability(
        db=db,
        room_id=payload.room_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        exclude_event_id=payload.exclude_event_id,
    )

    from backend.models.space_time import Room

    room = db.query(Room).filter(Room.id == payload.room_id).first()
    room_num = (room.room_number or f"#{payload.room_id}") if room else f"#{payload.room_id}"
    bldg_name = (room.building.name or "Main Campus") if (room and room.building and room.building.name) else "Main Campus"

    conflict_items = [
        EventVenueConflictItem(
            conflict_type=c["conflict_type"],
            type=c.get("type", c["conflict_type"]),
            conflict_id=c["conflict_id"],
            title=c["title"],
            reason=c.get("reason", c["title"]),
            start_time=c["start_time"],
            end_time=c["end_time"],
            details=c.get("details"),
        )
        for c in raw_conflicts
    ]

    return EventVenueCheckResponse(
        room_id=payload.room_id,
        room_number=room_num,
        building_name=bldg_name,
        is_available=is_avail,
        conflicts=conflict_items,
    )


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Get single event detail",
)
def get_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieves single event details with role boundary enforcement."""
    events = list_events_for_user(db=db, current_user=current_user)
    match = next((e for e in events if e["id"] == event_id), None)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campus event #{event_id} not found or not accessible.",
        )
    return match


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new campus event or club activity draft",
)
def create_new_event(
    payload: EventCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Creates an event draft (or publishes directly if caller holds EVENT_DIRECT_PUBLISH).
    Validates coordinator capability and checks venue availability.
    """
    event = create_event(db=db, creator=current_user, payload=payload)
    events = list_events_for_user(db=db, current_user=current_user)
    return next(e for e in events if e["id"] == event.id)


@router.put(
    "/{event_id}",
    response_model=EventResponse,
    summary="Update an existing event with optimistic locking",
)
def update_existing_event(
    event_id: int,
    payload: EventUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Updates event fields. Caller must be Admin or the assigned event coordinator."""
    event = update_event(db=db, updater=current_user, event_id=event_id, payload=payload)
    events = list_events_for_user(db=db, current_user=current_user)
    return next(e for e in events if e["id"] == event.id)


@router.post(
    "/{event_id}/submit",
    response_model=EventResponse,
    summary="Submit event draft for administrative approval",
)
def submit_for_approval(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Moves event to PENDING_APPROVAL and notifies administrators."""
    event = submit_event_for_approval(db=db, submitter=current_user, event_id=event_id)
    events = list_events_for_user(db=db, current_user=current_user)
    return next(e for e in events if e["id"] == event.id)


@router.post(
    "/{event_id}/review",
    response_model=EventResponse,
    summary="Approve or reject a pending event (Admin only)",
)
def review_pending_event(
    event_id: int,
    payload: EventApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Approves (publishes) or rejects an event with feedback."""
    event = review_event(
        db=db,
        reviewer=current_user,
        event_id=event_id,
        action=payload.action,
        reason=payload.reason,
        notes=payload.approval_notes,
    )
    events = list_events_for_user(db=db, current_user=current_user)
    return next(e for e in events if e["id"] == event.id)


@router.post(
    "/{event_id}/cancel",
    response_model=EventResponse,
    summary="Cancel a scheduled or published event",
)
def cancel_existing_event(
    event_id: int,
    payload: EventCancelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Cancels an event and notifies the target audience."""
    event = cancel_event(db=db, canceller=current_user, event_id=event_id, reason=payload.reason)
    events = list_events_for_user(db=db, current_user=current_user)
    return next(e for e in events if e["id"] == event.id)
