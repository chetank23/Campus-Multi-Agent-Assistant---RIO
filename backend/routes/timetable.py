import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models.identity import User
from backend.dependencies import get_current_user, require_role
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Faculty
from backend.models.space_time import Room
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry
from backend.models.workflow import AuditLog
from backend.schemas.timetable_generation import (
    GenerationScope,
    GenerationSummary,
    TimetableEntryResult,
    TimetableScore,
)
from backend.schemas.timetable import (
    CanonicalTimetableResponse,
    TimetablePreviewResponse,
    PublishTimetableRequest,
    PublishTimetableResponse,
    TimetableVersionResponse,
    TimetableVersionDetailResponse,
    TimetableEntryResponse,
    TimetableEntryDetailResponse,
    TimetableEntryUpdate,
)
from backend.services.timetable_service import (
    generate_timetable_preview,
    publish_canonical_timetable,
    get_canonical_timetables,
    execute_timetable_generation,
)
from backend.services.timetable_input_loader import validate_and_load_input
from backend.optimizer.validator import (
    validate_timetable,
    validate_persisted_timetable,
    ValidationResult,
    ValidationViolation,
)
from backend.services.notification_service import notify_timetable_published

router = APIRouter(prefix="/timetable", tags=["timetable"])


# ── Canonical Timetable Management Endpoints ──────────────────────────────

@router.get("/academic-years")
def get_timetable_academic_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    years = db.query(AcademicYear).order_by(AcademicYear.name.desc()).all()
    return [{"id": y.id, "name": y.name, "start_date": str(y.start_date) if y.start_date else None, "end_date": str(y.end_date) if y.end_date else None} for y in years]


