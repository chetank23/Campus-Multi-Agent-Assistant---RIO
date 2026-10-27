"""
backend/services/resource_booking_service.py
---------------------------------------------
Core domain logic for the Resource Allocation Engine:
  - Strict interval overlap conflict detection:
      requested_start < existing_end AND existing_start < requested_end
  - Published timetable collision detection for room/space resources
  - Alternative resource recommendations
  - Atomic booking state transitions with PostgreSQL row locking (with_for_update)
  - Full audit logging for every mutating action within the same transaction
"""

from __future__ import annotations

import datetime
import re
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Lab, Room, TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import AuditLog
from backend.schemas.resources import (
    AlternativeResource,
    AlternativeTime,
    ConflictDetail,
    ResourceBookingCreate,
    ResourceCreate,
    ResourceUpdate,
)
from backend.services.notification_service import (
    notify_booking_approved,
    notify_booking_cancelled,
    notify_booking_rejected,
    notify_booking_submitted,
)


def find_matching_room(db: Session, resource: Resource) -> Optional[Room]:
    """
    Attempts to map a Resource to a physical Room by location or name.
    Useful for LAB, SEMINAR_HALL, AUDITORIUM to detect timetable class conflicts.
    """
    if not resource:
        return None

    # Check direct location match against room_number
    if resource.location:
        room = db.query(Room).filter(Room.room_number.ilike(resource.location.strip())).first()
        if room:
            return room

    # Check direct name match against room_number (with optional prefix stripping)
    if resource.name:
        clean_name = re.sub(r"^(?:room|lab|hall|seminar\s+hall)\s+", "", resource.name.strip(), flags=re.IGNORECASE)
        room = db.query(Room).filter(
            or_(
                Room.room_number.ilike(resource.name.strip()),
                Room.room_number.ilike(clean_name),
            )
        ).first()
        if room:
            return room

    # Check lab_name match against Lab model
    if resource.name:
        lab = db.query(Lab).filter(Lab.lab_name.ilike(f"%{resource.name.strip()}%")).first()
        if lab and lab.room:
            return lab.room

    return None


