"""
backend/services/event_service.py
---------------------------------
Comprehensive domain service for:
1. Scoped Coordinator Capabilities (EVENT_COORDINATOR, CLUB_COORDINATOR, EVENT_DIRECT_PUBLISH)
2. Student & Faculty Activity Clubs
3. Campus Events & Club Activities with Deterministic Lifecycle & Venue Validation
4. Audit Logging and Audience Notifications
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.academic import Department, Program, Batch, Student, Faculty
from backend.models.space_time import Building, Room, TimeSlot
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.resources import Resource, ResourceBooking
from backend.models.workflow import AuditLog, Notification
from backend.models.events import CoordinatorCapability, Club, CampusEvent
from backend.schemas.events import (
    CapabilityAssignRequest,
    ClubCreateRequest,
    ClubUpdateRequest,
    EventCreateRequest,
    EventUpdateRequest,
)
from backend.services.notification_service import create_notification, create_bulk_notifications
from backend.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# 1. Scoped Capabilities Service
# ---------------------------------------------------------------------------

def check_user_has_capability(
    db: Session,
    user: User,
    capability: str,
    scope_type: Optional[str] = None,
    scope_id: Optional[int] = None,
) -> bool:
    """
    Evaluates whether a user holds an active, non-expired capability.
    - Administrators automatically satisfy administrative capabilities.
    - Non-admins must match capability name, active status, not expired,
      and scope (if GLOBAL or matching specific scope_id).
    """
    if user.role == "ADMIN":
        return True

    now = utc_now()
    query = (
        db.query(CoordinatorCapability)
        .filter(
            CoordinatorCapability.user_id == user.id,
            CoordinatorCapability.capability == capability,
            CoordinatorCapability.is_active == True,
            or_(
                CoordinatorCapability.starts_at.is_(None),
                CoordinatorCapability.starts_at <= now,
            ),
            or_(
                CoordinatorCapability.expires_at.is_(None),
                CoordinatorCapability.expires_at > now,
            ),
        )
    )

    caps = query.all()
    if not caps:
        return False

    if scope_type is None and scope_id is None:
        return True

    for c in caps:
        if c.scope_type == "GLOBAL":
            return True
        if scope_type and c.scope_type == scope_type:
            if scope_id is None or c.scope_id is None or c.scope_id == scope_id:
                return True

    return False


def assign_capability(
    db: Session,
    assigner: User,
    payload: CapabilityAssignRequest,
) -> CoordinatorCapability:
    """Assigns or reactivates a coordinator capability for a target user."""
    if assigner.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can assign coordinator capabilities.",
        )

    target_user = db.query(User).filter(User.id == payload.user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User #{payload.user_id} not found.",
        )

    if target_user.role == "STUDENT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coordinator capabilities cannot be assigned to student accounts.",
        )

    # Validate scope entity if specified
    if payload.scope_type == "CLUB" and payload.scope_id:
        club = db.query(Club).filter(Club.id == payload.scope_id).first()
        if not club:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Club #{payload.scope_id} not found.",
            )
    elif payload.scope_type == "DEPARTMENT" and payload.scope_id:
        dept = db.query(Department).filter(Department.id == payload.scope_id).first()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department #{payload.scope_id} not found.",
            )

    # Check for existing matching active assignment
    existing = (
        db.query(CoordinatorCapability)
        .filter(
            CoordinatorCapability.user_id == payload.user_id,
            CoordinatorCapability.capability == payload.capability,
            CoordinatorCapability.scope_type == payload.scope_type,
            CoordinatorCapability.scope_id == payload.scope_id,
            CoordinatorCapability.is_active == True,
        )
        .first()
    )

    now = utc_now()
    if existing:
        existing.starts_at = payload.starts_at or existing.starts_at
        existing.expires_at = payload.expires_at
        existing.assigned_by = assigner.id
        existing.updated_at = now
        record = existing
    else:
        record = CoordinatorCapability(
            user_id=payload.user_id,
            capability=payload.capability,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            is_active=True,
            starts_at=payload.starts_at,
            expires_at=payload.expires_at,
            assigned_by=assigner.id,
            created_at=now,
            updated_at=now,
        )
        db.add(record)

    db.flush()

    # Audit logging
    db.add(
        AuditLog(
            user_id=assigner.id,
            action="CAPABILITY_ASSIGNED",
            entity_type="CoordinatorCapability",
            entity_id=record.id,
            new_value={
                "target_user_id": target_user.id,
                "capability": payload.capability,
                "scope_type": payload.scope_type,
                "scope_id": payload.scope_id,
            },
        )
    )

    # Notification to the assigned user
    create_notification(
        db=db,
        user_id=target_user.id,
        title=f"Coordinator Capability Assigned: {payload.capability}",
        message=(
            f"You have been designated with capability '{payload.capability}' "
            f"(Scope: {payload.scope_type}"
            + (f" #{payload.scope_id}" if payload.scope_id else "")
            + ")."
        ),
        type="CAPABILITY_ASSIGNED",
        link="/faculty/my-clubs" if payload.capability == "CLUB_COORDINATOR" else "/faculty/events",
        entity_type="CoordinatorCapability",
        entity_id=record.id,
    )

    db.commit()
    db.refresh(record)
    return record


def revoke_capability(
    db: Session,
    revoker: User,
    capability_id: int,
    reason: Optional[str] = None,
) -> CoordinatorCapability:
    """Revokes an active coordinator capability immediately."""
    if revoker.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can revoke coordinator capabilities.",
        )

    record = db.query(CoordinatorCapability).filter(CoordinatorCapability.id == capability_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coordinator capability #{capability_id} not found.",
        )

    now = utc_now()
    record.is_active = False
    record.revoked_at = now
    record.revoked_by = revoker.id
    record.revocation_reason = reason or "Revoked by administrator."
    record.updated_at = now
    db.flush()

    db.add(
        AuditLog(
            user_id=revoker.id,
            action="CAPABILITY_REVOKED",
            entity_type="CoordinatorCapability",
            entity_id=record.id,
            old_value={"is_active": True},
            new_value={"is_active": False, "reason": record.revocation_reason},
        )
    )

    create_notification(
        db=db,
        user_id=record.user_id,
        title=f"Capability Revoked: {record.capability}",
        message=f"Your '{record.capability}' assignment has been revoked: {record.revocation_reason}",
        type="CAPABILITY_REVOKED",
        link="/faculty",
        entity_type="CoordinatorCapability",
        entity_id=record.id,
    )

    db.commit()
    db.refresh(record)
    return record


def list_capabilities(
    db: Session,
    user_id: Optional[int] = None,
    capability: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[CoordinatorCapability]:
    """Lists coordinator capabilities filtered by user, type, or active state."""
    query = db.query(CoordinatorCapability)
    if user_id is not None:
        query = query.filter(CoordinatorCapability.user_id == user_id)
    if capability:
        query = query.filter(CoordinatorCapability.capability == capability)
    if is_active is not None:
        query = query.filter(CoordinatorCapability.is_active == is_active)
    return query.order_by(CoordinatorCapability.id.desc()).all()


# ---------------------------------------------------------------------------
# 2. Club Management Service
# ---------------------------------------------------------------------------

def create_club(db: Session, creator: User, payload: ClubCreateRequest) -> Club:
    """Creates a new campus club or student organization."""
    if creator.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can register campus clubs.",
        )

    # Uniqueness checks
    existing_name = db.query(Club).filter(Club.name.ilike(payload.name.strip())).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A club with name '{payload.name}' already exists.",
        )

    existing_code = db.query(Club).filter(Club.code.ilike(payload.code.strip())).first()
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A club with code '{payload.code}' already exists.",
        )

    now = utc_now()
    club = Club(
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        category=payload.category.strip().upper(),
        description=payload.description.strip() if payload.description else None,
        status="ACTIVE",
        created_by=creator.id,
        created_at=now,
        updated_at=now,
    )
    db.add(club)
    db.flush()

    db.add(
        AuditLog(
            user_id=creator.id,
            action="CLUB_CREATED",
            entity_type="Club",
            entity_id=club.id,
            new_value={"name": club.name, "code": club.code, "category": club.category},
        )
    )

    db.commit()
    db.refresh(club)
    return club


def update_club(db: Session, updater: User, club_id: int, payload: ClubUpdateRequest) -> Club:
    """Updates club profile or status."""
    if updater.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update club profiles.",
        )

    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Club #{club_id} not found.",
        )

    old_vals = {"name": club.name, "category": club.category, "status": club.status}

    if payload.name:
        dup = db.query(Club).filter(Club.name.ilike(payload.name.strip()), Club.id != club_id).first()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A club named '{payload.name}' already exists.",
            )
        club.name = payload.name.strip()

    if payload.category:
        club.category = payload.category.strip().upper()
    if payload.description is not None:
        club.description = payload.description.strip() if payload.description else None
    if payload.status:
        club.status = payload.status

    club.updated_at = utc_now()
    db.flush()

    db.add(
        AuditLog(
            user_id=updater.id,
            action="CLUB_UPDATED",
            entity_type="Club",
            entity_id=club.id,
            old_value=old_vals,
            new_value={"name": club.name, "category": club.category, "status": club.status},
        )
    )

    db.commit()
    db.refresh(club)
    return club


def list_clubs(db: Session, category: Optional[str] = None, status_filter: Optional[str] = None) -> List[Club]:
    """Lists clubs matching optional category or status filters."""
    query = db.query(Club)
    if category:
        query = query.filter(Club.category == category.upper())
    if status_filter:
        query = query.filter(Club.status == status_filter.upper())
    return query.order_by(Club.name.asc()).all()


def get_club(db: Session, club_id: int) -> Optional[Club]:
    return db.query(Club).filter(Club.id == club_id).first()


def list_faculty_assigned_clubs(db: Session, faculty_user: User) -> List[Club]:
    """Returns all active clubs assigned to a faculty member via CLUB_COORDINATOR capability."""
    now = utc_now()
    assigned_club_ids = (
        db.query(CoordinatorCapability.scope_id)
        .filter(
            CoordinatorCapability.user_id == faculty_user.id,
            CoordinatorCapability.capability == "CLUB_COORDINATOR",
            CoordinatorCapability.scope_type == "CLUB",
            CoordinatorCapability.is_active == True,
            or_(
                CoordinatorCapability.starts_at.is_(None),
                CoordinatorCapability.starts_at <= now,
            ),
            or_(
                CoordinatorCapability.expires_at.is_(None),
                CoordinatorCapability.expires_at > now,
            ),
        )
        .all()
    )

    club_ids = [cid[0] for cid in assigned_club_ids if cid[0] is not None]
    if not club_ids:
        return []

    return db.query(Club).filter(Club.id.in_(club_ids), Club.status == "ACTIVE").order_by(Club.name.asc()).all()


# ---------------------------------------------------------------------------
# 3. Venue Conflict Verification Service
# ---------------------------------------------------------------------------

def check_venue_availability(
    db: Session,
    room_id: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    exclude_event_id: Optional[int] = None,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Checks venue availability across three distinct operational layers:
    1. Timetable classes scheduled in published timetable versions.
    2. Approved or pending resource bookings.
    3. Other active campus events scheduled in the same room.
    """
    if end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be strictly after start time.",
        )

    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room #{room_id} not found in campus facilities.",
        )

    conflicts: List[Dict[str, Any]] = []

    # 1. Check published timetable classes
    # TimeSlot day matching start_time day-of-week (e.g. MONDAY)
    target_day = start_time.strftime("%A").upper()
    t_start = start_time.time()
    t_end = end_time.time()

    pub_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
        .first()
    )

    if pub_version:
        tt_entries = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableEntry.version_id == pub_version.id,
                TimetableEntry.room_id == room_id,
                TimetableEntry.status != "CANCELLED",
                TimeSlot.day == target_day,
                TimeSlot.start_time < t_end,
                TimeSlot.end_time > t_start,
            )
            .all()
        )

        for entry in tt_entries:
            slot = entry.slot
            course = entry.course
            slot_st = slot.start_time.strftime("%H:%M:%S") if (slot and slot.start_time) else "00:00:00"
            slot_et = slot.end_time.strftime("%H:%M:%S") if (slot and slot.end_time) else "00:00:00"
            conflicts.append({
                "conflict_type": "TIMETABLE_CLASS",
                "type": "TIMETABLE_CLASS",
                "conflict_id": entry.id,
                "title": f"Class: {course.course_code if course else 'Course'} in {room.room_number}",
                "reason": f"Class: {course.course_code if course else 'Course'} in {room.room_number}",
                "start_time": f"{start_time.strftime('%Y-%m-%d')} {slot_st}",
                "end_time": f"{start_time.strftime('%Y-%m-%d')} {slot_et}",
                "details": f"Scheduled class for section #{entry.section_id}",
            })

    # 2. Check approved/pending resource bookings for this room/resource
    # Find matching resource mapped to this room (if any)
    resource = None
    if room.room_number:
        resource = (
            db.query(Resource)
            .filter(
                or_(
                    Resource.name.ilike(f"%{room.room_number}%"),
                    Resource.location.ilike(f"%{room.room_number}%"),
                ),
                Resource.status == "ACTIVE",
            )
            .first()
        )

    if resource:
        ev_date = start_time.date()
        bookings = (
            db.query(ResourceBooking)
            .filter(
                ResourceBooking.resource_id == resource.id,
                ResourceBooking.date == ev_date,
                ResourceBooking.status.in_(["APPROVED", "PENDING"]),
                ResourceBooking.start_time < t_end,
                ResourceBooking.end_time > t_start,
            )
            .all()
        )

        for b in bookings:
            b_st = b.start_time.strftime("%H:%M:%S") if b.start_time else "00:00:00"
            b_et = b.end_time.strftime("%H:%M:%S") if b.end_time else "00:00:00"
            conflicts.append({
                "conflict_type": "RESOURCE_BOOKING",
                "type": "RESOURCE_BOOKING",
                "conflict_id": b.id,
                "title": f"Resource Booking: {resource.name} ({b.status})",
                "reason": f"Resource Booking: {resource.name} ({b.status})",
                "start_time": f"{b.date} {b_st}",
                "end_time": f"{b.date} {b_et}",
                "details": f"Booking purpose: {b.purpose or 'N/A'}",
            })

    # 3. Check other scheduled campus events in the same room
    ev_query = (
        db.query(CampusEvent)
        .filter(
            CampusEvent.room_id == room_id,
            CampusEvent.status.in_(["APPROVED", "PUBLISHED", "ONGOING", "PENDING_APPROVAL"]),
            CampusEvent.start_time < end_time,
            CampusEvent.end_time > start_time,
        )
    )

    if exclude_event_id:
        ev_query = ev_query.filter(CampusEvent.id != exclude_event_id)

    event_conflicts = ev_query.all()
    for ev in event_conflicts:
        conflicts.append({
            "conflict_type": "CAMPUS_EVENT",
            "type": "CAMPUS_EVENT",
            "conflict_id": ev.id,
            "title": f"Event: {ev.title} ({ev.status})",
            "reason": f"Event: {ev.title} ({ev.status})",
            "start_time": ev.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": ev.end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "details": f"Organizer: {ev.organizer_name or 'Campus'}, Category: {ev.category}",
        })

    is_available = len(conflicts) == 0
    return is_available, conflicts