@router.get("/semesters")
def get_timetable_semesters(
    academic_year_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    query = db.query(Semester)
    if academic_year_id:
        query = query.filter(Semester.academic_year_id == academic_year_id)
    sems = query.order_by(Semester.semester_number.asc()).all()
    return [{"id": s.id, "semester_number": s.semester_number, "academic_year_id": s.academic_year_id} for s in sems]


@router.get("/departments")
def get_timetable_departments(
    academic_year_id: Optional[int] = None,
    semester_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    depts = db.query(Department).order_by(Department.name.asc()).all()
    result = []
    for d in depts:
        sec_query = db.query(Section).filter(Section.department_id == d.id)
        if semester_id:
            sec_query = sec_query.filter(Section.semester_id == semester_id)
        sec_count = sec_query.count()
        result.append({
            "id": d.id,
            "department_code": d.department_code,
            "name": d.name,
            "sections_count": sec_count,
        })
    return result


@router.get("/sections")
def get_timetable_sections(
    academic_year_id: Optional[int] = None,
    semester_id: Optional[int] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    query = db.query(Section)
    if department_id:
        query = query.filter(Section.department_id == department_id)
    if semester_id:
        query = query.filter(Section.semester_id == semester_id)
    if academic_year_id:
        query = query.join(Semester, Section.semester_id == Semester.id).filter(
            Semester.academic_year_id == academic_year_id
        )
    sections = query.order_by(Section.section_name.asc()).all()
    return [
        {
            "id": s.id,
            "section_name": s.section_name,
            "department_id": s.department_id,
            "semester_id": s.semester_id,
            "academic_year_id": academic_year_id or (s.semester.academic_year_id if s.semester else None),
            "student_count": s.student_count or 0,
        }
        for s in sections
    ]


@router.get("/canonical", response_model=List[CanonicalTimetableResponse])
def get_canonical_timetable_endpoint(
    academic_year_id: int,
    semester_id: int,
    department_id: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Retrieves the published canonical timetables and entries for the selected academic scope.
    Exactly ONE canonical timetable exists per Academic Year + Semester + Section.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return get_canonical_timetables(
        db=db,
        academic_year_id=academic_year_id,
        semester_id=semester_id,
        department_id=department_id,
    )


@router.post("/generate-preview", response_model=TimetablePreviewResponse)
def generate_timetable_preview_route(
    scope: GenerationScope,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Generates a temporary timetable preview for Admin with independent validation.
    Does NOT persist any draft records or versions to the database.
    """
    return generate_timetable_preview(
        db=db,
        scope=scope,
        current_user=current_user,
    )


@router.post("/publish", response_model=PublishTimetableResponse)
def publish_canonical_timetable_route(
    request: PublishTimetableRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Authoritatively validates and transactionally saves or replaces the canonical
    timetables for the selected academic scope.
    """
    return publish_canonical_timetable(
        db=db,
        request=request,
        current_user=current_user,
    )


@router.post("/generate", response_model=GenerationSummary)
def generate_timetable(
    scope: GenerationScope,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    """
    Stage 4 Part 2 & Stage 6D: Validates scope, solves, and persists.
    Delegates to shared authoritative service.
    """
    from backend.services.timetable_service import execute_timetable_generation

    gen_res = execute_timetable_generation(
        db=db,
        scope=scope,
        current_user=current_user,
    )

    if not gen_res.success:
        if gen_res.status == "VALIDATION_FAILED":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=gen_res.message,
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": gen_res.message,
                "diagnostics": gen_res.diagnostics,
            },
        )

    return GenerationSummary(
        status=gen_res.status,
        message=gen_res.message,
        loaded_sections=gen_res.loaded_sections,
        loaded_courses=gen_res.loaded_courses,
        loaded_faculty=gen_res.loaded_faculty,
        loaded_rooms=gen_res.loaded_rooms,
        loaded_time_slots=gen_res.loaded_time_slots,
        solve_time_seconds=gen_res.solve_time_seconds,
        diagnostics=gen_res.diagnostics,
        score=gen_res.score,
        version_id=gen_res.version_id,
    )


from typing import List, Optional

@router.get("/versions", response_model=List[TimetableVersionResponse])
def get_versions(
    academic_year_id: Optional[int] = None,
    response: Response = Response(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    if response:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    query = db.query(TimetableVersion)
    if academic_year_id:
        query = query.filter(TimetableVersion.academic_year_id == academic_year_id)
    return query.order_by(TimetableVersion.id.desc()).all()

from sqlalchemy.orm import Session, joinedload
from backend.models.academic import Faculty, Section
from backend.models.space_time import Room
from backend.schemas.timetable import (
    TimetableVersionResponse,
    TimetableVersionDetailResponse,
    TimetableEntryResponse,
    TimetableEntryDetailResponse,
    TimetableEntryUpdate,
)

@router.get("/versions/{version_id}", response_model=TimetableVersionDetailResponse)
def get_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    version = db.query(TimetableVersion).options(
        joinedload(TimetableVersion.academic_year),
        joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.course),
        joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
        joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.room).joinedload(Room.building),
        joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.slot),
        joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.section).joinedload(Section.class_teacher).joinedload(Faculty.user),
        joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.department),
        joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.program),
    ).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    detail_entries = []
    first_entry = version.timetable_entries[0] if version.timetable_entries else None

    dept_name = first_entry.department.name if first_entry and first_entry.department else None
    prog_name = first_entry.program.program_name if first_entry and first_entry.program else None
    ay_name = version.academic_year.name if version.academic_year else None
    sem_num = first_entry.semester_id if first_entry else None
    sec_name = first_entry.section.section_name if first_entry and first_entry.section else None

    ct_name = None
    ct_desig = None
    ct_contact = None
    if first_entry and first_entry.section and first_entry.section.class_teacher:
        ct = first_entry.section.class_teacher
        ct_name = ct.user.name if ct.user else None
        ct_desig = ct.designation
        ct_contact = ct.contact_number

    for e in version.timetable_entries:
        entry_detail = TimetableEntryDetailResponse(
            id=e.id,
            version_id=e.version_id,
            department_id=e.department_id,
            program_id=e.program_id,
            semester_id=e.semester_id,
            section_id=e.section_id,
            batch_id=e.batch_id,
            course_id=e.course_id,
            faculty_id=e.faculty_id,
            room_id=e.room_id,
            slot_id=e.slot_id,
            status=e.status,
            course_code=e.course.course_code if e.course else None,
            course_name=e.course.course_name if e.course else None,
            course_type=e.course.course_type if e.course else None,
            faculty_name=e.faculty.user.name if e.faculty and e.faculty.user else None,
            faculty_designation=e.faculty.designation if e.faculty else None,
            faculty_contact=e.faculty.contact_number if e.faculty else None,
            room_number=e.room.room_number if e.room else None,
            building_name=e.room.building.name if e.room and e.room.building else None,
            day=e.slot.day if e.slot else None,
            start_time=e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else None,
            end_time=e.slot.end_time.strftime("%H:%M") if (e.slot and e.slot.end_time) else None,
            slot_type=e.slot.slot_type if e.slot else None,
            section_name=e.section.section_name if e.section else None,
        )
        detail_entries.append(entry_detail)

    resp = TimetableVersionDetailResponse(
        id=version.id,
        academic_year_id=version.academic_year_id,
        version_number=version.version_number,
        status=version.status,
        created_by=version.created_by,
        approved_by=version.approved_by,
        created_at=version.created_at,
        published_at=version.published_at,
        reason=version.reason,
        department_name=dept_name,
        program_name=prog_name,
        academic_year_name=ay_name,
        semester_number=sem_num,
        section_name=sec_name,
        class_teacher_name=ct_name,
        class_teacher_designation=ct_desig,
        class_teacher_contact=ct_contact,
        timetable_entries=detail_entries
    )
    return resp