def check_resource_conflicts(
    db: Session,
    resource_id: int,
    date: datetime.date,
    start_time: datetime.time,
    end_time: datetime.time,
    exclude_booking_id: Optional[int] = None,
) -> Tuple[bool, List[ConflictDetail]]:
    """
    Checks for all conflicts for a resource booking interval:
      1. Resource must exist and be ACTIVE.
      2. No overlap with an already APPROVED booking for the same resource.
      3. No overlap with a PUBLISHED timetable entry for the underlying physical room.

    Returns:
      (is_available: bool, conflicts: List[ConflictDetail])
    """
    conflicts: List[ConflictDetail] = []

    # 1. Resource existence and status
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        conflicts.append(
            ConflictDetail(
                conflict_type="RESOURCE_INACTIVE",
                description=f"Resource with ID {resource_id} does not exist.",
            )
        )
        return False, conflicts

    if resource.status != "ACTIVE":
        conflicts.append(
            ConflictDetail(
                conflict_type="RESOURCE_INACTIVE",
                description=f"Resource '{resource.name}' is currently {resource.status} and unavailable for booking.",
            )
        )
        return False, conflicts

    # 2. Global Resource Lock Policy:
    # A resource with an active booking (PENDING or APPROVED) is globally locked and unavailable
    # for all new bookings and availability inquiries, regardless of purpose, date, or time.
    # It becomes eligible again only when the active booking is CANCELLED or REJECTED.
    active_booking_query = db.query(ResourceBooking).filter(
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.status.in_(["PENDING", "APPROVED"]),
    )
    if exclude_booking_id is not None:
        active_booking_query = active_booking_query.filter(ResourceBooking.id != exclude_booking_id)

    active_booking = active_booking_query.first()
    if active_booking:
        conflicts.append(
            ConflictDetail(
                conflict_type="ACTIVE_BOOKING_LOCK",
                description=(
                    f"Resource already booked. {resource.name} has an active booking and is not available "
                    f"for another booking. Please select another resource."
                ),
                conflicting_id=active_booking.id,
                start_time=active_booking.start_time,
                end_time=active_booking.end_time,
            )
        )
        return False, conflicts

    # 3. Approved bookings overlap check (retained for interval sanity)
    # Interval overlap: existing_start < requested_end AND requested_start < existing_end
    booking_query = db.query(ResourceBooking).filter(
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.date == date,
        ResourceBooking.status == "APPROVED",
        ResourceBooking.start_time < end_time,
        ResourceBooking.end_time > start_time,
    )
    if exclude_booking_id is not None:
        booking_query = booking_query.filter(ResourceBooking.id != exclude_booking_id)

    overlapping_bookings = booking_query.all()
    for b in overlapping_bookings:
        b_st_str = b.start_time.strftime("%H:%M") if b.start_time else "N/A"
        b_et_str = b.end_time.strftime("%H:%M") if b.end_time else "N/A"
        conflicts.append(
            ConflictDetail(
                conflict_type="EXISTING_BOOKING",
                description=(
                    f"Overlaps with approved reservation #{b.id} "
                    f"({b_st_str} - {b_et_str})"
                ),
                conflicting_id=b.id,
                start_time=b.start_time,
                end_time=b.end_time,
            )
        )

    # 3. Published timetable check (for physical room-based resources)
    room = find_matching_room(db, resource)
    if room:
        day_3 = date.strftime("%a").upper()
        day_full = date.strftime("%A").upper()

        # Join TimetableEntry -> TimetableVersion (PUBLISHED only) & TimeSlot
        tt_conflicts = (
            db.query(TimetableEntry, TimeSlot)
            .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableVersion.status == "PUBLISHED",
                TimetableEntry.room_id == room.id,
                TimetableEntry.status.in_(["ACTIVE", "DRAFT"]),
                TimeSlot.day.in_([day_3, day_full]),
                TimeSlot.start_time < end_time,
                TimeSlot.end_time > start_time,
            )
            .all()
        )

        for entry, slot in tt_conflicts:
            conflicts.append(
                ConflictDetail(
                    conflict_type="PUBLISHED_TIMETABLE",
                    description=(
                        f"Physical room '{room.room_number}' is occupied by published timetable class "
                        f"on {day_full} ({slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')})"
                    ),
                    conflicting_id=entry.id,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                )
            )

    is_available = len(conflicts) == 0
    return is_available, conflicts


def find_alternative_resources(
    db: Session,
    resource_id: int,
    date: datetime.date,
    start_time: datetime.time,
    end_time: datetime.time,
    limit: int = 5,
) -> List[AlternativeResource]:
    """
    Finds available alternative resources of the same type and compatible capacity
    for the requested date and time interval.
    """
    target = db.query(Resource).filter(Resource.id == resource_id).first()
    if not target:
        return []

    # Find candidates with matching resource_type and ACTIVE status
    candidates = (
        db.query(Resource)
        .filter(
            Resource.id != resource_id,
            Resource.resource_type == target.resource_type,
            Resource.status == "ACTIVE",
        )
        .all()
    )

    # Sort candidates by capacity closeness
    if target.capacity is not None:
        target_cap = target.capacity
        candidates.sort(key=lambda r: abs((r.capacity or 0) - target_cap))

    alternatives: List[AlternativeResource] = []
    for cand in candidates:
        available, _ = check_resource_conflicts(
            db=db,
            resource_id=cand.id,
            date=date,
            start_time=start_time,
            end_time=end_time,
        )
        if available:
            alternatives.append(
                AlternativeResource(
                    id=cand.id,
                    name=cand.name or f"Resource #{cand.id}",
                    resource_type=cand.resource_type or "EQUIPMENT",
                    location=cand.location,
                    capacity=cand.capacity,
                )
            )
            if len(alternatives) >= limit:
                break

    return alternatives