# ---------------------------------------------------------------------------
# 4. Campus Events & Activities Lifecycle Service
# ---------------------------------------------------------------------------

def _resolve_live_status(event: CampusEvent, now: Optional[datetime.datetime] = None) -> str:
    """Computes dynamic operational status for a published event."""
    if event.status in ("CANCELLED", "REJECTED", "ARCHIVED", "DRAFT", "PENDING_APPROVAL"):
        return event.status
    if not now:
        now = utc_now()
    if now < event.start_time:
        return "UPCOMING"
    elif event.start_time <= now <= event.end_time:
        return "ONGOING"
    else:
        return "COMPLETED"


def create_event(
    db: Session,
    creator: User,
    payload: EventCreateRequest,
) -> CampusEvent:
    """
    Creates a new campus event or club activity.
    Enforces coordinator capability boundaries and direct publishing authorization.
    """
    if creator.role == "STUDENT":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students are not authorized to create campus events or club activities.",
        )

    # Coordinator capability verification for faculty
    if creator.role == "FACULTY":
        if payload.club_id:
            # Must hold CLUB_COORDINATOR capability for this specific club
            has_club_cap = check_user_has_capability(
                db=db,
                user=creator,
                capability="CLUB_COORDINATOR",
                scope_type="CLUB",
                scope_id=payload.club_id,
            )
            if not has_club_cap:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: You are not an authorized coordinator for Club #{payload.club_id}.",
                )
        else:
            # Institutional event: must hold EVENT_COORDINATOR capability
            has_event_cap = check_user_has_capability(
                db=db,
                user=creator,
                capability="EVENT_COORDINATOR",
            )
            if not has_event_cap:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Faculty require an active EVENT_COORDINATOR capability to create institutional events.",
                )

    # Direct publishing capability check
    # If requires_approval is False, caller must hold EVENT_DIRECT_PUBLISH or be ADMIN
    has_direct_pub = check_user_has_capability(
        db=db,
        user=creator,
        capability="EVENT_DIRECT_PUBLISH",
        scope_type="CLUB" if payload.club_id else None,
        scope_id=payload.club_id if payload.club_id else None,
    )

    if not payload.requires_approval and not has_direct_pub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Direct publishing is restricted to coordinators with an explicit EVENT_DIRECT_PUBLISH capability.",
        )

    # Check venue availability if room_id is specified
    if payload.room_id:
        is_avail, conflicts = check_venue_availability(
            db=db,
            room_id=payload.room_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        if not is_avail:
            first_c = conflicts[0]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Venue conflict: {first_c['title']} ({first_c['start_time']} - {first_c['end_time']}).",
            )

    now = utc_now()
    # Determine initial status
    if not payload.requires_approval and has_direct_pub:
        initial_status = "PUBLISHED"
        pub_at = now
        app_by = creator.id
        app_at = now
    else:
        initial_status = "DRAFT"
        pub_at = None
        app_by = None
        app_at = None

    event = CampusEvent(
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        category=payload.category.strip().upper(),
        club_id=payload.club_id,
        organizer_name=payload.organizer_name.strip() if payload.organizer_name else creator.name,
        coordinator_id=creator.id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        timezone=payload.timezone,
        building_id=payload.building_id,
        room_id=payload.room_id,
        venue_name=payload.venue_name.strip() if payload.venue_name else None,
        is_online=payload.is_online,
        online_link=payload.online_link.strip() if payload.online_link else None,
        target_audience=payload.target_audience,
        target_department_id=payload.target_department_id,
        target_program_id=payload.target_program_id,
        target_batch_id=payload.target_batch_id,
        target_year=payload.target_year,
        instructions=payload.instructions.strip() if payload.instructions else None,
        requires_approval=payload.requires_approval,
        status=initial_status,
        approved_by=app_by,
        approved_at=app_at,
        published_at=pub_at,
        created_by=creator.id,
        updated_by=creator.id,
        version=1,
        created_at=now,
        updated_at=now,
    )

    db.add(event)
    db.flush()

    # Audit logging
    action_name = "EVENT_DIRECT_PUBLISHED" if initial_status == "PUBLISHED" else "EVENT_DRAFT_CREATED"
    db.add(
        AuditLog(
            user_id=creator.id,
            action=action_name,
            entity_type="CampusEvent",
            entity_id=event.id,
            new_value={
                "title": event.title,
                "category": event.category,
                "status": event.status,
                "club_id": event.club_id,
                "start_time": event.start_time.isoformat(),
                "end_time": event.end_time.isoformat(),
            },
        )
    )

    # If directly published, notify relevant audience
    if initial_status == "PUBLISHED":
        _notify_event_published(db=db, event=event)

    db.commit()
    db.refresh(event)
    return event