@router.post("/versions/{version_id}/validate", response_model=ValidationResult)
def validate_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
        
    val_result = validate_persisted_timetable(db, version_id)
    
    # Update status safely if valid
    if val_result.is_valid and version.status in ("DRAFT", "GENERATED", "REVIEWED"):
        old_status = version.status
        version.status = "VALIDATED"
        db.add(AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VALIDATED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": "VALIDATED"}
        ))
        db.commit()
    elif not val_result.is_valid and version.status == "VALIDATED":
        old_status = version.status
        version.status = "REVIEWED"
        db.add(AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VALIDATION_FAILED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": "REVIEWED", "blocker_count": val_result.blocker_count}
        ))
        db.commit()

    return val_result

@router.patch("/entries/{entry_id}", response_model=TimetableEntryResponse)
def edit_entry(
    entry_id: int,
    updates: TimetableEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    entry = db.query(TimetableEntry).filter(TimetableEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
        
    version = db.query(TimetableVersion).filter(TimetableVersion.id == entry.version_id).first()
    if version and version.status in ("PUBLISHED", "FINALIZED"):
        raise HTTPException(status_code=409, detail="Cannot edit an entry in a finalized/published timetable")

    old_values = {}
    new_values = {}
    
    update_data = updates.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        old_values[k] = getattr(entry, k)
        setattr(entry, k, v)
        new_values[k] = v

    if old_values:
        audit = AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_ENTRY_EDITED",
            entity_type="TimetableEntry",
            entity_id=entry.id,
            old_value=old_values,
            new_value=new_values
        )
        db.add(audit)
        
        # Reset version status if it was validated
        if version and version.status == "VALIDATED":
            version.status = "REVIEWED"
        
    try:
        db.commit()
        db.refresh(entry)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database update failed")
        
    return entry

@router.post("/versions/{version_id}/finalize")
def finalize_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
        
    if version.status != "VALIDATED":
        raise HTTPException(status_code=409, detail=f"Cannot finalize version in status {version.status}. It must be VALIDATED first.")
        
    # Authoritative re-validation before finalization
    val_result = validate_persisted_timetable(db, version_id)
    if not val_result.is_valid or val_result.blocker_count > 0:
        version.status = "REVIEWED"
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=f"Cannot finalize timetable: {val_result.blocker_count} blocker violation(s) found. Please resolve conflicts before finalizing."
        )

    old_status = version.status
    version.status = "FINALIZED"
    
    audit = AuditLog(
        user_id=current_user.id,
        action="TIMETABLE_FINALIZED",
        entity_type="TimetableVersion",
        entity_id=version.id,
        old_value={"status": old_status},
        new_value={"status": "FINALIZED"}
    )
    db.add(audit)
    db.commit()
    return {"message": "Timetable finalized", "version_id": version.id, "status": version.status}

@router.post("/versions/{version_id}/publish")
def publish_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
        
    if version.status == "PUBLISHED":
        raise HTTPException(status_code=409, detail="Version is already PUBLISHED")

    if version.status != "FINALIZED":
        raise HTTPException(status_code=409, detail=f"Version must be FINALIZED before publishing (current: {version.status})")
        
    # Authoritative server-side validation against hard constraints before publication
    val_result = validate_persisted_timetable(db, version_id)
    if not val_result.is_valid or val_result.blocker_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Publication rejected: {val_result.blocker_count} blocker violation(s) found in timetable version #{version_id}."
        )

    old_status = version.status
    now = datetime.datetime.now(datetime.UTC)
    version.status = "PUBLISHED"
    version.published_at = now
    
    audit = AuditLog(
        user_id=current_user.id,
        action="TIMETABLE_PUBLISHED",
        entity_type="TimetableVersion",
        entity_id=version.id,
        old_value={"status": old_status},
        new_value={"status": "PUBLISHED", "published_at": now.isoformat()}
    )
    db.add(audit)
    db.commit()

    # Trigger authoritative notifications for affected faculty and students
    dispatch_res = notify_timetable_published(db=db, version_id=version.id)

    return {
        "message": "Timetable published",
        "version_id": version.id,
        "status": version.status,
        "notifications": dispatch_res,
    }