def find_alternative_times(
    db: Session,
    resource_id: int,
    date: datetime.date,
    duration_minutes: int,
    limit: int = 5,
) -> List[AlternativeTime]:
    """
    Finds available alternative time intervals for the same resource on the requested date.
    Evaluates candidate standard campus operating windows (09:00 to 17:00).
    """
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource or resource.status != "ACTIVE":
        return []

    candidate_starts = [
        datetime.time(9, 0),
        datetime.time(10, 0),
        datetime.time(11, 15),
        datetime.time(12, 15),
        datetime.time(14, 0),
        datetime.time(15, 0),
        datetime.time(16, 0),
    ]

    duration_delta = datetime.timedelta(minutes=duration_minutes)
    alternatives: List[AlternativeTime] = []

    for start_t in candidate_starts:
        dummy_dt = datetime.datetime.combine(date, start_t)
        end_dt = dummy_dt + duration_delta
        if end_dt.time() > datetime.time(18, 0):
            continue
        end_t = end_dt.time()

        is_avail, _ = check_resource_conflicts(
            db=db,
            resource_id=resource_id,
            date=date,
            start_time=start_t,
            end_time=end_t,
        )
        if is_avail:
            alternatives.append(
                AlternativeTime(
                    resource_id=resource.id,
                    resource_name=resource.name or f"Resource #{resource.id}",
                    date=date,
                    start_time=start_t,
                    end_time=end_t,
                    duration_minutes=duration_minutes,
                )
            )
            if len(alternatives) >= limit:
                break

    return alternatives


# ── Booking Mutations with Atomic State & Concurrency Safety ──────────────────

def create_booking_request(
    db: Session,
    booking_in: ResourceBookingCreate,
    current_user_id: int,
    initial_status: str = "PENDING",
) -> ResourceBooking:
    """
    Submits a booking request. Enforces interval validation and conflict checks.
    If a conflict exists, raises HTTP 409 with structured explanation and alternatives.
    """
    # Serialize concurrent booking requests on the target resource
    resource = (
        db.query(Resource)
        .filter(Resource.id == booking_in.resource_id)
        .with_for_update()
        .first()
    )
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource with ID {booking_in.resource_id} not found",
        )

    available, conflicts = check_resource_conflicts(
        db=db,
        resource_id=booking_in.resource_id,
        date=booking_in.date,
        start_time=booking_in.start_time,
        end_time=booking_in.end_time,
    )

    if not available:
        alternatives = find_alternative_resources(
            db=db,
            resource_id=booking_in.resource_id,
            date=booking_in.date,
            start_time=booking_in.start_time,
            end_time=booking_in.end_time,
        )
        duration_minutes = int((datetime.datetime.combine(booking_in.date, booking_in.end_time) - datetime.datetime.combine(booking_in.date, booking_in.start_time)).total_seconds() // 60)
        alt_times = find_alternative_times(
            db=db,
            resource_id=booking_in.resource_id,
            date=booking_in.date,
            duration_minutes=duration_minutes,
        )
        conflict_msg = "; ".join(c.description for c in conflicts)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Resource unavailable due to conflict: {conflict_msg}",
                "conflicts": [c.model_dump(mode="json") for c in conflicts],
                "alternatives": [a.model_dump(mode="json") for a in alternatives],
                "alternative_times": [t.model_dump(mode="json") for t in alt_times],
            },
        )

    booking = ResourceBooking(
        resource_id=booking_in.resource_id,
        requested_by=current_user_id,
        date=booking_in.date,
        start_time=booking_in.start_time,
        end_time=booking_in.end_time,
        purpose=booking_in.purpose,
        status=initial_status,
        approved_by=current_user_id if initial_status == "APPROVED" else None,
    )
    db.add(booking)
    db.flush()

    # Log audit entry
    audit = AuditLog(
        user_id=current_user_id,
        action="RESOURCE_BOOKING_CREATED",
        entity_type="ResourceBooking",
        entity_id=booking.id,
        new_value={
            "resource_id": booking.resource_id,
            "date": str(booking.date),
            "start_time": str(booking.start_time),
            "end_time": str(booking.end_time),
            "status": booking.status,
            "purpose": booking.purpose,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(booking)
    notify_booking_submitted(db=db, booking_id=booking.id)
    return booking


def approve_booking_request(
    db: Session,
    booking_id: int,
    approver_id: int,
) -> ResourceBooking:
    """
    Approves a PENDING booking using SELECT ... FOR UPDATE.
    Crucially, locks the parent Resource row first to serialize all concurrent booking
    approvals targeting the same physical facility or equipment, preventing double-booking races.
    Rechecks conflicts atomically before transitioning to APPROVED.
    """
    # 1. Fetch the target booking to determine the target resource
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource booking #{booking_id} not found",
        )

    if booking.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve booking #{booking_id} because its current status is '{booking.status}' (expected 'PENDING').",
        )

    # 2. Lock the parent Resource row to serialize all concurrent booking allocations on this resource
    resource = (
        db.query(Resource)
        .filter(Resource.id == booking.resource_id)
        .with_for_update()
        .first()
    )
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource #{booking.resource_id} not found",
        )

    # 3. Lock the specific booking row and recheck status
    booking = (
        db.query(ResourceBooking)
        .filter(ResourceBooking.id == booking_id)
        .with_for_update()
        .first()
    )

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource booking #{booking_id} not found",
        )

    if booking.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve booking #{booking_id} because its status is '{booking.status}' (expected 'PENDING').",
        )

    if (
        booking.resource_id is None
        or booking.date is None
        or booking.start_time is None
        or booking.end_time is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve booking #{booking_id}: incomplete booking schedule data.",
        )

    # 4. Re-check conflicts atomically while holding lock on the parent Resource
    available, conflicts = check_resource_conflicts(
        db=db,
        resource_id=booking.resource_id,
        date=booking.date,
        start_time=booking.start_time,
        end_time=booking.end_time,
        exclude_booking_id=booking.id,
    )

    if not available:
        conflict_msg = "; ".join(c.description for c in conflicts)
        alternatives = find_alternative_resources(
            db=db,
            resource_id=booking.resource_id,
            date=booking.date,
            start_time=booking.start_time,
            end_time=booking.end_time,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Cannot approve booking: resource conflict detected: {conflict_msg}",
                "conflicts": [c.model_dump(mode="json") for c in conflicts],
                "alternatives": [a.model_dump(mode="json") for a in alternatives],
            },
        )

    old_status = booking.status
    booking.status = "APPROVED"
    booking.approved_by = approver_id

    # Write audit log
    audit = AuditLog(
        user_id=approver_id,
        action="RESOURCE_BOOKING_APPROVED",
        entity_type="ResourceBooking",
        entity_id=booking.id,
        old_value={"status": old_status},
        new_value={"status": "APPROVED", "approved_by": approver_id},
    )
    db.add(audit)
    db.commit()
    db.refresh(booking)
    notify_booking_approved(db=db, booking_id=booking.id)
    return booking