def update_event(
    db: Session,
    updater: User,
    event_id: int,
    payload: EventUpdateRequest,
) -> CampusEvent:
    """Updates permitted event fields with optimistic concurrency version checking."""
    event = db.query(CampusEvent).filter(CampusEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campus event #{event_id} not found.",
        )

    # Permission check: must be Admin or the assigned event coordinator
    if updater.role != "ADMIN" and event.coordinator_id != updater.id:
        # If club activity, verify if updater has active coordinator capability on this club
        if event.club_id and check_user_has_capability(
            db, updater, "CLUB_COORDINATOR", scope_type="CLUB", scope_id=event.club_id
        ):
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to edit this event.",
            )

    # Optimistic locking check
    if payload.version is not None and payload.version != event.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict: Event #{event_id} was modified by another transaction (expected v{payload.version}, found v{event.version}).",
        )

    old_vals = {
        "title": event.title,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "room_id": event.room_id,
        "status": event.status,
    }

    new_start = payload.start_time or event.start_time
    new_end = payload.end_time or event.end_time
    new_room = payload.room_id if payload.room_id is not None else event.room_id

    # If timing or venue changed, validate venue availability
    if (new_start != event.start_time or new_end != event.end_time or new_room != event.room_id) and new_room:
        is_avail, conflicts = check_venue_availability(
            db=db,
            room_id=new_room,
            start_time=new_start,
            end_time=new_end,
            exclude_event_id=event.id,
        )
        if not is_avail:
            first_c = conflicts[0]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Venue conflict: {first_c['title']} ({first_c['start_time']} - {first_c['end_time']}).",
            )

    # Apply updates
    if payload.title:
        event.title = payload.title.strip()
    if payload.description is not None:
        event.description = payload.description.strip() if payload.description else None
    if payload.category:
        event.category = payload.category.strip().upper()
    if payload.organizer_name is not None:
        event.organizer_name = payload.organizer_name.strip() if payload.organizer_name else None

    event.start_time = new_start
    event.end_time = new_end
    event.room_id = new_room
    if payload.building_id is not None:
        event.building_id = payload.building_id
    if payload.venue_name is not None:
        event.venue_name = payload.venue_name.strip() if payload.venue_name else None
    if payload.is_online is not None:
        event.is_online = payload.is_online
    if payload.online_link is not None:
        event.online_link = payload.online_link.strip() if payload.online_link else None
    if payload.target_audience:
        event.target_audience = payload.target_audience
    if payload.target_department_id is not None:
        event.target_department_id = payload.target_department_id
    if payload.target_program_id is not None:
        event.target_program_id = payload.target_program_id
    if payload.target_batch_id is not None:
        event.target_batch_id = payload.target_batch_id
    if payload.target_year is not None:
        event.target_year = payload.target_year
    if payload.instructions is not None:
        event.instructions = payload.instructions.strip() if payload.instructions else None

    event.version += 1
    event.updated_by = updater.id
    event.updated_at = utc_now()
    db.flush()

    db.add(
        AuditLog(
            user_id=updater.id,
            action="EVENT_UPDATED",
            entity_type="CampusEvent",
            entity_id=event.id,
            old_value=old_vals,
            new_value={
                "title": event.title,
                "start_time": event.start_time.isoformat(),
                "end_time": event.end_time.isoformat(),
                "room_id": event.room_id,
                "version": event.version,
            },
        )
    )

    # Notify audience if event is published and venue/time was changed
    if event.status == "PUBLISHED" and (old_vals["start_time"] != event.start_time.isoformat() or old_vals["room_id"] != event.room_id):
        _notify_event_updated(db=db, event=event)

    db.commit()
    db.refresh(event)
    return event


