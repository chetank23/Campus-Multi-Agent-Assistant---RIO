"""
backend/routes/placements.py
----------------------------
REST API endpoints for CDC Placement Management:
- Placement drive CRUD & lifecycle operations
- Student placement feed with eligibility breakdown
- Pre-flight publication validation
- Dashboard analytics for CDC coordinators
- Student academic records administration
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.identity import User
from backend.routes.auth import get_current_user
from backend.schemas.placements import (
    CdcDashboardStats,
    PlacementDriveActionReason,
    PlacementDriveCreateRequest,
    PlacementDriveResponse,
    PlacementDriveUpdateRequest,
    PlacementDriveValidationResponse,
    StudentAcademicRecordResponse,
    StudentAcademicRecordUpsert,
    StudentEligibilityResult,
)
from backend.services.placement_service import (
    cancel_placement_drive,
    close_placement_drive,
    create_placement_drive,
    evaluate_student_eligibility,
    get_cdc_dashboard_stats,
    get_placement_drive_detail,
    get_student_academic_record,
    list_placement_drives_for_user,
    postpone_placement_drive,
    publish_placement_drive,
    require_cdc_coordinator,
    update_placement_drive,
    upsert_student_academic_record,
    validate_placement_drive,
)
from backend.models.academic import Student

router = APIRouter(prefix="/placements", tags=["CDC Placements"])


# ---------------------------------------------------------------------------
# 1. Placement Drives Feed & Details
# ---------------------------------------------------------------------------

@router.get(
    "/drives",
    response_model=List[PlacementDriveResponse],
    summary="List placement drives for authenticated user",
)
def get_placement_drives(
    status: Optional[str] = Query(None, description="Filter: DRAFT, PUBLISHED, CLOSED, POSTPONED, CANCELLED"),
    job_type: Optional[str] = Query(None, description="FULL_TIME, INTERNSHIP, INTERN_PLUS_FULL_TIME"),
    tier: Optional[str] = Query(None, description="TIER_1, DREAM, SUPER_DREAM, CORE"),
    search: Optional[str] = Query(None, description="Search by title, company, or role"),
    only_eligible: bool = Query(False, description="Filter only eligible drives for student"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns placement drives honoring role barriers:
    - Students see only PUBLISHED, CLOSED, or POSTPONED drives with deterministic eligibility.
    - CDC Coordinators and Admins see drafts and administrative management data.
    """
    return list_placement_drives_for_user(
        db=db,
        current_user=current_user,
        status_filter=status,
        job_type=job_type,
        tier=tier,
        search_query=search,
        only_eligible=only_eligible,
    )