def reject_booking_request(
    db: Session,
    booking_id: int,
    reviewer_id: int,
    reason: Optional[str] = None,
) -> ResourceBooking:
    """
    Rejects a PENDING booking request.
    """
    booking = (
        db.query(ResourceBooking)
        .filter(ResourceBooking.id == booking_id)
        .with_for_update()
        .first()
    )

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource booking #{booking_id} not found",
        )

    if booking.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject booking #{booking_id} because its current status is '{booking.status}' (expected 'PENDING').",
        )

    old_status = booking.status
    booking.status = "REJECTED"
    booking.approved_by = reviewer_id

    audit = AuditLog(
        user_id=reviewer_id,
        action="RESOURCE_BOOKING_REJECTED",
        entity_type="ResourceBooking",
        entity_id=booking.id,
        old_value={"status": old_status},
        new_value={"status": "REJECTED", "reviewer_id": reviewer_id, "reason": reason},
    )
    db.add(audit)
    db.commit()
    db.refresh(booking)
    notify_booking_rejected(db=db, booking_id=booking.id, reason=reason)
    return booking


def cancel_booking_request(
    db: Session,
    booking_id: int,
    current_user_id: int,
    current_user_role: str,
    reason: Optional[str] = None,
) -> ResourceBooking:
    """
    Cancels a PENDING or APPROVED booking request.
    Allowed only for ADMIN or the user who originally requested the booking.
    """
    booking = (
        db.query(ResourceBooking)
        .filter(ResourceBooking.id == booking_id)
        .with_for_update()
        .first()
    )

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource booking #{booking_id} not found",
        )

    # Permission check: ADMIN or requester
    if current_user_role != "ADMIN" and booking.requested_by != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to cancel this booking.",
        )

    if booking.status not in ["PENDING", "APPROVED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel booking #{booking_id} with status '{booking.status}'.",
        )

    old_status = booking.status
    booking.status = "CANCELLED"

    audit = AuditLog(
        user_id=current_user_id,
        action="RESOURCE_BOOKING_CANCELLED",
        entity_type="ResourceBooking",
        entity_id=booking.id,
        old_value={"status": old_status},
        new_value={"status": "CANCELLED", "cancelled_by": current_user_id, "reason": reason},
    )
    db.add(audit)
    db.commit()
    db.refresh(booking)
    notify_booking_cancelled(db=db, booking_id=booking.id, cancelled_by_user_id=current_user_id, reason=reason)
    return booking


