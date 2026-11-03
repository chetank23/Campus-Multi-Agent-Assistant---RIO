"""
backend/routes/substitutions.py
-------------------------------
API Router for Faculty Substitution workflows:
- /substitutions/my-classes: Scheduled class occurrences for the authenticated faculty member.
- /substitutions/requests: Create an unavailability request.
- /substitutions/my-requests: View requests submitted by the authenticated faculty member.
- /substitutions/my-assignments: View classes where authenticated faculty is covering as substitute.
- /substitutions/pending: Review queue for Admins & Substitution Coordinators.
- /substitutions/requests/{id}/candidates: Deterministic ranked candidate recommendations.
- /substitutions/requests/{id}/review: Approve or reject a request with optimistic locking.
- /substitutions/requests/{id}/cancel: Cancel an existing request.
- /substitutions/requests/{id}: Retrieve detailed status of a specific substitution request.
- /substitutions/date-view: View effective schedule for a specific date (with substitution overlays).
"""

from __future__ import annotations

import datetime
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models.academic import Faculty, Student
from backend.models.identity import User
from backend.models.space_time import Room, TimeSlot
from backend.models.substitution import FacultySubstitution
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.schemas.substitution import (
    CandidateRecommendationResponse,
    ClassOccurrenceResponse,
    FacultySubstitutionResponse,
    StudentDateClassView,
    SubstitutionRequestCreate,
    SubstitutionReviewActionRequest,
)
from backend.services.event_service import check_user_has_capability
from backend.utils.datetime_utils import utc_now
from backend.models.events import CoordinatorCapability
from backend.services.substitution_service import (
    check_reviewer_authority,
    approve_substitution_request,
    cancel_substitution_request,
    create_substitution_request,
    day_matches_date,
    find_and_rank_substitute_candidates,
    format_substitution_response,
    get_active_substitutions_for_date,
    list_faculty_upcoming_classes,
    reject_substitution_request,
)

router = APIRouter(prefix="/substitutions", tags=["Faculty Substitution"])


@router.get("/my-classes", response_model=List[ClassOccurrenceResponse])
def get_my_classes(
    from_date: Optional[datetime.date] = None,
    days_ahead: int = Query(default=14, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("FACULTY")),
):
    """
    Returns the real upcoming scheduled class occurrences for the authenticated faculty member.
    Includes active substitution request status if unavailability was previously submitted.
    """
    return list_faculty_upcoming_classes(
        db=db,
        faculty_user=current_user,
        from_date=from_date,
        days_ahead=days_ahead,
    )


@router.post(
    "/requests",
    response_model=FacultySubstitutionResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_substitution_request(
    payload: SubstitutionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submits a faculty unavailability request for a specific class on a specific date.
    Strictly verifies ownership, weekday match, and duplicate avoidance.
    """
    sub = create_substitution_request(
        db=db,
        current_user=current_user,
        timetable_entry_id=payload.timetable_entry_id,
        substitution_date=payload.substitution_date,
        reason=payload.reason,
    )
    # Re-query with full joins for response
    full_sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.reviewer),
        )
        .filter(FacultySubstitution.id == sub.id)
        .first()
    )
    assert full_sub is not None
    return format_substitution_response(full_sub, current_user.role)


@router.get("/my-requests", response_model=List[FacultySubstitutionResponse])
def get_my_substitution_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns substitution requests submitted by or concerning the authenticated faculty member.
    """
    query = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.reviewer),
        )
    )
    if current_user.role != "ADMIN":
        fac = db.query(Faculty).filter(Faculty.user_id == current_user.id).first()
        if not fac:
            return []
        query = query.filter(FacultySubstitution.original_faculty_id == fac.id)

    subs = query.order_by(FacultySubstitution.substitution_date.desc(), FacultySubstitution.id.desc()).all()
    return [format_substitution_response(s, current_user.role) for s in subs]


