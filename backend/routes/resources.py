"""
backend/routes/resources.py
---------------------------
API endpoints for Resource Inventory Management, Booking Lifecycle,
and Conflict/Availability Verification.
"""

from __future__ import annotations

import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.schemas.resources import (
    AvailabilityResponse,
    BookingStatus,
    BookingStatusAction,
    ResourceBookingCreate,
    ResourceBookingResponse,
    ResourceCreate,
    ResourceResponse,
    ResourceType,
    ResourceUpdate,
)
from backend.services.resource_booking_service import (
    approve_booking_request,
    cancel_booking_request,
    check_resource_conflicts,
    create_booking_request,
    create_resource,
    delete_or_deactivate_resource,
    find_alternative_resources,
    reject_booking_request,
    update_resource,
)

router = APIRouter(prefix="/resources", tags=["Resources"])


def _enrich_booking_response(
    booking: ResourceBooking,
    db: Session,
    viewer: Optional[User] = None,
) -> ResourceBookingResponse:
    """
    Helper to populate user and resource metadata on booking responses.
    Protects user privacy by masking personal email addresses for non-admin third parties.
    """
    if (
        booking.resource_id is None
        or booking.date is None
        or booking.start_time is None
        or booking.end_time is None
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resource booking #{booking.id} contains incomplete schedule data.",
        )

    res = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    requester = db.query(User).filter(User.id == booking.requested_by).first() if booking.requested_by else None
    approver = db.query(User).filter(User.id == booking.approved_by).first() if booking.approved_by else None

    # Privacy protection: only ADMIN or the requester can see personal email
    is_owner_or_admin = viewer is None or viewer.role == "ADMIN" or (viewer.id == booking.requested_by)
    requester_email = requester.email if (requester and is_owner_or_admin) else None

    raw_status = (booking.status or "PENDING").upper()
    if raw_status == "APPROVED":
        status_val: BookingStatus = "APPROVED"
    elif raw_status == "REJECTED":
        status_val: BookingStatus = "REJECTED"
    elif raw_status == "CANCELLED":
        status_val: BookingStatus = "CANCELLED"
    else:
        status_val: BookingStatus = "PENDING"

    return ResourceBookingResponse(
        id=booking.id,
        resource_id=booking.resource_id,
        requested_by=booking.requested_by,
        date=booking.date,
        start_time=booking.start_time,
        end_time=booking.end_time,
        purpose=booking.purpose,
        status=status_val,
        approved_by=booking.approved_by,
        resource_name=res.name if res else f"Resource #{booking.resource_id}",
        resource_type=res.resource_type if res else None,
        resource_location=res.location if res else None,
        requester_name=requester.name if requester else None,
        requester_email=requester_email,
        approver_name=approver.name if approver else None,
    )


# ── Booking Endpoints (Declared before /{resource_id} to avoid collision) ─────