# ── Resource Inventory Management ─────────────────────────────────────────────

def create_resource(db: Session, res_in: ResourceCreate, user_id: int) -> Resource:
    """Creates a new campus resource and logs the action."""
    res = Resource(**res_in.model_dump())
    db.add(res)
    db.flush()

    audit = AuditLog(
        user_id=user_id,
        action="RESOURCE_CREATED",
        entity_type="Resource",
        entity_id=res.id,
        new_value=res_in.model_dump(mode="json"),
    )
    db.add(audit)
    db.commit()
    db.refresh(res)
    return res


def update_resource(
    db: Session,
    resource_id: int,
    res_in: ResourceUpdate,
    user_id: int,
) -> Resource:
    """Updates an existing resource and logs the diff."""
    res = db.query(Resource).filter(Resource.id == resource_id).first()
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource #{resource_id} not found",
        )

    update_data = res_in.model_dump(exclude_unset=True)
    old_data = {k: getattr(res, k) for k in update_data}

    for key, value in update_data.items():
        setattr(res, key, value)

    audit = AuditLog(
        user_id=user_id,
        action="RESOURCE_UPDATED",
        entity_type="Resource",
        entity_id=res.id,
        old_value=old_data,
        new_value=update_data,
    )
    db.add(audit)
    db.commit()
    db.refresh(res)
    return res


def delete_or_deactivate_resource(
    db: Session,
    resource_id: int,
    user_id: int,
) -> dict:
    """
    Deactivates or deletes a resource.
    If active/pending bookings depend on the resource, prevents hard deletion and deactivates it safely.
    """
    res = db.query(Resource).filter(Resource.id == resource_id).first()
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource #{resource_id} not found",
        )

    # Check for active or pending bookings
    active_bookings = (
        db.query(ResourceBooking)
        .filter(
            ResourceBooking.resource_id == resource_id,
            ResourceBooking.status.in_(["PENDING", "APPROVED"]),
        )
        .count()
    )

    if active_bookings > 0:
        # Safe deactivation instead of destructive delete
        old_status = res.status
        res.status = "INACTIVE"
        audit = AuditLog(
            user_id=user_id,
            action="RESOURCE_DEACTIVATED",
            entity_type="Resource",
            entity_id=res.id,
            old_value={"status": old_status},
            new_value={"status": "INACTIVE", "reason": "Deactivated due to existing bookings"},
        )
        db.add(audit)
        db.commit()
        return {
            "action": "DEACTIVATED",
            "message": f"Resource #{resource_id} has {active_bookings} active/pending bookings; status set to INACTIVE.",
            "resource_id": resource_id,
        }

    # If no bookings exist, check any history
    has_history = (
        db.query(ResourceBooking)
        .filter(ResourceBooking.resource_id == resource_id)
        .count()
    )

    if has_history > 0:
        old_status = res.status
        res.status = "INACTIVE"
        audit = AuditLog(
            user_id=user_id,
            action="RESOURCE_DEACTIVATED",
            entity_type="Resource",
            entity_id=res.id,
            old_value={"status": old_status},
            new_value={"status": "INACTIVE", "reason": "Deactivated to preserve booking history"},
        )
        db.add(audit)
        db.commit()
        return {
            "action": "DEACTIVATED",
            "message": f"Resource #{resource_id} has past booking records; status set to INACTIVE.",
            "resource_id": resource_id,
        }

    # Hard delete allowed when zero bookings exist
    db.delete(res)
    audit = AuditLog(
        user_id=user_id,
        action="RESOURCE_DELETED",
        entity_type="Resource",
        entity_id=resource_id,
        old_value={"name": res.name, "resource_type": res.resource_type},
        new_value=None,
    )
    db.add(audit)
    db.commit()
    return {
        "action": "DELETED",
        "message": f"Resource #{resource_id} successfully deleted.",
        "resource_id": resource_id,
    }
