"""
backend/services/placement_service.py
-------------------------------------
Authoritative domain service for CDC Placement Management:
1. CDC Coordinator Capability Verification (institutional & department scopes)
2. Deterministic Eligibility Engine (programs, departments, batches, graduation year, CGPA, backlogs)
3. Pre-flight Publication Validation & Duplicate Detection
4. Placement Drive Lifecycle (DRAFT, PUBLISHED, CLOSED, POSTPONED, CANCELLED)
5. Selection Rounds Scheduling
6. Student Placement Feed with Role-Based Privacy Barriers
7. Bulk Notifications & Audit Logging
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, joinedload

from backend.models.identity import User
from backend.models.events import CoordinatorCapability
from backend.models.academic import Department, Program, Batch, Student
from backend.models.placements import PlacementDrive, PlacementSchedule, StudentAcademicRecord
from backend.models.space_time import Room
from backend.models.workflow import AuditLog, Notification
from backend.schemas.placements import (
    PlacementDriveCreateRequest,
    PlacementDriveResponse,
    PlacementDriveUpdateRequest,
    PlacementDriveValidationResponse,
    PlacementScheduleCreate,
    PlacementScheduleResponse,
    StudentAcademicRecordResponse,
    StudentAcademicRecordUpsert,
    StudentEligibilityResult,
    CdcDashboardStats,
)
from backend.services.event_service import check_user_has_capability
from backend.services.notification_service import create_bulk_notifications, create_notification


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# 1. CDC Coordinator Capability Authorization
# ---------------------------------------------------------------------------

def check_user_is_cdc_coordinator(
    db: Session,
    user: User,
    department_id: Optional[int] = None,
) -> bool:
    """
    Verifies if the user is an authorized CDC Coordinator.
    - Admins always have global CDC authority.
    - Other users must possess an active CDC_COORDINATOR capability
      with GLOBAL scope or DEPARTMENT scope matching department_id.
    """
    if user.role == "ADMIN":
        return True

    now = utc_now()
    caps = (
        db.query(CoordinatorCapability)
        .filter(
            CoordinatorCapability.user_id == user.id,
            CoordinatorCapability.capability == "CDC_COORDINATOR",
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
        return False

    for c in caps:
        if c.scope_type == "GLOBAL":
            return True
        if c.scope_type == "DEPARTMENT":
            if department_id is None or c.scope_id is None or c.scope_id == department_id:
                return True

    return False


def require_cdc_coordinator(
    db: Session,
    user: User,
    department_id: Optional[int] = None,
) -> None:
    """Enforces CDC Coordinator capability, raising HTTP 403 if unauthorized."""
    if not check_user_is_cdc_coordinator(db, user, department_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not possess the required CDC_COORDINATOR capability.",
        )


# ---------------------------------------------------------------------------
# 2. Deterministic Eligibility Engine
# ---------------------------------------------------------------------------

def evaluate_student_eligibility(
    db: Session,
    drive: PlacementDrive,
    student: Student,
) -> StudentEligibilityResult:
    """
    Authoritative deterministic evaluation of student eligibility against drive criteria.
    Returns:
      - status: ELIGIBLE | NOT_ELIGIBLE | CANNOT_DETERMINE
      - is_eligible: bool
      - reasons: list of explanatory lines
      - criteria_breakdown: detailed status per evaluated dimension
    """
    reasons: List[str] = []
    cannot_determine_reasons: List[str] = []
    not_eligible_reasons: List[str] = []
    breakdown: Dict[str, Any] = {}

    # 1. Department / Branch Check
    if drive.eligible_department_ids and len(drive.eligible_department_ids) > 0:
        if not student.department_id:
            cannot_determine_reasons.append("Student department record is missing.")
            breakdown["department"] = {"status": "MISSING", "required": drive.eligible_department_ids}
        elif student.department_id not in drive.eligible_department_ids:
            dept_name = student.department.name if student.department else f"Dept #{student.department_id}"
            not_eligible_reasons.append(f"Department '{dept_name}' is not in the eligible branches list.")
            breakdown["department"] = {"status": "FAIL", "student_dept_id": student.department_id, "required": drive.eligible_department_ids}
        else:
            dept_name = student.department.name if student.department else f"Dept #{student.department_id}"
            reasons.append(f"Department '{dept_name}' meets branch eligibility.")
            breakdown["department"] = {"status": "PASS", "student_dept_id": student.department_id}
    else:
        breakdown["department"] = {"status": "ALL_ELIGIBLE"}

    # 2. Program Check
    if drive.eligible_program_ids and len(drive.eligible_program_ids) > 0:
        if not student.program_id:
            cannot_determine_reasons.append("Student program record is missing.")
            breakdown["program"] = {"status": "MISSING", "required": drive.eligible_program_ids}
        elif student.program_id not in drive.eligible_program_ids:
            prog_name = student.program.program_name if student.program else f"Program #{student.program_id}"
            not_eligible_reasons.append(f"Degree/Program '{prog_name}' is not eligible for this drive.")
            breakdown["program"] = {"status": "FAIL", "student_program_id": student.program_id, "required": drive.eligible_program_ids}
        else:
            reasons.append("Degree/Program matches eligible criteria.")
            breakdown["program"] = {"status": "PASS"}
    else:
        breakdown["program"] = {"status": "ALL_ELIGIBLE"}

    # 3. Batch Check
    if drive.eligible_batch_ids and len(drive.eligible_batch_ids) > 0:
        if not student.batch_id:
            cannot_determine_reasons.append("Student batch record is missing.")
            breakdown["batch"] = {"status": "MISSING", "required": drive.eligible_batch_ids}
        elif student.batch_id not in drive.eligible_batch_ids:
            not_eligible_reasons.append("Current batch is not targeted for this placement drive.")
            breakdown["batch"] = {"status": "FAIL"}
        else:
            reasons.append("Batch matches drive target.")
            breakdown["batch"] = {"status": "PASS"}

    # 4. Academic Metrics Check (CGPA, Backlogs, Grad Year)
    # Fetch authoritative student academic record
    acad = (
        db.query(StudentAcademicRecord)
        .filter(StudentAcademicRecord.student_id == student.id)
        .first()
    )

    needs_acad_record = any([
        drive.graduation_year is not None,
        drive.min_cgpa is not None,
        drive.min_percentage is not None,
        drive.max_active_backlogs is not None,
        drive.max_total_backlogs is not None,
    ])

    if needs_acad_record and not acad:
        cannot_determine_reasons.append(
            "Verified student academic record (CGPA, backlogs, graduation year) is not on file in CDC database."
        )
        breakdown["academic_record"] = {"status": "MISSING"}
    elif acad:
        # A. Graduation Year
        if drive.graduation_year is not None:
            if acad.graduation_year is None:
                cannot_determine_reasons.append("Student graduation year record is missing.")
                breakdown["graduation_year"] = {"status": "MISSING", "required": drive.graduation_year}
            elif acad.graduation_year != drive.graduation_year:
                not_eligible_reasons.append(
                    f"Graduation year ({acad.graduation_year}) does not match drive requirement ({drive.graduation_year})."
                )
                breakdown["graduation_year"] = {
                    "status": "FAIL",
                    "student_val": acad.graduation_year,
                    "required": drive.graduation_year,
                }
            else:
                reasons.append(f"Graduation batch year {acad.graduation_year} matches drive requirements.")
                breakdown["graduation_year"] = {"status": "PASS", "val": acad.graduation_year}

        # B. CGPA & Grading Scale Check
        if drive.min_cgpa is not None:
            if acad.cgpa is None:
                cannot_determine_reasons.append("Authoritative student CGPA record is missing.")
                breakdown["cgpa"] = {"status": "MISSING", "required": drive.min_cgpa}
            else:
                # Scale normalization if necessary
                if acad.grading_scale != drive.grading_scale and acad.grading_scale > 0:
                    normalized_cgpa = (acad.cgpa / acad.grading_scale) * drive.grading_scale
                else:
                    normalized_cgpa = acad.cgpa

                if round(normalized_cgpa, 2) < round(drive.min_cgpa, 2):
                    not_eligible_reasons.append(
                        f"Student CGPA ({acad.cgpa:.2f}/{acad.grading_scale:.1f}) is below the required threshold of {drive.min_cgpa:.2f}/{drive.grading_scale:.1f}."
                    )
                    breakdown["cgpa"] = {
                        "status": "FAIL",
                        "student_val": acad.cgpa,
                        "student_scale": acad.grading_scale,
                        "required": drive.min_cgpa,
                        "required_scale": drive.grading_scale,
                    }
                else:
                    reasons.append(
                        f"CGPA ({acad.cgpa:.2f}/{acad.grading_scale:.1f}) meets or exceeds the minimum of {drive.min_cgpa:.2f}."
                    )
                    breakdown["cgpa"] = {
                        "status": "PASS",
                        "student_val": acad.cgpa,
                        "required": drive.min_cgpa,
                    }

        # C. Percentage Check
        if drive.min_percentage is not None:
            if acad.percentage is None:
                cannot_determine_reasons.append("Aggregate percentage record is missing.")
                breakdown["percentage"] = {"status": "MISSING", "required": drive.min_percentage}
            elif acad.percentage < drive.min_percentage:
                not_eligible_reasons.append(
                    f"Aggregate percentage ({acad.percentage:.1f}%) is below the minimum required ({drive.min_percentage:.1f}%)."
                )
                breakdown["percentage"] = {"status": "FAIL", "student_val": acad.percentage, "required": drive.min_percentage}
            else:
                reasons.append(f"Aggregate percentage ({acad.percentage:.1f}%) satisfies requirement.")
                breakdown["percentage"] = {"status": "PASS", "student_val": acad.percentage}

        # D. Active Backlogs Check
        if drive.max_active_backlogs is not None:
            if acad.active_backlogs is None:
                cannot_determine_reasons.append("Active backlogs count is not verified.")
                breakdown["active_backlogs"] = {"status": "MISSING", "required": drive.max_active_backlogs}
            elif acad.active_backlogs > drive.max_active_backlogs:
                not_eligible_reasons.append(
                    f"Active backlogs ({acad.active_backlogs}) exceeds the maximum allowed limit of {drive.max_active_backlogs}."
                )
                breakdown["active_backlogs"] = {
                    "status": "FAIL",
                    "student_val": acad.active_backlogs,
                    "max_allowed": drive.max_active_backlogs,
                }
            else:
                reasons.append(
                    f"Active backlogs ({acad.active_backlogs}) within allowed limit (max {drive.max_active_backlogs})."
                )
                breakdown["active_backlogs"] = {"status": "PASS", "val": acad.active_backlogs}

        # E. Total Backlogs History Check
        if drive.max_total_backlogs is not None:
            if acad.total_backlogs is None:
                cannot_determine_reasons.append("Total backlog history record is missing.")
                breakdown["total_backlogs"] = {"status": "MISSING"}
            elif acad.total_backlogs > drive.max_total_backlogs:
                not_eligible_reasons.append(
                    f"Total backlog history ({acad.total_backlogs}) exceeds the maximum limit of {drive.max_total_backlogs}."
                )
                breakdown["total_backlogs"] = {"status": "FAIL", "student_val": acad.total_backlogs}
            else:
                reasons.append(f"Total backlog history ({acad.total_backlogs}) satisfies criteria.")
                breakdown["total_backlogs"] = {"status": "PASS", "val": acad.total_backlogs}

    # Synthesize Final Determination
    if not_eligible_reasons:
        final_status = "NOT_ELIGIBLE"
        is_eligible = False
        all_reasons = not_eligible_reasons + cannot_determine_reasons + reasons
    elif cannot_determine_reasons:
        final_status = "CANNOT_DETERMINE"
        is_eligible = False
        all_reasons = cannot_determine_reasons + reasons
    else:
        final_status = "ELIGIBLE"
        is_eligible = True
        all_reasons = reasons if reasons else ["Student meets all specified placement criteria."]

    return StudentEligibilityResult(
        status=final_status,
        is_eligible=is_eligible,
        reasons=all_reasons,
        criteria_breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# 3. Pre-flight Validation & Duplicate Detection
# ---------------------------------------------------------------------------

def validate_placement_drive(
    db: Session,
    payload: PlacementDriveCreateRequest,
    exclude_drive_id: Optional[int] = None,
) -> PlacementDriveValidationResponse:
    """Pre-flight safety inspection before publishing or saving."""
    errors: List[str] = []
    warnings: List[str] = []
    now = utc_now()

    # 1. Deadline Check
    if payload.application_deadline.tzinfo:
        app_dl = payload.application_deadline.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    else:
        app_dl = payload.application_deadline

    if app_dl <= now.replace(tzinfo=None):
        errors.append("Application deadline must be set in the future.")

    # 2. Schedule Checks
    if payload.schedules:
        for s in payload.schedules:
            st = s.start_time.replace(tzinfo=None) if s.start_time.tzinfo else s.start_time
            et = s.end_time.replace(tzinfo=None) if s.end_time.tzinfo else s.end_time
            if st >= et:
                errors.append(f"Schedule round '{s.title}': Start time must precede end time.")
            if st < app_dl:
                warnings.append(
                    f"Schedule round '{s.title}' starts before the application deadline ({app_dl.strftime('%Y-%m-%d %H:%M')})."
                )

    # 3. Duplicate Detection
    dup_query = db.query(PlacementDrive).filter(
        PlacementDrive.company_name.ilike(payload.company_name.strip()),
        PlacementDrive.title.ilike(payload.title.strip()),
        PlacementDrive.status.in_(["PUBLISHED", "DRAFT", "POSTPONED"]),
    )
    if exclude_drive_id:
        dup_query = dup_query.filter(PlacementDrive.id != exclude_drive_id)

    duplicates = dup_query.all()
    dup_titles = [f"#{d.id}: {d.title} ({d.status})" for d in duplicates]
    if duplicates:
        warnings.append(
            f"Likely duplicate drive detected for company '{payload.company_name}': {', '.join(dup_titles)}."
        )

    # 4. Compute Estimated Eligible Student Pool
    student_query = db.query(Student)
    if payload.eligible_department_ids:
        student_query = student_query.filter(Student.department_id.in_(payload.eligible_department_ids))
    if payload.eligible_program_ids:
        student_query = student_query.filter(Student.program_id.in_(payload.eligible_program_ids))
    if payload.eligible_batch_ids:
        student_query = student_query.filter(Student.batch_id.in_(payload.eligible_batch_ids))

    candidate_students = student_query.all()

    # Create dummy drive for evaluation
    dummy_drive = PlacementDrive(
        company_name=payload.company_name,
        title=payload.title,
        job_role=payload.job_role,
        eligible_department_ids=payload.eligible_department_ids,
        eligible_program_ids=payload.eligible_program_ids,
        eligible_batch_ids=payload.eligible_batch_ids,
        graduation_year=payload.graduation_year,
        min_cgpa=payload.min_cgpa,
        grading_scale=payload.grading_scale,
        min_percentage=payload.min_percentage,
        max_active_backlogs=payload.max_active_backlogs,
        max_total_backlogs=payload.max_total_backlogs,
        application_deadline=app_dl,
    )

    eligible_count = 0
    for s in candidate_students:
        res = evaluate_student_eligibility(db, dummy_drive, s)
        if res.is_eligible:
            eligible_count += 1

    return PlacementDriveValidationResponse(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        eligible_students_count=eligible_count,
        likely_duplicates=dup_titles,
    )


# ---------------------------------------------------------------------------
# 4. Placement Drive CRUD & Lifecycle
# ---------------------------------------------------------------------------

def create_placement_drive(
    db: Session,
    creator: User,
    payload: PlacementDriveCreateRequest,
    direct_publish: bool = False,
) -> PlacementDrive:
    """Creates a new placement drive, optionally publishing directly."""
    require_cdc_coordinator(db, creator)

    # Validation
    val_resp = validate_placement_drive(db, payload)
    if direct_publish and not val_resp.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot publish drive with validation errors: {'; '.join(val_resp.errors)}",
        )

    now = utc_now()
    initial_status = "PUBLISHED" if direct_publish else "DRAFT"

    drive = PlacementDrive(
        company_name=payload.company_name.strip(),
        company_description=payload.company_description,
        company_website=payload.company_website,
        company_logo_url=payload.company_logo_url,
        title=payload.title.strip(),
        job_role=payload.job_role.strip(),
        job_description=payload.job_description,
        job_type=payload.job_type,
        work_location=payload.work_location,
        compensation_details=payload.compensation_details,
        tier=payload.tier,
        eligible_department_ids=payload.eligible_department_ids,
        eligible_program_ids=payload.eligible_program_ids,
        eligible_batch_ids=payload.eligible_batch_ids,
        graduation_year=payload.graduation_year,
        min_cgpa=payload.min_cgpa,
        grading_scale=payload.grading_scale,
        min_percentage=payload.min_percentage,
        max_active_backlogs=payload.max_active_backlogs,
        max_total_backlogs=payload.max_total_backlogs,
        allowed_genders=payload.allowed_genders,
        additional_criteria=payload.additional_criteria,
        application_deadline=payload.application_deadline.replace(tzinfo=None) if payload.application_deadline.tzinfo else payload.application_deadline,
        application_link=payload.application_link,
        application_instructions=payload.application_instructions,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        required_documents=payload.required_documents,
        status=initial_status,
        published_at=now if direct_publish else None,
        coordinator_id=creator.id,
        created_by=creator.id,
        version=1,
    )
    db.add(drive)
    db.flush()

    # Add schedule rounds
    if payload.schedules:
        for s in payload.schedules:
            st = s.start_time.replace(tzinfo=None) if s.start_time.tzinfo else s.start_time
            et = s.end_time.replace(tzinfo=None) if s.end_time.tzinfo else s.end_time
            sch = PlacementSchedule(
                drive_id=drive.id,
                round_type=s.round_type,
                round_order=s.round_order,
                title=s.title,
                start_time=st,
                end_time=et,
                venue_name=s.venue_name,
                room_id=s.room_id,
                is_online=s.is_online,
                meeting_link=s.meeting_link,
                instructions=s.instructions,
            )
            db.add(sch)
        db.flush()

    action_name = "PLACEMENT_DRIVE_PUBLISHED" if direct_publish else "PLACEMENT_DRIVE_DRAFT_CREATED"
    db.add(
        AuditLog(
            user_id=creator.id,
            action=action_name,
            entity_type="PlacementDrive",
            entity_id=drive.id,
            new_value={"title": drive.title, "company": drive.company_name, "status": drive.status},
        )
    )

    if direct_publish:
        _notify_eligible_students_drive_published(db, drive)

    db.commit()
    db.refresh(drive)
    return drive


def update_placement_drive(
    db: Session,
    updater: User,
    drive_id: int,
    payload: PlacementDriveUpdateRequest,
) -> PlacementDrive:
    """Updates placement drive details with optimistic concurrency version control."""
    require_cdc_coordinator(db, updater)

    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placement drive #{drive_id} not found.",
        )

    # Optimistic locking
    if payload.version is not None and payload.version != drive.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict: Placement drive #{drive_id} was modified by another transaction (expected v{payload.version}, found v{drive.version}).",
        )

    old_vals = {
        "title": drive.title,
        "company_name": drive.company_name,
        "application_deadline": drive.application_deadline.isoformat(),
        "status": drive.status,
    }

    # Update basic fields if provided
    for f in [
        "company_name", "company_description", "company_website", "company_logo_url",
        "title", "job_role", "job_description", "job_type", "work_location",
        "compensation_details", "tier", "eligible_department_ids", "eligible_program_ids",
        "eligible_batch_ids", "graduation_year", "min_cgpa", "min_percentage",
        "max_active_backlogs", "max_total_backlogs", "allowed_genders",
        "additional_criteria", "application_link", "application_instructions",
        "contact_email", "contact_phone", "required_documents",
    ]:
        val = getattr(payload, f, None)
        if val is not None:
            setattr(drive, f, val)

    if payload.grading_scale is not None:
        drive.grading_scale = payload.grading_scale

    if payload.application_deadline is not None:
        dl = payload.application_deadline.replace(tzinfo=None) if payload.application_deadline.tzinfo else payload.application_deadline
        drive.application_deadline = dl

    # Update schedules if provided
    if payload.schedules is not None:
        db.query(PlacementSchedule).filter(PlacementSchedule.drive_id == drive.id).delete()
        for s in payload.schedules:
            st = s.start_time.replace(tzinfo=None) if s.start_time.tzinfo else s.start_time
            et = s.end_time.replace(tzinfo=None) if s.end_time.tzinfo else s.end_time
            sch = PlacementSchedule(
                drive_id=drive.id,
                round_type=s.round_type,
                round_order=s.round_order,
                title=s.title,
                start_time=st,
                end_time=et,
                venue_name=s.venue_name,
                room_id=s.room_id,
                is_online=s.is_online,
                meeting_link=s.meeting_link,
                instructions=s.instructions,
            )
            db.add(sch)

    drive.version += 1
    drive.updated_by = updater.id
    drive.updated_at = utc_now()
    db.flush()

    db.add(
        AuditLog(
            user_id=updater.id,
            action="PLACEMENT_DRIVE_UPDATED",
            entity_type="PlacementDrive",
            entity_id=drive.id,
            old_value=old_vals,
            new_value={"title": drive.title, "status": drive.status, "version": drive.version},
        )
    )

    # If already published, notify students of schedule/deadline update
    if drive.status == "PUBLISHED":
        _notify_eligible_students_drive_updated(db, drive)

    db.commit()
    db.refresh(drive)
    return drive


def publish_placement_drive(
    db: Session,
    publisher: User,
    drive_id: int,
) -> PlacementDrive:
    """Directly publishes a validated placement drive."""
    require_cdc_coordinator(db, publisher)

    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placement drive #{drive_id} not found.",
        )

    if drive.status == "PUBLISHED":
        return drive  # Idempotent

    # Pre-flight check
    dummy_req = PlacementDriveCreateRequest(
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
        schedules=[
            PlacementScheduleCreate(
                round_type=s.round_type,
                round_order=s.round_order,
                title=s.title,
                start_time=s.start_time,
                end_time=s.end_time,
                venue_name=s.venue_name,
                room_id=s.room_id,
                is_online=s.is_online,
                meeting_link=s.meeting_link,
            )
            for s in drive.schedules
        ],
    )
    val = validate_placement_drive(db, dummy_req, exclude_drive_id=drive.id)
    if not val.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot publish drive: {'; '.join(val.errors)}",
        )

    now = utc_now()
    drive.status = "PUBLISHED"
    drive.published_at = now
    drive.updated_by = publisher.id
    drive.updated_at = now
    drive.version += 1
    db.flush()

    db.add(
        AuditLog(
            user_id=publisher.id,
            action="PLACEMENT_DRIVE_PUBLISHED",
            entity_type="PlacementDrive",
            entity_id=drive.id,
            new_value={"title": drive.title, "status": "PUBLISHED", "version": drive.version},
        )
    )

    _notify_eligible_students_drive_published(db, drive)

    db.commit()
    db.refresh(drive)
    return drive


def postpone_placement_drive(
    db: Session,
    coordinator: User,
    drive_id: int,
    reason: str,
) -> PlacementDrive:
    """Postpones a placement drive and notifies candidates."""
    require_cdc_coordinator(db, coordinator)

    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placement drive #{drive_id} not found.",
        )

    if drive.status in ("CLOSED", "CANCELLED", "ARCHIVED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot postpone drive already in status '{drive.status}'.",
        )

    old_status = drive.status
    drive.status = "POSTPONED"
    drive.postpone_reason = reason.strip()
    drive.updated_by = coordinator.id
    drive.updated_at = utc_now()
    drive.version += 1
    db.flush()

    db.add(
        AuditLog(
            user_id=coordinator.id,
            action="PLACEMENT_DRIVE_POSTPONED",
            entity_type="PlacementDrive",
            entity_id=drive.id,
            old_value={"status": old_status},
            new_value={"status": "POSTPONED", "reason": drive.postpone_reason, "version": drive.version},
        )
    )

    _notify_eligible_students_drive_postponed(db, drive, reason)

    db.commit()
    db.refresh(drive)
    return drive


def cancel_placement_drive(
    db: Session,
    coordinator: User,
    drive_id: int,
    reason: str,
) -> PlacementDrive:
    """Cancels a scheduled or published placement drive."""
    require_cdc_coordinator(db, coordinator)

    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placement drive #{drive_id} not found.",
        )

    if drive.status in ("CANCELLED", "ARCHIVED"):
        return drive  # Idempotent

    old_status = drive.status
    drive.status = "CANCELLED"
    drive.cancellation_reason = reason.strip()
    drive.updated_by = coordinator.id
    drive.updated_at = utc_now()
    drive.version += 1
    db.flush()

    db.add(
        AuditLog(
            user_id=coordinator.id,
            action="PLACEMENT_DRIVE_CANCELLED",
            entity_type="PlacementDrive",
            entity_id=drive.id,
            old_value={"status": old_status},
            new_value={"status": "CANCELLED", "reason": drive.cancellation_reason, "version": drive.version},
        )
    )

    if old_status in ("PUBLISHED", "POSTPONED"):
        _notify_eligible_students_drive_cancelled(db, drive, reason)

    db.commit()
    db.refresh(drive)
    return drive


def close_placement_drive(
    db: Session,
    coordinator: User,
    drive_id: int,
) -> PlacementDrive:
    """Closes applications for a placement drive."""
    require_cdc_coordinator(db, coordinator)

    drive = db.query(PlacementDrive).filter(PlacementDrive.id == drive_id).first()
    if not drive:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placement drive #{drive_id} not found.",
        )

    if drive.status == "CLOSED":
        return drive  # Idempotent

    now = utc_now()
    drive.status = "CLOSED"
    drive.closed_at = now
    drive.updated_by = coordinator.id
    drive.updated_at = now
    drive.version += 1
    db.flush()

    db.add(
        AuditLog(
            user_id=coordinator.id,
            action="PLACEMENT_DRIVE_CLOSED",
            entity_type="PlacementDrive",
            entity_id=drive.id,
            new_value={
                "status": "CLOSED",
                "closed_at": now.isoformat(),
                "version": drive.version,
            },
        )
    )

    db.commit()
    db.refresh(drive)
    return drive


# ---------------------------------------------------------------------------
# 5. Queries & Student Placement Portal Feed
# ---------------------------------------------------------------------------

def list_placement_drives_for_user(
    db: Session,
    current_user: User,
    status_filter: Optional[str] = None,
    job_type: Optional[str] = None,
    tier: Optional[str] = None,
    search_query: Optional[str] = None,
    only_eligible: bool = False,
) -> List[Dict[str, Any]]:
    """
    Returns placement drives tailored to user's role and permission barriers.
    - STUDENT: Strictly published, closed, or postponed drives. Drafts are NEVER returned.
      Evaluates student eligibility and embeds eligibility result.
    - CDC Coordinator / Admin: Returns matching drives including DRAFTs with dashboard metadata.
    """
    now = utc_now()
    query = db.query(PlacementDrive).options(joinedload(PlacementDrive.schedules))

    # 1. Role-based Barrier
    student_obj: Optional[Student] = None
    if current_user.role == "STUDENT":
        # Students NEVER see DRAFT drives
        allowed_statuses = ["PUBLISHED", "CLOSED", "POSTPONED", "CANCELLED"]
        if status_filter and status_filter.upper() in allowed_statuses:
            query = query.filter(PlacementDrive.status == status_filter.upper())
        else:
            query = query.filter(PlacementDrive.status.in_(allowed_statuses))

        student_obj = db.query(Student).filter(Student.user_id == current_user.id).first()
    else:
        # Staff / Admin view
        if status_filter:
            query = query.filter(PlacementDrive.status == status_filter.upper())

    # 2. Filters
    if job_type:
        query = query.filter(PlacementDrive.job_type == job_type.upper())
    if tier:
        query = query.filter(PlacementDrive.tier == tier.upper())
    if search_query:
        sq = f"%{search_query.strip()}%"
        query = query.filter(
            or_(
                PlacementDrive.title.ilike(sq),
                PlacementDrive.company_name.ilike(sq),
                PlacementDrive.job_role.ilike(sq),
            )
        )

    drives = query.order_by(PlacementDrive.application_deadline.asc(), PlacementDrive.id.desc()).all()

    # Pre-fetch department and program name mappings for display
    depts = {d.id: d.name for d in db.query(Department).all()}
    progs = {p.id: p.program_name for p in db.query(Program).all()}

    results: List[Dict[str, Any]] = []
    for d in drives:
        # Check deadline passed
        is_dl_passed = d.application_deadline < now.replace(tzinfo=None)

        dept_names = [depts[did] for did in (d.eligible_department_ids or []) if did in depts]
        prog_names = [progs[pid] for pid in (d.eligible_program_ids or []) if pid in progs]

        # Evaluate student eligibility if student
        elig_res: Optional[StudentEligibilityResult] = None
        if student_obj:
            elig_res = evaluate_student_eligibility(db, d, student_obj)
            if only_eligible and not elig_res.is_eligible:
                continue

        # Format schedules
        sch_items = []
        for s in d.schedules:
            room_num = s.room.room_number if s.room else None
            bldg_name = s.room.building.name if (s.room and s.room.building) else None
            sch_items.append({
                "id": s.id,
                "round_type": s.round_type,
                "round_order": s.round_order,
                "title": s.title,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat(),
                "venue_name": s.venue_name,
                "room_id": s.room_id,
                "room_number": room_num,
                "building_name": bldg_name,
                "is_online": s.is_online,
                "meeting_link": s.meeting_link,
                "instructions": s.instructions,
            })

        results.append({
            "id": d.id,
            "company_name": d.company_name,
            "company_description": d.company_description,
            "company_website": d.company_website,
            "company_logo_url": d.company_logo_url,
            "title": d.title,
            "job_role": d.job_role,
            "job_description": d.job_description,
            "job_type": d.job_type,
            "work_location": d.work_location,
            "compensation_details": d.compensation_details,
            "tier": d.tier,
            "eligible_department_ids": d.eligible_department_ids,
            "eligible_department_names": dept_names,
            "eligible_program_ids": d.eligible_program_ids,
            "eligible_program_names": prog_names,
            "eligible_batch_ids": d.eligible_batch_ids,
            "graduation_year": d.graduation_year,
            "min_cgpa": d.min_cgpa,
            "grading_scale": d.grading_scale,
            "min_percentage": d.min_percentage,
            "max_active_backlogs": d.max_active_backlogs,
            "max_total_backlogs": d.max_total_backlogs,
            "allowed_genders": d.allowed_genders,
            "additional_criteria": d.additional_criteria,
            "application_deadline": d.application_deadline.isoformat(),
            "is_deadline_passed": is_dl_passed,
            "application_link": d.application_link,
            "application_instructions": d.application_instructions,
            "contact_email": d.contact_email,
            "contact_phone": d.contact_phone,
            "required_documents": d.required_documents,
            "status": d.status,
            "postpone_reason": d.postpone_reason,
            "cancellation_reason": d.cancellation_reason,
            "published_at": d.published_at.isoformat() if d.published_at else None,
            "closed_at": d.closed_at.isoformat() if d.closed_at else None,
            "coordinator_id": d.coordinator_id,
            "coordinator_name": d.coordinator.name if d.coordinator else "CDC Coordinator",
            "coordinator_email": d.coordinator.email if d.coordinator else "",
            "version": d.version,
            "created_at": d.created_at.isoformat(),
            "updated_at": d.updated_at.isoformat(),
            "schedules": sch_items,
            "eligibility": elig_res.model_dump() if elig_res else None,
        })

    return results


def get_placement_drive_detail(
    db: Session,
    drive_id: int,
    current_user: User,
) -> Dict[str, Any]:
    """Retrieves full placement drive detail with student-specific eligibility."""
    drives = list_placement_drives_for_user(db=db, current_user=current_user)
    match = next((d for d in drives if d["id"] == drive_id), None)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placement drive #{drive_id} not found or not accessible.",
        )
    return match


def get_cdc_dashboard_stats(db: Session, user: User) -> Dict[str, Any]:
    """Calculates operational metrics for CDC Coordinator dashboard."""
    require_cdc_coordinator(db, user)
    now = utc_now().replace(tzinfo=None)

    total = db.query(PlacementDrive).count()
    published = db.query(PlacementDrive).filter(PlacementDrive.status == "PUBLISHED").count()
    drafts = db.query(PlacementDrive).filter(PlacementDrive.status == "DRAFT").count()
    closed = db.query(PlacementDrive).filter(PlacementDrive.status == "CLOSED").count()
    postponed = db.query(PlacementDrive).filter(PlacementDrive.status == "POSTPONED").count()
    cancelled = db.query(PlacementDrive).filter(PlacementDrive.status == "CANCELLED").count()

    upcoming_dl = (
        db.query(PlacementDrive)
        .filter(
            PlacementDrive.status == "PUBLISHED",
            PlacementDrive.application_deadline >= now,
            PlacementDrive.application_deadline <= now + datetime.timedelta(days=7),
        )
        .count()
    )

    recent = list_placement_drives_for_user(db=db, current_user=user)[:5]

    return {
        "total_drives": total,
        "published_drives": published,
        "draft_drives": drafts,
        "closed_drives": closed,
        "postponed_drives": postponed,
        "cancelled_drives": cancelled,
        "upcoming_deadlines_count": upcoming_dl,
        "recent_drives": recent,
    }


# ---------------------------------------------------------------------------
# 6. Student Academic Record Operations
# ---------------------------------------------------------------------------

def upsert_student_academic_record(
    db: Session,
    updater: User,
    payload: StudentAcademicRecordUpsert,
) -> StudentAcademicRecord:
    """Creates or updates authoritative student academic metrics."""
    require_cdc_coordinator(db, updater)

    student = db.query(Student).filter(Student.id == payload.student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student #{payload.student_id} not found.",
        )

    rec = (
        db.query(StudentAcademicRecord)
        .filter(StudentAcademicRecord.student_id == payload.student_id)
        .first()
    )

    now = utc_now()
    if not rec:
        rec = StudentAcademicRecord(
            student_id=payload.student_id,
            cgpa=payload.cgpa,
            grading_scale=payload.grading_scale,
            percentage=payload.percentage,
            active_backlogs=payload.active_backlogs or 0,
            total_backlogs=payload.total_backlogs or 0,
            graduation_year=payload.graduation_year,
            tenth_percentage=payload.tenth_percentage,
            twelfth_percentage=payload.twelfth_percentage,
            is_verified=payload.is_verified,
            verified_by=updater.id if payload.is_verified else None,
            verified_at=now if payload.is_verified else None,
        )
        db.add(rec)
    else:
        rec.cgpa = payload.cgpa
        rec.grading_scale = payload.grading_scale
        rec.percentage = payload.percentage
        rec.active_backlogs = payload.active_backlogs
        rec.total_backlogs = payload.total_backlogs
        rec.graduation_year = payload.graduation_year
        rec.tenth_percentage = payload.tenth_percentage
        rec.twelfth_percentage = payload.twelfth_percentage
        rec.is_verified = payload.is_verified
        if payload.is_verified:
            rec.verified_by = updater.id
            rec.verified_at = now
        rec.updated_at = now

    db.commit()
    db.refresh(rec)
    return rec


def get_student_academic_record(db: Session, student_id: int) -> Optional[StudentAcademicRecord]:
    return (
        db.query(StudentAcademicRecord)
        .filter(StudentAcademicRecord.student_id == student_id)
        .first()
    )


# ---------------------------------------------------------------------------
# 7. Targeted Notifications
# ---------------------------------------------------------------------------

def _notify_eligible_students_drive_published(db: Session, drive: PlacementDrive) -> None:
    """Dispatches targeted in-app notifications only to eligible student candidates."""
    query = db.query(Student)
    if drive.eligible_department_ids:
        query = query.filter(Student.department_id.in_(drive.eligible_department_ids))
    if drive.eligible_program_ids:
        query = query.filter(Student.program_id.in_(drive.eligible_program_ids))
    if drive.eligible_batch_ids:
        query = query.filter(Student.batch_id.in_(drive.eligible_batch_ids))

    candidates = query.all()
    if not candidates:
        return

    notifs = []
    for s in candidates:
        if s.user_id:
            notifs.append(
                Notification(
                    user_id=s.user_id,
                    title=f"New Placement Drive: {drive.company_name}",
                    message=f"{drive.company_name} has announced a campus placement drive for '{drive.job_role}'. Deadline: {drive.application_deadline.strftime('%b %d, %Y')}.",
                    type="PLACEMENT_PUBLISHED",
                    link="/student/placements",
                    entity_type="PlacementDrive",
                    entity_id=drive.id,
                )
            )

    if notifs:
        create_bulk_notifications(db=db, notifications=notifs)


def _notify_eligible_students_drive_updated(db: Session, drive: PlacementDrive) -> None:
    """Dispatches update notifications to target audience."""
    query = db.query(Student)
    if drive.eligible_department_ids:
        query = query.filter(Student.department_id.in_(drive.eligible_department_ids))

    candidates = query.all()
    notifs = [
        Notification(
            user_id=s.user_id,
            title=f"Placement Drive Updated: {drive.company_name}",
            message=f"Schedule or details for '{drive.title}' have been updated by CDC.",
            type="PLACEMENT_UPDATED",
            link="/student/placements",
            entity_type="PlacementDrive",
            entity_id=drive.id,
        )
        for s in candidates
        if s.user_id
    ]
    if notifs:
        create_bulk_notifications(db=db, notifications=notifs)


def _notify_eligible_students_drive_postponed(db: Session, drive: PlacementDrive, reason: str) -> None:
    query = db.query(Student)
    if drive.eligible_department_ids:
        query = query.filter(Student.department_id.in_(drive.eligible_department_ids))

    candidates = query.all()
    notifs = [
        Notification(
            user_id=s.user_id,
            title=f"Placement Drive Postponed: {drive.company_name}",
            message=f"Drive for '{drive.title}' has been postponed. Reason: {reason}",
            type="PLACEMENT_POSTPONED",
            link="/student/placements",
            entity_type="PlacementDrive",
            entity_id=drive.id,
        )
        for s in candidates
        if s.user_id
    ]
    if notifs:
        create_bulk_notifications(db=db, notifications=notifs)


def _notify_eligible_students_drive_cancelled(db: Session, drive: PlacementDrive, reason: str) -> None:
    query = db.query(Student)
    if drive.eligible_department_ids:
        query = query.filter(Student.department_id.in_(drive.eligible_department_ids))

    candidates = query.all()
    notifs = [
        Notification(
            user_id=s.user_id,
            title=f"Placement Drive Cancelled: {drive.company_name}",
            message=f"Drive for '{drive.title}' was cancelled by CDC. Reason: {reason}",
            type="PLACEMENT_CANCELLED",
            link="/student/placements",
            entity_type="PlacementDrive",
            entity_id=drive.id,
        )
        for s in candidates
        if s.user_id
    ]
    if notifs:
        create_bulk_notifications(db=db, notifications=notifs)