def submit_event_for_approval(db: Session, submitter: User, event_id: int) -> CampusEvent:
    """Submits a draft or rejected event for administrator review."""
    event = db.query(CampusEvent).filter(CampusEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campus event #{event_id} not found.",
        )

    if submitter.role != "ADMIN" and event.coordinator_id != submitter.id:
        if not (event.club_id and check_user_has_capability(db, submitter, "CLUB_COORDINATOR", "CLUB", event.club_id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to submit this event.",
            )

    if event.status not in ("DRAFT", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit event in status '{event.status}'. Must be DRAFT or REJECTED.",
        )

    # Re-verify venue conflict prior to submission
    if event.room_id:
        is_avail, conflicts = check_venue_availability(
            db=db,
            room_id=event.room_id,
            start_time=event.start_time,
            end_time=event.end_time,
            exclude_event_id=event.id,
        )
        if not is_avail:
            first_c = conflicts[0]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot submit event with venue conflict: {first_c['title']} ({first_c['start_time']} - {first_c['end_time']}).",
            )

    old_status = event.status
    event.status = "PENDING_APPROVAL"
    event.updated_by = submitter.id
    event.updated_at = utc_now()
    event.version += 1
    db.flush()

    db.add(
        AuditLog(
            user_id=submitter.id,
            action="EVENT_SUBMITTED_FOR_APPROVAL",
            entity_type="CampusEvent",
            entity_id=event.id,
            old_value={"status": old_status},
            new_value={"status": "PENDING_APPROVAL"},
        )
    )

    # Notify all administrators of pending event
    admins = db.query(User).filter(User.role == "ADMIN", User.is_active == True).all()
    for adm in admins:
        create_notification(
            db=db,
            user_id=adm.id,
            title=f"Event Approval Pending: {event.title}",
            message=f"Coordinator {submitter.name} submitted event '{event.title}' scheduled for {event.start_time.strftime('%Y-%m-%d %H:%M')}.",
            type="EVENT_PENDING_APPROVAL",
            link="/admin/events",
            entity_type="CampusEvent",
            entity_id=event.id,
        )

    db.commit()
    db.refresh(event)
    return event


