"""
backend/routes/clubs.py
-----------------------
REST API routes for:
1. Campus Clubs & Student Organizations
2. Faculty "My Clubs" Coordinator Workspace
3. Admin Coordinator Capability Management (Assign, Revoke, List)
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.identity import User
from backend.models.events import Club, CoordinatorCapability, CampusEvent
from backend.routes.auth import get_current_user
from backend.schemas.events import (
    CapabilityAssignRequest,
    CapabilityResponse,
    CapabilityRevokeRequest,
    ClubCoordinatorItem,
    ClubCreateRequest,
    ClubResponse,
    ClubUpdateRequest,
    EventResponse,
)
from backend.services.event_service import (
    assign_capability,
    create_club,
    get_club,
    list_capabilities,
    list_clubs,
    list_events_for_user,
    list_faculty_assigned_clubs,
    revoke_capability,
    update_club,
)

router = APIRouter(tags=["clubs"])


def _format_club_response(db: Session, club: Club) -> ClubResponse:
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    # Fetch active coordinators for this club
    caps = (
        db.query(CoordinatorCapability)
        .filter(
            CoordinatorCapability.capability == "CLUB_COORDINATOR",
            CoordinatorCapability.scope_type == "CLUB",
            CoordinatorCapability.scope_id == club.id,
            CoordinatorCapability.is_active == True,
        )
        .all()
    )

    coordinator_items = []
    for c in caps:
        u = c.user
        # Check if coordinator also has direct publish capability for this club
        has_dp = (
            db.query(CoordinatorCapability)
            .filter(
                CoordinatorCapability.user_id == c.user_id,
                CoordinatorCapability.capability == "EVENT_DIRECT_PUBLISH",
                CoordinatorCapability.is_active == True,
            )
            .first()
            is not None
        )

        coordinator_items.append(
            ClubCoordinatorItem(
                capability_id=c.id,
                user_id=c.user_id,
                name=u.name if u else "Faculty",
                email=u.email if u else "",
                role=u.role if u else "FACULTY",
                is_active=c.is_active,
                has_direct_publish=has_dp,
                assigned_at=c.created_at.isoformat() if c.created_at else datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
        )

    activities_count = db.query(CampusEvent).filter(CampusEvent.club_id == club.id).count()

    c_at = club.created_at.isoformat() if club.created_at else datetime.datetime.now(datetime.timezone.utc).isoformat()
    u_at = club.updated_at.isoformat() if club.updated_at else datetime.datetime.now(datetime.timezone.utc).isoformat()

    return ClubResponse(
        id=club.id,
        name=club.name,
        code=club.code,
        category=club.category,
        description=club.description,
        status=club.status,
        coordinators=coordinator_items,
        activities_count=activities_count,
        created_at=c_at,
        updated_at=u_at,
    )


# ---------------------------------------------------------------------------
# 1. Public & Student Club Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/clubs",
    response_model=List[ClubResponse],
    summary="List all campus clubs and organizations",
)
def get_clubs(
    category: Optional[str] = Query(None, description="Category filter (TECHNICAL, CULTURAL, etc.)"),
    status: Optional[str] = Query(None, description="Status filter (ACTIVE, INACTIVE)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ClubResponse]:
    """Lists clubs with coordinator summaries and activity counts."""
    # Default to ACTIVE clubs for non-admins
    st = status if (current_user.role == "ADMIN" and status) else (status or "ACTIVE")
    clubs = list_clubs(db=db, category=category, status_filter=st)
    return [_format_club_response(db, c) for c in clubs]


@router.get(
    "/clubs/{club_id}",
    response_model=ClubResponse,
    summary="Get single club details",
)
def get_club_detail(
    club_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClubResponse:
    """Retrieves club details and active coordinator assignments."""
    club = get_club(db=db, club_id=club_id)
    if not club:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Club #{club_id} not found.",
        )
    return _format_club_response(db, club)


@router.get(
    "/clubs/{club_id}/activities",
    response_model=List[EventResponse],
    summary="List visible activities for a specific club",
)
def get_club_activities(
    club_id: int,
    time_filter: Optional[str] = Query(None, description="TODAY, ONGOING, THIS_WEEK, UPCOMING"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists activities for a specific club honoring student/faculty visibility barriers."""
    club = get_club(db=db, club_id=club_id)
    if not club:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Club #{club_id} not found.",
        )

    return list_events_for_user(
        db=db,
        current_user=current_user,
        club_id=club_id,
        time_filter=time_filter,
    )


# ---------------------------------------------------------------------------
# 2. Faculty "My Clubs" Coordinator Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/faculty/my-clubs",
    response_model=List[ClubResponse],
    summary="List clubs assigned to authenticated faculty member",
)
def get_my_clubs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ClubResponse]:
    """
    Returns only the clubs assigned to the current faculty member
    through active CLUB_COORDINATOR capabilities.
    """
    if current_user.role != "FACULTY" and current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="My Clubs is only accessible to faculty members.",
        )

    if current_user.role == "ADMIN":
        # Admin can view all active clubs
        clubs = list_clubs(db=db, status_filter="ACTIVE")
    else:
        clubs = list_faculty_assigned_clubs(db=db, faculty_user=current_user)

    return [_format_club_response(db, c) for c in clubs]


