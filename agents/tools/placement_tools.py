"""
agents/tools/placement_tools.py
-------------------------------
Authoritative LangGraph agent tools for CDC Placement Management:
- Placement drive draft creation, validation, publication, update, and cancellation
- Student placement listings with deterministic eligibility evaluation
- Deadline, venue, and multi-round selection schedule inspection
- Grounded strictly in PostgreSQL placement records
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.academic import Student
from backend.models.placements import PlacementDrive, PlacementSchedule
from backend.schemas.placements import (
    PlacementDriveCreateRequest,
    PlacementDriveUpdateRequest,
    PlacementScheduleCreate,
)
from backend.services.placement_service import (
    cancel_placement_drive,
    create_placement_drive,
    evaluate_student_eligibility,
    get_placement_drive_detail,
    list_placement_drives_for_user,
    publish_placement_drive,
    require_cdc_coordinator,
    update_placement_drive,
    validate_placement_drive,
)


def _parse_datetime(val: Any) -> Optional[datetime.datetime]:
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val
    try:
        return datetime.datetime.fromisoformat(str(val))
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(str(val), fmt)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# 1. Student Placement Queries
# ---------------------------------------------------------------------------

def list_published_placement_drives_data(
    db: Session,
    user: User,
    job_type: Optional[str] = None,
    tier: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Lists published placement drives visible to the authenticated user."""
    drives = list_placement_drives_for_user(
        db=db,
        current_user=user,
        status_filter="PUBLISHED" if user.role == "STUDENT" else None,
        job_type=job_type,
        tier=tier,
        search_query=search,
    )
    return {
        "count": len(drives),
        "drives": drives[:20],
    }


def list_my_eligible_drives_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """Lists only placement drives where authenticated student meets all deterministic criteria."""
    if user.role != "STUDENT":
        return {
            "eligible": False,
            "error": "Eligible drives lookup is only applicable for student accounts.",
            "drives": [],
        }

    drives = list_placement_drives_for_user(
        db=db,
        current_user=user,
        only_eligible=True,
    )
    return {
        "count": len(drives),
        "eligible_drives": drives,
    }