def review_event(
    db: Session,
    reviewer: User,
    event_id: int,
    action: str,  # 'APPROVE' or 'REJECT'
    reason: Optional[str] = None,
    notes: Optional[str] = None,
) -> CampusEvent:
    """Administrator review of a pending event."""
    if reviewer.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can approve or reject events.",
        )

    event = db.query(CampusEvent).filter(CampusEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campus event #{event_id} not found.",
        )

    if event.status != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot review event in status '{event.status}'. Must be PENDING_APPROVAL.",
        )

    now = utc_now()
    old_status = event.status

    if action == "APPROVE":
        # Final venue check before approving
        if event.room_id:
            is_avail, conflicts = check_venue_availability(
                db=db,
                room_id=event.room_id,
                start_time=event.start_time,
                end_time=event.end_time,
                exclude_event_id=event.id,
            )
            if not is_avail:
                first_c = conflicts[0]
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot approve event due to active venue conflict: {first_c['title']}.",
                )

        event.status = "PUBLISHED"
        event.approved_by = reviewer.id
        event.approved_at = now
        event.published_at = now
        event.approval_notes = notes.strip() if notes else None
        event.rejection_reason = None
        action_name = "EVENT_APPROVED"

        # Notify coordinator
        create_notification(
            db=db,
            user_id=event.coordinator_id,
            title=f"Event Approved: {event.title}",
            message=f"Your event '{event.title}' has been approved and published to the campus calendar.",
            type="EVENT_APPROVED",
            link="/faculty/events",
            entity_type="CampusEvent",
            entity_id=event.id,
        )

        # Notify audience
        _notify_event_published(db=db, event=event)

    elif action == "REJECT":
        event.status = "REJECTED"
        event.rejection_reason = reason.strip() if reason else "Rejected by administrator without specific comments."
        event.approval_notes = notes.strip() if notes else None
        action_name = "EVENT_REJECTED"

        # Notify coordinator
        create_notification(
            db=db,
            user_id=event.coordinator_id,
            title=f"Event Rejected: {event.title}",
            message=f"Your event submission '{event.title}' was rejected: {event.rejection_reason}",
            type="EVENT_REJECTED",
            link="/faculty/events",
            entity_type="CampusEvent",
            entity_id=event.id,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review action '{action}'. Must be APPROVE or REJECT.",
        )

    event.updated_by = reviewer.id
    event.updated_at = now
    event.version += 1
    db.flush()

    db.add(
        AuditLog(
            user_id=reviewer.id,
            action=action_name,
            entity_type="CampusEvent",
            entity_id=event.id,
            old_value={"status": old_status},
            new_value={"status": event.status, "reason": event.rejection_reason, "notes": event.approval_notes},
        )
    )

    db.commit()
    db.refresh(event)
    return event