@router.get(
    "/drives/{drive_id}",
    response_model=PlacementDriveResponse,
    summary="Get single placement drive details",
)
def get_drive_by_id(
    drive_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieves single drive details with schedules and caller-specific eligibility evaluation."""
    return get_placement_drive_detail(db=db, drive_id=drive_id, current_user=current_user)


# ---------------------------------------------------------------------------
# 2. CDC Coordinator Management Operations
# ---------------------------------------------------------------------------

@router.post(
    "/drives",
    response_model=PlacementDriveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new placement drive (CDC Coordinator / Admin)",
)
def create_drive(
    payload: PlacementDriveCreateRequest,
    direct_publish: bool = Query(False, description="Directly publish if validation passes"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Creates a new placement drive in DRAFT or PUBLISHED status."""
    drive = create_placement_drive(
        db=db,
        creator=current_user,
        payload=payload,
        direct_publish=direct_publish,
    )
    return get_placement_drive_detail(db=db, drive_id=drive.id, current_user=current_user)


@router.put(
    "/drives/{drive_id}",
    response_model=PlacementDriveResponse,
    summary="Update placement drive details (CDC Coordinator / Admin)",
)
def update_drive(
    drive_id: int,
    payload: PlacementDriveUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Updates permitted drive fields with optimistic concurrency version control."""
    drive = update_placement_drive(
        db=db,
        updater=current_user,
        drive_id=drive_id,
        payload=payload,
    )
    return get_placement_drive_detail(db=db, drive_id=drive.id, current_user=current_user)


@router.post(
    "/drives/validate",
    response_model=PlacementDriveValidationResponse,
    summary="Validate drive criteria, deadline, and duplicates before publishing",
)
def validate_drive(
    payload: PlacementDriveCreateRequest,
    exclude_id: Optional[int] = Query(None, description="Drive ID to exclude when checking duplicates"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlacementDriveValidationResponse:
    """Pre-flight validation check before publishing."""
    require_cdc_coordinator(db, current_user)
    return validate_placement_drive(db=db, payload=payload, exclude_drive_id=exclude_id)


@router.post(
    "/drives/{drive_id}/publish",
    response_model=PlacementDriveResponse,
    summary="Directly publish a validated placement drive",
)
def publish_drive(
    drive_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Directly publishes a validated placement drive and dispatches targeted student notifications."""
    drive = publish_placement_drive(db=db, publisher=current_user, drive_id=drive_id)
    return get_placement_drive_detail(db=db, drive_id=drive.id, current_user=current_user)


@router.post(
    "/drives/{drive_id}/postpone",
    response_model=PlacementDriveResponse,
    summary="Postpone a placement drive with explanation",
)
def postpone_drive(
    drive_id: int,
    payload: PlacementDriveActionReason,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Postpones a drive and alerts registered students."""
    drive = postpone_placement_drive(
        db=db,
        coordinator=current_user,
        drive_id=drive_id,
        reason=payload.reason,
    )
    return get_placement_drive_detail(db=db, drive_id=drive.id, current_user=current_user)


@router.post(
    "/drives/{drive_id}/cancel",
    response_model=PlacementDriveResponse,
    summary="Cancel a scheduled placement drive",
)
def cancel_drive(
    drive_id: int,
    payload: PlacementDriveActionReason,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Cancels a drive and dispatches targeted cancellation notifications."""
    drive = cancel_placement_drive(
        db=db,
        coordinator=current_user,
        drive_id=drive_id,
        reason=payload.reason,
    )
    return get_placement_drive_detail(db=db, drive_id=drive.id, current_user=current_user)


@router.post(
    "/drives/{drive_id}/close",
    response_model=PlacementDriveResponse,
    summary="Close applications for a placement drive",
)
def close_drive(
    drive_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Closes applications for a drive."""
    drive = close_placement_drive(db=db, coordinator=current_user, drive_id=drive_id)
    return get_placement_drive_detail(db=db, drive_id=drive.id, current_user=current_user)


# ---------------------------------------------------------------------------
# 3. Student Deterministic Eligibility Check
# ---------------------------------------------------------------------------

@router.get(
    "/drives/{drive_id}/eligibility",
    response_model=StudentEligibilityResult,
    summary="Check student deterministic eligibility for a drive",
)
def check_student_drive_eligibility(
    drive_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudentEligibilityResult:
    """Evaluates authenticated student's eligibility using structured rules."""
    if current_user.role != "STUDENT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eligibility evaluation is applicable only to students.",
        )

    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found for authenticated user.",
        )

    drive_dict = get_placement_drive_detail(db=db, drive_id=drive_id, current_user=current_user)
    from backend.models.placements import PlacementDrive
    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found.")

    return evaluate_student_eligibility(db=db, drive=drive, student=student)


# ---------------------------------------------------------------------------
# 4. Dashboard Stats
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard",
    response_model=CdcDashboardStats,
    summary="CDC Coordinator operational dashboard statistics",
)
def get_dashboard_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Returns overview stats on placement drives."""
    return get_cdc_dashboard_stats(db=db, user=current_user)


# ---------------------------------------------------------------------------
# 5. Student Academic Records Management
# ---------------------------------------------------------------------------

@router.post(
    "/academic-records",
    response_model=StudentAcademicRecordResponse,
    summary="Upsert student academic record (CDC Coordinator / Admin)",
)
def upsert_academic_record(
    payload: StudentAcademicRecordUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Creates or updates authoritative CGPA, grading scale, backlogs, and graduation year for a student."""
    rec = upsert_student_academic_record(db=db, updater=current_user, payload=payload)
    student = rec.student
    return {
        "id": rec.id,
        "student_id": rec.student_id,
        "student_name": student.user.name if (student and student.user) else "Student",
        "student_usn": student.student_id if student else "",
        "department_name": student.department.name if (student and student.department) else None,
        "program_name": student.program.program_name if (student and student.program) else None,
        "cgpa": rec.cgpa,
        "grading_scale": rec.grading_scale,
        "percentage": rec.percentage,
        "active_backlogs": rec.active_backlogs,
        "total_backlogs": rec.total_backlogs,
        "graduation_year": rec.graduation_year,
        "tenth_percentage": rec.tenth_percentage,
        "twelfth_percentage": rec.twelfth_percentage,
        "is_verified": rec.is_verified,
        "verified_by_name": rec.verifier.name if rec.verifier else None,
        "updated_at": rec.updated_at.isoformat(),
    }


@router.get(
    "/academic-records/{student_id}",
    response_model=StudentAcademicRecordResponse,
    summary="Get student academic record by student ID",
)
def get_academic_record(
    student_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieves academic record. Students can only inspect their own record."""
    if current_user.role == "STUDENT":
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student or student.id != student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only view your own academic record.",
            )
    else:
        require_cdc_coordinator(db, current_user)

    rec = get_student_academic_record(db=db, student_id=student_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Academic record for student #{student_id} not found.",
        )

    student = rec.student
    return {
        "id": rec.id,
        "student_id": rec.student_id,
        "student_name": student.user.name if (student and student.user) else "Student",
        "student_usn": student.student_id if student else "",
        "department_name": student.department.name if (student and student.department) else None,
        "program_name": student.program.program_name if (student and student.program) else None,
        "cgpa": rec.cgpa,
        "grading_scale": rec.grading_scale,
        "percentage": rec.percentage,
        "active_backlogs": rec.active_backlogs,
        "total_backlogs": rec.total_backlogs,
        "graduation_year": rec.graduation_year,
        "tenth_percentage": rec.tenth_percentage,
        "twelfth_percentage": rec.twelfth_percentage,
        "is_verified": rec.is_verified,
        "verified_by_name": rec.verifier.name if rec.verifier else None,
        "updated_at": rec.updated_at.isoformat(),
    }