# ---------------------------------------------------------------------------
# 3. Admin Club & Capability Management Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/clubs",
    response_model=ClubResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new campus club (Admin only)",
)
def create_new_club(
    payload: ClubCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClubResponse:
    """Admin registration of a student/faculty organization."""
    club = create_club(db=db, creator=current_user, payload=payload)
    return _format_club_response(db, club)


@router.put(
    "/clubs/{club_id}",
    response_model=ClubResponse,
    summary="Update club profile or status (Admin only)",
)
def update_existing_club(
    club_id: int,
    payload: ClubUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClubResponse:
    """Admin updates club metadata or deactivates/activates a club."""
    club = update_club(db=db, updater=current_user, club_id=club_id, payload=payload)
    return _format_club_response(db, club)


@router.post(
    "/admin/capabilities/assign",
    response_model=CapabilityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign coordinator capability to a user (Admin only)",
)
def assign_user_capability(
    payload: CapabilityAssignRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CapabilityResponse:
    """
    Assigns EVENT_COORDINATOR, CLUB_COORDINATOR, or EVENT_DIRECT_PUBLISH.
    Enforces scope type and scope ID validation.
    """
    cap = assign_capability(db=db, assigner=current_user, payload=payload)
    u = cap.user

    scope_name = None
    if cap.scope_type == "CLUB" and cap.scope_id:
        club = db.query(Club).filter(Club.id == cap.scope_id).first()
        scope_name = club.name if club else None

    return CapabilityResponse(
        id=cap.id,
        user_id=cap.user_id,
        user_name=u.name if u else "",
        user_email=u.email if u else "",
        user_role=u.role if u else "",
        capability=cap.capability,
        scope_type=cap.scope_type,
        scope_id=cap.scope_id,
        scope_name=scope_name,
        is_active=cap.is_active,
        starts_at=cap.starts_at.isoformat() if cap.starts_at else None,
        expires_at=cap.expires_at.isoformat() if cap.expires_at else None,
        assigned_by=cap.assigned_by,
        assigned_by_name=current_user.name,
        revocation_reason=cap.revocation_reason,
        created_at=cap.created_at.isoformat() if cap.created_at else datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


@router.post(
    "/admin/capabilities/{capability_id}/revoke",
    response_model=CapabilityResponse,
    summary="Revoke an active coordinator capability (Admin only)",
)
def revoke_user_capability(
    capability_id: int,
    payload: CapabilityRevokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CapabilityResponse:
    """Revokes a capability immediately, cutting off backend permissions."""
    cap = revoke_capability(
        db=db,
        revoker=current_user,
        capability_id=capability_id,
        reason=payload.reason,
    )
    u = cap.user
    return CapabilityResponse(
        id=cap.id,
        user_id=cap.user_id,
        user_name=u.name if u else "",
        user_email=u.email if u else "",
        user_role=u.role if u else "",
        capability=cap.capability,
        scope_type=cap.scope_type,
        scope_id=cap.scope_id,
        is_active=cap.is_active,
        starts_at=cap.starts_at.isoformat() if cap.starts_at else None,
        expires_at=cap.expires_at.isoformat() if cap.expires_at else None,
        assigned_by=cap.assigned_by,
        revocation_reason=cap.revocation_reason,
        created_at=cap.created_at.isoformat() if cap.created_at else datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


@router.get(
    "/admin/capabilities",
    response_model=List[CapabilityResponse],
    summary="List coordinator capabilities (Admin only)",
)
def get_all_capabilities(
    user_id: Optional[int] = Query(None),
    capability: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[CapabilityResponse]:
    """Lists capability records for administrative oversight."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can inspect capability assignments.",
        )

    records = list_capabilities(db=db, user_id=user_id, capability=capability, is_active=is_active)
    resp = []
    for r in records:
        u = r.user
        scope_name = None
        if r.scope_type == "CLUB" and r.scope_id:
            club = db.query(Club).filter(Club.id == r.scope_id).first()
            scope_name = club.name if club else None

        resp.append(
            CapabilityResponse(
                id=r.id,
                user_id=r.user_id,
                user_name=u.name if u else "",
                user_email=u.email if u else "",
                user_role=u.role if u else "",
                capability=r.capability,
                scope_type=r.scope_type,
                scope_id=r.scope_id,
                scope_name=scope_name,
                is_active=r.is_active,
                starts_at=r.starts_at.isoformat() if r.starts_at else None,
                expires_at=r.expires_at.isoformat() if r.expires_at else None,
                assigned_by=r.assigned_by,
                created_at=r.created_at.isoformat(),
            )
        )
    return resp