@router.get("/bookings", response_model=List[ResourceBookingResponse])
def list_bookings(
    status_filter: Optional[BookingStatus] = Query(None, alias="status"),
    resource_id: Optional[int] = Query(None),
    from_date: Optional[datetime.date] = Query(None),
    to_date: Optional[datetime.date] = Query(None),
    my_only: bool = Query(False, description="Filter only bookings requested by current user"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lists resource bookings.
    - ADMIN sees all bookings.
    - FACULTY and STUDENT see their own bookings plus public APPROVED bookings (unless my_only=True).
    """
    query = db.query(ResourceBooking)

    if current_user.role != "ADMIN" or my_only:
        if my_only or current_user.role == "STUDENT":
            query = query.filter(ResourceBooking.requested_by == current_user.id)
        else:
            # Non-admin sees their own requests OR any approved reservation
            query = query.filter(
                or_(
                    ResourceBooking.requested_by == current_user.id,
                    ResourceBooking.status == "APPROVED",
                )
            )

    if status_filter:
        query = query.filter(ResourceBooking.status == status_filter)
    if resource_id:
        query = query.filter(ResourceBooking.resource_id == resource_id)
    if from_date:
        query = query.filter(ResourceBooking.date >= from_date)
    if to_date:
        query = query.filter(ResourceBooking.date <= to_date)

    bookings = query.order_by(ResourceBooking.date.desc(), ResourceBooking.start_time.desc()).all()
    return [_enrich_booking_response(b, db, viewer=current_user) for b in bookings]


@router.post("/bookings", response_model=ResourceBookingResponse, status_code=status.HTTP_201_CREATED)
def submit_booking_request(
    booking_in: ResourceBookingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submits a new resource booking request.
    Validates interval and runs conflict checks against existing bookings & timetable.
    Returns 409 Conflict with alternative options if requested time is unavailable.
    """
    booking = create_booking_request(
        db=db,
        booking_in=booking_in,
        current_user_id=current_user.id,
        initial_status="PENDING",
    )
    return _enrich_booking_response(booking, db, viewer=current_user)


@router.get("/bookings/{booking_id}", response_model=ResourceBookingResponse)
def get_booking_details(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetches details for a specific booking request."""
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource booking #{booking_id} not found",
        )

    # Privacy check: non-admin can only inspect their own booking or approved bookings
    if current_user.role != "ADMIN" and booking.requested_by != current_user.id and booking.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this booking.",
        )

    return _enrich_booking_response(booking, db, viewer=current_user)


@router.post("/bookings/{booking_id}/approve", response_model=ResourceBookingResponse)
def approve_booking(
    booking_id: int,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Approves a PENDING booking request.
    Enforces atomic re-checking to ensure no race-condition collision occurred.
    """
    booking = approve_booking_request(
        db=db,
        booking_id=booking_id,
        approver_id=admin_user.id,
    )
    return _enrich_booking_response(booking, db, viewer=admin_user)


@router.post("/bookings/{booking_id}/reject", response_model=ResourceBookingResponse)
def reject_booking(
    booking_id: int,
    action: Optional[BookingStatusAction] = None,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """Rejects a PENDING booking request."""
    reason = action.reason if action else None
    booking = reject_booking_request(
        db=db,
        booking_id=booking_id,
        reviewer_id=admin_user.id,
        reason=reason,
    )
    return _enrich_booking_response(booking, db, viewer=admin_user)


@router.post("/bookings/{booking_id}/cancel", response_model=ResourceBookingResponse)
def cancel_booking(
    booking_id: int,
    action: Optional[BookingStatusAction] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cancels a PENDING or APPROVED booking.
    Allowed only for ADMIN or the user who created the request.
    """
    reason = action.reason if action else None
    booking = cancel_booking_request(
        db=db,
        booking_id=booking_id,
        current_user_id=current_user.id,
        current_user_role=current_user.role,
        reason=reason,
    )
    return _enrich_booking_response(booking, db, viewer=current_user)


@router.get("/availability", response_model=AvailabilityResponse)
def check_availability(
    resource_id: int = Query(...),
    date: datetime.date = Query(...),
    start_time: datetime.time = Query(...),
    end_time: datetime.time = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Checks resource availability for a date and time interval.
    If occupied, returns conflict descriptions and compatible alternative resources.
    """
    if start_time >= end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be strictly after start_time",
        )

    available, conflicts = check_resource_conflicts(
        db=db,
        resource_id=resource_id,
        date=date,
        start_time=start_time,
        end_time=end_time,
    )

    alternatives = []
    if not available:
        alternatives = find_alternative_resources(
            db=db,
            resource_id=resource_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
        )

    return AvailabilityResponse(
        resource_id=resource_id,
        date=date,
        start_time=start_time,
        end_time=end_time,
        available=available,
        conflicts=conflicts,
        alternatives=alternatives,
    )


# ── Resource Inventory Endpoints ──────────────────────────────────────────────

@router.get("", response_model=List[ResourceResponse])
def list_resources(
    resource_type: Optional[ResourceType] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists campus resources with filtering and search."""
    query = db.query(Resource)

    if resource_type:
        query = query.filter(Resource.resource_type == resource_type)
    if status_filter:
        query = query.filter(Resource.status == status_filter)
    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Resource.name.ilike(search_pattern),
                Resource.location.ilike(search_pattern),
            )
        )

    return query.order_by(Resource.id).offset(skip).limit(limit).all()


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
def create_new_resource(
    resource_in: ResourceCreate,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """Creates a new campus resource (Admin only)."""
    return create_resource(db=db, res_in=resource_in, user_id=admin_user.id)


@router.get("/{resource_id}", response_model=ResourceResponse)
def get_resource_by_id(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves a single resource by its ID."""
    res = db.query(Resource).filter(Resource.id == resource_id).first()
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource #{resource_id} not found",
        )
    return res


@router.put("/{resource_id}", response_model=ResourceResponse)
def update_existing_resource(
    resource_id: int,
    resource_in: ResourceUpdate,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """Updates an existing resource's attributes (Admin only)."""
    return update_resource(
        db=db,
        resource_id=resource_id,
        res_in=resource_in,
        user_id=admin_user.id,
    )


@router.delete("/{resource_id}")
def delete_resource_by_id(
    resource_id: int,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Deactivates or deletes a resource (Admin only).
    Safely sets status to INACTIVE if bookings depend on it.
    """
    return delete_or_deactivate_resource(
        db=db,
        resource_id=resource_id,
        user_id=admin_user.id,
    )