@router.get("/my-assignments", response_model=List[FacultySubstitutionResponse])
def get_my_substitution_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("FACULTY")),
):
    """
    Returns substitution assignments where the authenticated faculty member
    has been appointed to cover another teacher's class.
    """
    fac = db.query(Faculty).filter(Faculty.user_id == current_user.id).first()
    if not fac:
        return []

    subs = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.reviewer),
        )
        .filter(
            FacultySubstitution.substitute_faculty_id == fac.id,
            FacultySubstitution.status == "APPROVED",
        )
        .order_by(FacultySubstitution.substitution_date.asc(), FacultySubstitution.id.asc())
        .all()
    )
    return [format_substitution_response(s, current_user.role) for s in subs]


@router.get("/pending", response_model=List[FacultySubstitutionResponse])
def get_pending_substitutions_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Review queue of pending substitution requests for Admins and Reviewers
    holding SUBSTITUTION_COORDINATOR or SUBSTITUTION_REVIEWER capability.
    """
    is_admin = current_user.role == "ADMIN"
    dept_filter: Optional[Set[int]] = None
    if not is_admin:
        now = utc_now()
        caps = (
            db.query(CoordinatorCapability)
            .filter(
                CoordinatorCapability.user_id == current_user.id,
                CoordinatorCapability.capability.in_(["SUBSTITUTION_COORDINATOR", "SUBSTITUTION_REVIEWER"]),
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
        if not caps:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You lack the required capability to view the substitution review queue.",
            )
        is_global = any(c.scope_type == "GLOBAL" for c in caps)
        if not is_global:
            dept_filter = {c.scope_id for c in caps if c.scope_type == "DEPARTMENT" and c.scope_id is not None}

    query = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.reviewer),
        )
        .filter(FacultySubstitution.status.in_(["REQUESTED", "PROPOSED"]))
    )

    if dept_filter is not None:
        query = query.join(TimetableEntry, FacultySubstitution.timetable_entry_id == TimetableEntry.id).filter(
            TimetableEntry.department_id.in_(dept_filter)
        )

    subs = query.order_by(FacultySubstitution.substitution_date.asc(), FacultySubstitution.id.asc()).all()
    return [format_substitution_response(s, current_user.role) for s in subs]


@router.get("/requests/{id}/candidates", response_model=CandidateRecommendationResponse)
def get_candidate_recommendations(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Provides transparent, deterministic substitute candidate recommendations
    with qualification, clash, availability, and workload breakdowns.
    """
    sub = (
        db.query(FacultySubstitution)
        .options(joinedload(FacultySubstitution.timetable_entry))
        .filter(FacultySubstitution.id == id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substitution request not found.",
        )
    dept_id = sub.timetable_entry.department_id if sub.timetable_entry else None
    if not check_reviewer_authority(db, current_user, dept_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You lack the required capability to inspect candidate recommendations for this department.",
        )

    return find_and_rank_substitute_candidates(db=db, substitution_id=id)


@router.post("/requests/{id}/review", response_model=FacultySubstitutionResponse)
def review_substitution_request(
    id: int,
    payload: SubstitutionReviewActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Executes a review action (APPROVE or REJECT) on a substitution request with optimistic concurrency.
    """
    if payload.action == "APPROVE":
        if not payload.substitute_faculty_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="substitute_faculty_id is required when approving a substitution request.",
            )
        sub = approve_substitution_request(
            db=db,
            reviewer_user=current_user,
            substitution_id=id,
            substitute_faculty_id=payload.substitute_faculty_id,
            expected_version=payload.version,
        )
    elif payload.action == "REJECT":
        if not payload.rejection_reason or len(payload.rejection_reason.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A valid rejection reason (minimum 3 characters) is required when rejecting.",
            )
        sub = reject_substitution_request(
            db=db,
            reviewer_user=current_user,
            substitution_id=id,
            rejection_reason=payload.rejection_reason,
            expected_version=payload.version,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown review action: {payload.action}",
        )

    # Re-query with joins for serialization
    full_sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.reviewer),
        )
        .filter(FacultySubstitution.id == sub.id)
        .first()
    )
    assert full_sub is not None
    return format_substitution_response(full_sub, current_user.role)


@router.post("/requests/{id}/cancel", response_model=FacultySubstitutionResponse)
def cancel_request(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cancels an existing substitution request.
    """
    sub = cancel_substitution_request(
        db=db,
        current_user=current_user,
        substitution_id=id,
    )
    full_sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.reviewer),
        )
        .filter(FacultySubstitution.id == sub.id)
        .first()
    )
    assert full_sub is not None
    return format_substitution_response(full_sub, current_user.role)


