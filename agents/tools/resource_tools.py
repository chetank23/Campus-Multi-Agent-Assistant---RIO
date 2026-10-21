"""
agents/tools/resource_tools.py
------------------------------
Authoritative database-grounded tool adapters for Resource Agent operations.
Reuses domain services from backend.services.resource_booking_service:
- Resource discovery & inventory search
- Real-time interval conflict detection & alternative suggestions
- User-scoped booking history inspection
- Single booking detail lookup with role-based privacy masking
- Booking creation and cancellation with atomic row locking
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.schemas.resources import (
    ResourceBookingCreate,
    ConflictDetail,
    AlternativeResource,
)
from backend.services.resource_booking_service import (
    check_resource_conflicts,
    find_alternative_resources,
    create_booking_request,
    cancel_booking_request,
)


def discover_resources_data(
    db: Session,
    resource_type: Optional[str] = None,
    min_capacity: Optional[int] = None,
    location_query: Optional[str] = None,
    search_query: Optional[str] = None,
    status_filter: str = "ACTIVE",
    limit: int = 15,
) -> Dict[str, Any]:
    """
    Discovers campus facilities and equipment in the database.
    Filterable by type, capacity, location, and search keyword.
    """
    query = db.query(Resource)

    if status_filter:
        query = query.filter(Resource.status == status_filter)

    if resource_type:
        query = query.filter(Resource.resource_type == resource_type.upper())

    if min_capacity is not None and min_capacity > 0:
        query = query.filter(Resource.capacity >= min_capacity)

    if location_query:
        query = query.filter(Resource.location.ilike(f"%{location_query.strip()}%"))

    if search_query:
        term = f"%{search_query.strip()}%"
        query = query.filter(
            or_(
                Resource.name.ilike(term),
                Resource.location.ilike(term),
                Resource.resource_type.ilike(term),
            )
        )

    resources = query.order_by(Resource.id).limit(limit).all()

    active_locks = set(
        row[0]
        for row in db.query(ResourceBooking.resource_id)
        .filter(ResourceBooking.status.in_(["PENDING", "APPROVED"]))
        .all()
    )

    results = []
    for r in resources:
        is_locked = r.id in active_locks
        results.append({
            "id": r.id,
            "name": r.name,
            "resource_type": r.resource_type,
            "location": r.location,
            "capacity": r.capacity,
            "status": r.status,
            "is_locked": is_locked,
            "availability_status": "LOCKED" if is_locked else "AVAILABLE",
        })

    return {
        "count": len(results),
        "resources": results,
    }


def check_resource_availability_data(
    db: Session,
    resource_id: int,
    date: datetime.date,
    start_time: datetime.time,
    end_time: datetime.time,
) -> Dict[str, Any]:
    """
    Authoritative interval availability check:
    - Verifies resource exists and is ACTIVE
    - Checks overlap against approved reservations
    - Checks overlap against published timetable entries for the room
    - If conflict, suggests genuine alternative resources of same type
    """
    res = db.query(Resource).filter(Resource.id == resource_id).first()
    if not res:
        return {
            "resource_id": resource_id,
            "available": False,
            "message": f"Resource with ID {resource_id} does not exist in inventory.",
            "conflicts": [{"conflict_type": "RESOURCE_INACTIVE", "description": "Resource not found."}],
            "alternatives": [],
        }

    available, conflicts = check_resource_conflicts(
        db=db,
        resource_id=resource_id,
        date=date,
        start_time=start_time,
        end_time=end_time,
    )

    alternatives: List[AlternativeResource] = []
    if not available:
        alternatives = find_alternative_resources(
            db=db,
            resource_id=resource_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            limit=5,
        )

    return {
        "resource_id": res.id,
        "resource_name": res.name,
        "resource_type": res.resource_type,
        "location": res.location,
        "capacity": res.capacity,
        "date": str(date),
        "start_time": str(start_time),
        "end_time": str(end_time),
        "available": available,
        "conflicts": [c.model_dump(mode="json") for c in conflicts],
        "alternatives": [a.model_dump(mode="json") for a in alternatives],
    }


def get_user_bookings_data(
    db: Session,
    user: User,
    status_filter: Optional[str] = None,
    limit: int = 15,
) -> Dict[str, Any]:
    """
    Lists resource bookings for the authenticated user session.
    - ADMIN sees all bookings (or filtered).
    - FACULTY / STUDENT sees their own bookings.
    """
    query = db.query(ResourceBooking)

    if user.role != "ADMIN":
        query = query.filter(ResourceBooking.requested_by == user.id)

    if status_filter:
        query = query.filter(ResourceBooking.status == status_filter.upper())

    bookings = query.order_by(ResourceBooking.date.desc(), ResourceBooking.start_time.desc()).limit(limit).all()

    items = []
    for b in bookings:
        res = db.query(Resource).filter(Resource.id == b.resource_id).first()
        requester = db.query(User).filter(User.id == b.requested_by).first() if b.requested_by else None
        items.append({
            "booking_id": b.id,
            "resource_id": b.resource_id,
            "resource_name": res.name if res else f"Resource #{b.resource_id}",
            "resource_type": res.resource_type if res else None,
            "location": res.location if res else None,
            "date": str(b.date),
            "start_time": str(b.start_time),
            "end_time": str(b.end_time),
            "status": b.status,
            "purpose": b.purpose,
            "requested_by_id": b.requested_by,
            "requester_name": requester.name if requester else None,
        })

    return {
        "count": len(items),
        "bookings": items,
    }


def get_booking_details_data(
    db: Session,
    booking_id: int,
    user: User,
) -> Dict[str, Any]:
    """
    Fetches full booking details with role-based privacy masking.
    Non-admin users may only inspect their own bookings or public approved bookings.
    """
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking:
        return {"error": f"Booking request #{booking_id} was not found."}

    # Privacy guard
    if user.role != "ADMIN" and booking.requested_by != user.id and booking.status != "APPROVED":
        return {"error": f"Access denied: You do not have permission to view booking #{booking_id}."}

    res = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    requester = db.query(User).filter(User.id == booking.requested_by).first() if booking.requested_by else None
    approver = db.query(User).filter(User.id == booking.approved_by).first() if booking.approved_by else None

    # Mask requester email for non-admin viewers who are not the requester
    can_see_email = (user.role == "ADMIN" or user.id == booking.requested_by)
    requester_email = requester.email if (requester and can_see_email) else None

    return {
        "booking_id": booking.id,
        "resource_id": booking.resource_id,
        "resource_name": res.name if res else f"Resource #{booking.resource_id}",
        "resource_type": res.resource_type if res else None,
        "location": res.location if res else None,
        "capacity": res.capacity if res else None,
        "date": str(booking.date),
        "start_time": str(booking.start_time),
        "end_time": str(booking.end_time),
        "status": booking.status,
        "purpose": booking.purpose,
        "requester_name": requester.name if requester else None,
        "requester_email": requester_email,
        "approver_name": approver.name if approver else None,
    }


def execute_create_booking_data(
    db: Session,
    resource_id: int,
    date: datetime.date,
    start_time: datetime.time,
    end_time: datetime.time,
    purpose: str,
    user: User,
) -> Dict[str, Any]:
    """
    Executes authoritative booking creation through backend.services.resource_booking_service.
    Enforces atomic conflict detection and AuditLog entry within transaction.
    """
    try:
        booking_in = ResourceBookingCreate(
            resource_id=resource_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            purpose=purpose,
        )
        booking = create_booking_request(
            db=db,
            booking_in=booking_in,
            current_user_id=user.id,
            initial_status="PENDING",
        )
        res = db.query(Resource).filter(Resource.id == booking.resource_id).first()
        return {
            "success": True,
            "booking_id": booking.id,
            "resource_id": booking.resource_id,
            "resource_name": res.name if res else f"Resource #{booking.resource_id}",
            "resource_type": res.resource_type if res else None,
            "location": res.location if res else None,
            "date": str(booking.date),
            "start_time": str(booking.start_time),
            "end_time": str(booking.end_time),
            "status": booking.status,
            "purpose": booking.purpose,
        }
    except Exception as exc:
        # HTTPException or validation error
        detail = getattr(exc, "detail", str(exc))
        return {
            "success": False,
            "error": detail,
        }


def execute_cancel_booking_data(
    db: Session,
    booking_id: int,
    user: User,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes booking cancellation through backend.services.resource_booking_service.
    Enforces role authorization (ADMIN or requester only).
    """
    try:
        booking = cancel_booking_request(
            db=db,
            booking_id=booking_id,
            current_user_id=user.id,
            current_user_role=user.role,
            reason=reason,
        )
        res = db.query(Resource).filter(Resource.id == booking.resource_id).first()
        return {
            "success": True,
            "booking_id": booking.id,
            "resource_name": res.name if res else f"Resource #{booking.resource_id}",
            "status": booking.status,
            "message": f"Booking #{booking.id} has been cancelled successfully.",
        }
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return {
            "success": False,
            "error": detail,
        }