def get_placement_drive_details_data(
    db: Session,
    user: User,
    drive_id: Optional[int] = None,
    company_name: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetches details of a specific placement drive with eligibility breakdown."""
    if drive_id:
        try:
            return get_placement_drive_detail(db=db, drive_id=drive_id, current_user=user)
        except Exception as e:
            return {"error": str(e)}

    # Lookup by company name or title
    drives = list_placement_drives_for_user(db=db, current_user=user)
    if company_name:
        cn = company_name.strip().lower()
        match = next((d for d in drives if cn in d["company_name"].lower()), None)
        if match:
            return match

    if title:
        t = title.strip().lower()
        match = next((d for d in drives if t in d["title"].lower()), None)
        if match:
            return match

    return {"error": f"No placement drive found matching query (company: {company_name}, title: {title})."}


def get_drive_deadlines_and_schedule_data(
    db: Session,
    user: User,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns application deadlines and interview/assessment schedules for upcoming drives."""
    drives = list_placement_drives_for_user(db=db, current_user=user)
    if company_name:
        cn = company_name.strip().lower()
        drives = [d for d in drives if cn in d["company_name"].lower()]

    items = []
    for d in drives:
        items.append({
            "drive_id": d["id"],
            "company_name": d["company_name"],
            "title": d["title"],
            "job_role": d["job_role"],
            "application_deadline": d["application_deadline"],
            "is_deadline_passed": d["is_deadline_passed"],
            "schedules_count": len(d["schedules"]),
            "schedules": d["schedules"],
        })

    return {
        "count": len(items),
        "deadlines_and_schedules": items,
    }


def get_student_drive_eligibility_data(
    db: Session,
    user: User,
    drive_id: Optional[int] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic eligibility check for student caller against a target company drive."""
    if user.role != "STUDENT":
        return {
            "error": "Eligibility checks are only applicable to student callers.",
            "is_eligible": False,
        }

    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        return {"error": "Student profile record not found.", "is_eligible": False}

    target_drive: Optional[PlacementDrive] = None
    if drive_id:
        target_drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    elif company_name:
        cn = company_name.strip().lower()
        target_drive = (
            db.query(PlacementDrive)
            .filter(
                func.lower(PlacementDrive.company_name).ilike(f"%{cn}%"),
                PlacementDrive.status == "PUBLISHED",
            )
            .first()
        )

    if not target_drive:
        return {"error": f"Placement drive for '{company_name or drive_id}' was not found or is not published."}

    res = evaluate_student_eligibility(db=db, drive=target_drive, student=student)
    return {
        "company_name": target_drive.company_name,
        "title": target_drive.title,
        "job_role": target_drive.job_role,
        "status": res.status,
        "is_eligible": res.is_eligible,
        "reasons": res.reasons,
        "criteria_breakdown": res.criteria_breakdown,
    }


# ---------------------------------------------------------------------------
# 2. CDC Coordinator Management Tools
# ---------------------------------------------------------------------------

def create_placement_drive_draft_data(
    db: Session,
    user: User,
    company_name: str,
    title: str,
    job_role: str,
    application_deadline: str,
    job_type: str = "FULL_TIME",
    work_location: Optional[str] = None,
    compensation_details: Optional[str] = None,
    min_cgpa: Optional[float] = None,
    graduation_year: Optional[int] = None,
    max_active_backlogs: Optional[int] = None,
    eligible_department_ids: Optional[List[int]] = None,
    additional_criteria: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a new placement drive draft (CDC Coordinator / Admin only)."""
    try:
        require_cdc_coordinator(db, user)
    except HTTPException as e:
        return {"error": e.detail}

    dl = _parse_datetime(application_deadline)
    if not dl:
        return {"error": f"Invalid application deadline '{application_deadline}'. Use YYYY-MM-DD HH:MM format."}

    jt = "FULL_TIME"
    if job_type.upper() in ("INTERNSHIP", "INTERN_PLUS_FULL_TIME", "FULL_TIME"):
        jt = job_type.upper()

    req = PlacementDriveCreateRequest(
        company_name=company_name,
        title=title,
        job_role=job_role,
        application_deadline=dl,
        job_type=jt,  # type: ignore
        work_location=work_location,
        compensation_details=compensation_details,
        min_cgpa=min_cgpa,
        graduation_year=graduation_year,
        max_active_backlogs=max_active_backlogs,
        eligible_department_ids=eligible_department_ids,
        additional_criteria=additional_criteria,
    )

    try:
        drive = create_placement_drive(db=db, creator=user, payload=req, direct_publish=False)
        return {
            "success": True,
            "drive_id": drive.id,
            "title": drive.title,
            "company_name": drive.company_name,
            "status": drive.status,
            "message": f"Placement drive draft #{drive.id} created successfully.",
        }
    except Exception as e:
        return {"error": str(e)}


def validate_placement_drive_data(
    db: Session,
    user: User,
    drive_id: int,
) -> Dict[str, Any]:
    """Performs safety validation and checks eligible candidate pool before publishing."""
    try:
        require_cdc_coordinator(db, user)
    except HTTPException as e:
        return {"error": e.detail}

    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        return {"error": f"Placement drive #{drive_id} not found."}

    req = PlacementDriveCreateRequest(
        company_name=drive.company_name,
        title=drive.title,
        job_role=drive.job_role,
        application_deadline=drive.application_deadline,
        eligible_department_ids=drive.eligible_department_ids,
        eligible_program_ids=drive.eligible_program_ids,
        eligible_batch_ids=drive.eligible_batch_ids,
        graduation_year=drive.graduation_year,
        min_cgpa=drive.min_cgpa,
        grading_scale=drive.grading_scale,
        min_percentage=drive.min_percentage,
        max_active_backlogs=drive.max_active_backlogs,
        max_total_backlogs=drive.max_total_backlogs,
    )
    val = validate_placement_drive(db=db, payload=req, exclude_drive_id=drive.id)
    return {
        "drive_id": drive.id,
        "is_valid": val.is_valid,
        "errors": val.errors,
        "warnings": val.warnings,
        "eligible_students_count": val.eligible_students_count,
        "likely_duplicates": val.likely_duplicates,
    }


def publish_placement_drive_data(
    db: Session,
    user: User,
    drive_id: int,
) -> Dict[str, Any]:
    """Publishes a validated placement drive and dispatches student notifications."""
    try:
        drive = publish_placement_drive(db=db, publisher=user, drive_id=drive_id)
        return {
            "success": True,
            "drive_id": drive.id,
            "title": drive.title,
            "company_name": drive.company_name,
            "status": drive.status,
            "published_at": drive.published_at.isoformat() if drive.published_at else None,
            "message": f"Placement drive '{drive.title}' published successfully to student portal.",
        }
    except Exception as e:
        return {"error": str(e)}


def update_placement_drive_data(
    db: Session,
    user: User,
    drive_id: int,
    compensation_details: Optional[str] = None,
    application_deadline: Optional[str] = None,
    work_location: Optional[str] = None,
    additional_criteria: Optional[str] = None,
    version: Optional[int] = None,
) -> Dict[str, Any]:
    """Updates an existing placement drive with optimistic concurrency locking."""
    dl = _parse_datetime(application_deadline) if application_deadline else None
    req = PlacementDriveUpdateRequest(
        compensation_details=compensation_details,
        application_deadline=dl,
        work_location=work_location,
        additional_criteria=additional_criteria,
        version=version,
    )
    try:
        drive = update_placement_drive(db=db, updater=user, drive_id=drive_id, payload=req)
        return {
            "success": True,
            "drive_id": drive.id,
            "title": drive.title,
            "version": drive.version,
            "message": f"Placement drive #{drive.id} updated successfully.",
        }
    except Exception as e:
        return {"error": str(e)}


def cancel_placement_drive_data(
    db: Session,
    user: User,
    drive_id: int,
    reason: str,
) -> Dict[str, Any]:
    """Cancels a scheduled or published placement drive with reason."""
    try:
        drive = cancel_placement_drive(db=db, coordinator=user, drive_id=drive_id, reason=reason)
        return {
            "success": True,
            "drive_id": drive.id,
            "title": drive.title,
            "status": drive.status,
            "cancellation_reason": drive.cancellation_reason,
            "message": f"Placement drive '{drive.title}' cancelled.",
        }
    except Exception as e:
        return {"error": str(e)}