@router.get("/requests/{id}", response_model=FacultySubstitutionResponse)
def get_substitution_request_by_id(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves full details of a specific substitution request.
    Respects privacy barriers by masking private reasons for student callers.
    """
    sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.reviewer),
        )
        .filter(FacultySubstitution.id == id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substitution request not found.",
        )

    # Scoped authorization check:
    # 1. Admin: allowed
    # 2. Reviewer with capability for this department/global: allowed
    # 3. Faculty: only if original or appointed substitute
    # 4. Student: only if enrolled in class section
    is_admin = current_user.role == "ADMIN"
    if not is_admin:
        dept_id = sub.timetable_entry.department_id if sub.timetable_entry else None
        is_reviewer = check_reviewer_authority(db, current_user, dept_id)
        if not is_reviewer:
            if current_user.role == "FACULTY":
                fac = db.query(Faculty).filter(Faculty.user_id == current_user.id).first()
                is_party = fac and (sub.original_faculty_id == fac.id or sub.substitute_faculty_id == fac.id)
                if not is_party:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You are not authorized to view this substitution request.",
                    )
            elif current_user.role == "STUDENT":
                student = db.query(Student).filter(Student.user_id == current_user.id).first()
                if not student or (sub.timetable_entry and student.section_id != sub.timetable_entry.section_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You are not authorized to view substitution details for classes outside your enrolled section.",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions.",
                )

    return format_substitution_response(sub, current_user.role)


@router.get("/date-view", response_model=List[StudentDateClassView])
def get_classes_for_date(
    date: datetime.date,
    section_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the effective class schedule for a specific date, overlaying
    approved faculty substitutions while keeping the canonical master schedule intact.
    """
    # If student, default to their enrolled section
    if current_user.role == "STUDENT" and section_id is None:
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if student:
            section_id = student.section_id

    query = (
        db.query(TimetableEntry)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .options(
            joinedload(TimetableEntry.slot),
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
        )
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.status != "CANCELLED",
        )
    )
    if section_id:
        query = query.filter(TimetableEntry.section_id == section_id)

    raw_entries = query.all()

    # Filter to entries matching the weekday of the requested date
    matching_entries = [e for e in raw_entries if e.slot and day_matches_date(e.slot.day, date)]

    # Fetch active substitutions for this date
    sub_map = get_active_substitutions_for_date(db=db, date=date)

    result: List[StudentDateClassView] = []
    for e in matching_entries:
        sub = sub_map.get(e.id)
        is_sub = sub is not None
        orig_fac_name = e.faculty.user.name if (e.faculty and e.faculty.user) else "Unknown"

        effective_fac_name = orig_fac_name
        if is_sub and sub and sub.substitute_faculty and sub.substitute_faculty.user:
            effective_fac_name = sub.substitute_faculty.user.name

        start_str = e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else None
        end_str = e.slot.end_time.strftime("%H:%M") if (e.slot and e.slot.end_time) else None

        result.append(
            StudentDateClassView(
                timetable_entry_id=e.id,
                date=date,
                course_code=e.course.course_code if e.course else None,
                course_name=e.course.course_name if e.course else None,
                room_number=e.room.room_number if e.room else None,
                building_name=e.room.building.name if (e.room and e.room.building) else None,
                start_time=start_str,
                end_time=end_str,
                is_substituted=is_sub,
                faculty_name=effective_fac_name,
                original_faculty_name=orig_fac_name if is_sub else None,
                slot_type=e.slot.slot_type if e.slot else None,
                status=e.status,
            )
        )

    result.sort(key=lambda x: x.start_time or "00:00")
    return result