def cancel_event(
    db: Session,
    canceller: User,
    event_id: int,
    reason: Optional[str] = None,
) -> CampusEvent:
    """Cancels a scheduled or published event."""
    event = db.query(CampusEvent).filter(CampusEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campus event #{event_id} not found.",
        )

    if canceller.role != "ADMIN" and event.coordinator_id != canceller.id:
        if not (event.club_id and check_user_has_capability(db, canceller, "CLUB_COORDINATOR", "CLUB", event.club_id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to cancel this event.",
            )

    if event.status in ("CANCELLED", "COMPLETED", "ARCHIVED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel event already in status '{event.status}'.",
        )

    old_status = event.status
    event.status = "CANCELLED"
    event.rejection_reason = reason or "Cancelled by coordinator."
    event.updated_by = canceller.id
    event.updated_at = utc_now()
    event.version += 1
    db.flush()

    db.add(
        AuditLog(
            user_id=canceller.id,
            action="EVENT_CANCELLED",
            entity_type="CampusEvent",
            entity_id=event.id,
            old_value={"status": old_status},
            new_value={"status": "CANCELLED", "reason": event.rejection_reason},
        )
    )

    # Notify audience of cancellation if the event was published
    if old_status in ("PUBLISHED", "APPROVED", "ONGOING"):
        _notify_event_cancelled(db=db, event=event, reason=event.rejection_reason)

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# 5. Event Audience Querying & Notifications Helpers
# ---------------------------------------------------------------------------

def _notify_event_published(db: Session, event: CampusEvent) -> None:
    """Emits notifications to the target audience for a published event."""
    audience = event.target_audience
    user_ids: List[int] = []

    if audience in ("ALL", "STUDENT"):
        q = db.query(Student.user_id)
        if event.target_department_id:
            q = q.join(Department, Student.department_id == Department.id).filter(Department.id == event.target_department_id)
        if event.target_batch_id:
            q = q.filter(Student.batch_id == event.target_batch_id)
        user_ids.extend([u[0] for u in q.all()])

    if audience in ("ALL", "FACULTY"):
        fq = db.query(Faculty.user_id)
        if event.target_department_id:
            fq = fq.filter(Faculty.department_id == event.target_department_id)
        user_ids.extend([u[0] for u in fq.all()])

    unique_uids = list(set(user_ids))
    if unique_uids:
        club_prefix = f"[{event.club.name}] " if event.club else ""
        notifs = [
            Notification(
                user_id=uid,
                title=f"New Event: {club_prefix}{event.title}",
                message=f"{event.category}: Scheduled on {event.start_time.strftime('%Y-%m-%d %H:%M')}. {event.description or ''}".strip(),
                type="EVENT_PUBLISHED",
                link="/events",
                entity_type="CampusEvent",
                entity_id=event.id,
                is_read=False,
            )
            for uid in unique_uids
        ]
        create_bulk_notifications(db=db, notifications=notifs)


def _notify_event_updated(db: Session, event: CampusEvent) -> None:
    """Emits update notification to audience."""
    _notify_event_published(db, event)


def _notify_event_cancelled(db: Session, event: CampusEvent, reason: Optional[str]) -> None:
    """Emits cancellation notice to audience."""
    audience = event.target_audience
    user_ids: List[int] = []

    if audience in ("ALL", "STUDENT"):
        q = db.query(Student.user_id)
        if event.target_department_id:
            q = q.join(Department, Student.department_id == Department.id).filter(Department.id == event.target_department_id)
        user_ids.extend([u[0] for u in q.all()])

    if audience in ("ALL", "FACULTY"):
        fq = db.query(Faculty.user_id)
        if event.target_department_id:
            fq = fq.filter(Faculty.department_id == event.target_department_id)
        user_ids.extend([u[0] for u in fq.all()])

    unique_uids = list(set(user_ids))
    if unique_uids:
        reason_txt = f" Reason: {reason}" if reason else ""
        notifs = [
            Notification(
                user_id=uid,
                title=f"Event Cancelled: {event.title}",
                message=f"Notice: The event scheduled for {event.start_time.strftime('%Y-%m-%d')} has been cancelled.{reason_txt}",
                type="EVENT_CANCELLED",
                link="/events",
                entity_type="CampusEvent",
                entity_id=event.id,
                is_read=False,
            )
            for uid in unique_uids
        ]
        create_bulk_notifications(db=db, notifications=notifs)


def list_events_for_user(
    db: Session,
    current_user: User,
    category: Optional[str] = None,
    club_id: Optional[int] = None,
    time_filter: Optional[str] = None,  # 'TODAY', 'ONGOING', 'THIS_WEEK', 'UPCOMING', 'COMPLETED'
    status_filter: Optional[str] = None,
    search_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieves events strictly honoring role boundaries, audience policies, and live status.
    - STUDENT: strictly sees PUBLISHED events matching their department/audience.
      Draft, pending, and rejected events are never exposed to students.
    - FACULTY: sees all published events plus their own drafts/pending events.
    - ADMIN: sees all events, including pending approval queue.
    """
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)
    week_end = today_start + datetime.timedelta(days=7)

    query = db.query(CampusEvent)

    # 1. Role and audience security barrier
    if current_user.role == "STUDENT":
        # Strictly published events only
        query = query.filter(CampusEvent.status.in_(["PUBLISHED", "APPROVED"]))

        # Audience filter
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if student:
            dept_id = student.department_id
            batch_id = student.batch_id
            query = query.filter(
                or_(
                    CampusEvent.target_audience.in_(["ALL", "STUDENT"]),
                    and_(
                        CampusEvent.target_audience == "DEPARTMENT_ONLY",
                        CampusEvent.target_department_id == dept_id,
                    ),
                    and_(
                        CampusEvent.target_batch_id.isnot(None),
                        CampusEvent.target_batch_id == batch_id,
                    ),
                )
            )
        else:
            query = query.filter(CampusEvent.target_audience.in_(["ALL", "STUDENT"]))

    elif current_user.role == "FACULTY":
        if status_filter:
            if status_filter in ("DRAFT", "PENDING_APPROVAL", "REJECTED"):
                # Faculty can only view their own drafts/pending events
                query = query.filter(
                    CampusEvent.status == status_filter,
                    CampusEvent.coordinator_id == current_user.id,
                )
            else:
                query = query.filter(CampusEvent.status == status_filter)
        else:
            # Default faculty view: published events + own drafts
            query = query.filter(
                or_(
                    CampusEvent.status.in_(["PUBLISHED", "APPROVED"]),
                    CampusEvent.coordinator_id == current_user.id,
                )
            )

    elif current_user.role == "ADMIN":
        if status_filter:
            query = query.filter(CampusEvent.status == status_filter)

    # 2. Category & Club filters
    if category:
        query = query.filter(CampusEvent.category == category.upper())
    if club_id:
        query = query.filter(CampusEvent.club_id == club_id)

    # 3. Search query
    if search_query:
        sq = f"%{search_query.strip()}%"
        query = query.filter(
            or_(
                CampusEvent.title.ilike(sq),
                CampusEvent.description.ilike(sq),
                CampusEvent.organizer_name.ilike(sq),
            )
        )

    # 4. Time filter
    if time_filter == "TODAY":
        query = query.filter(CampusEvent.start_time >= today_start, CampusEvent.start_time < today_end)
    elif time_filter == "ONGOING":
        query = query.filter(CampusEvent.start_time <= now, CampusEvent.end_time >= now)
    elif time_filter == "THIS_WEEK":
        query = query.filter(CampusEvent.start_time >= today_start, CampusEvent.start_time < week_end)
    elif time_filter == "UPCOMING":
        query = query.filter(CampusEvent.start_time > now)
    elif time_filter == "COMPLETED":
        query = query.filter(CampusEvent.end_time < now)

    events = query.order_by(CampusEvent.start_time.asc()).all()

    # Format into enriched response dicts
    results = []
    for ev in events:
        live_st = _resolve_live_status(ev, now)
        bldg_name = ev.building.name if ev.building else None
        room_num = ev.room.room_number if ev.room else None
        dept_name = ev.department.name if ev.department else None
        club_name = ev.club.name if ev.club else None

        results.append({
            "id": ev.id,
            "title": ev.title,
            "description": ev.description,
            "category": ev.category,
            "club_id": ev.club_id,
            "club_name": club_name,
            "organizer_name": ev.organizer_name,
            "coordinator_id": ev.coordinator_id,
            "coordinator_name": ev.coordinator.name if ev.coordinator else "Coordinator",
            "coordinator_email": ev.coordinator.email if ev.coordinator else "",
            "start_time": ev.start_time.isoformat(),
            "end_time": ev.end_time.isoformat(),
            "timezone": ev.timezone,
            "building_id": ev.building_id,
            "building_name": bldg_name,
            "room_id": ev.room_id,
            "room_number": room_num,
            "venue_name": ev.venue_name,
            "is_online": ev.is_online,
            "online_link": ev.online_link,
            "target_audience": ev.target_audience,
            "target_department_id": ev.target_department_id,
            "target_department_name": dept_name,
            "target_program_id": ev.target_program_id,
            "target_batch_id": ev.target_batch_id,
            "target_year": ev.target_year,
            "instructions": ev.instructions,
            "requires_approval": ev.requires_approval,
            "status": ev.status,
            "live_status": live_st,
            "rejection_reason": ev.rejection_reason,
            "cancellation_reason": ev.rejection_reason if ev.status == "CANCELLED" else None,
            "approval_notes": ev.approval_notes,
            "approved_by": ev.approved_by,
            "approved_at": ev.approved_at.isoformat() if ev.approved_at else None,
            "published_at": ev.published_at.isoformat() if ev.published_at else None,
            "created_by": ev.created_by,
            "version": ev.version,
            "created_at": ev.created_at.isoformat(),
            "updated_at": ev.updated_at.isoformat(),
        })

    return results
