import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.identity import User
from backend.dependencies import get_current_user, require_role
from backend.schemas.timetable_generation import GenerationScope, GenerationSummary, TimetableEntryResult, TimetableScore
from backend.schemas.timetable import (
    TimetableVersionResponse,
    TimetableVersionDetailResponse,
    TimetableEntryResponse,
    TimetableEntryUpdate,
)
from backend.services.timetable_input_loader import validate_and_load_input
from backend.optimizer.timetable_solver import TimetableSolver
from backend.optimizer.validator import validate_timetable, ValidationResult, ValidationViolation
from backend.optimizer.scorer import compute_score
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.workflow import AuditLog

router = APIRouter(prefix="/timetable", tags=["timetable"])

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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    query = db.query(TimetableVersion)
    if academic_year_id:
        query = query.filter(TimetableVersion.academic_year_id == academic_year_id)
    return query.all()

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
        
    entries = db.query(TimetableEntry).filter(TimetableEntry.version_id == version_id).all()
    if not entries:
        return ValidationResult(is_valid=True, violations=[])
        
    first_entry = entries[0]
    if not (version.academic_year_id and first_entry.department_id and first_entry.program_id and first_entry.semester_id):
        raise HTTPException(status_code=400, detail="Incomplete context in timetable entries")
        
    scope = GenerationScope(
        academic_year_id=version.academic_year_id,
        department_id=first_entry.department_id,
        program_id=first_entry.program_id,
        semester_id=first_entry.semester_id
    )
    
    try:
        opt_input = validate_and_load_input(db, scope)
    except HTTPException as e:
        raise e
        
    assignment_lookup = {
        (a.course_id, a.faculty_id, a.section_id, a.batch_id): a.id
        for a in opt_input.course_assignments
    }
    
    entry_results = []
    for entry in entries:
        if entry.course_id is None or entry.faculty_id is None or entry.room_id is None or entry.slot_id is None:
            return ValidationResult(
                is_valid=False,
                violations=[ValidationViolation(severity="HARD", message=f"Persisted entry {entry.id} is incomplete and cannot be validated")]
            )
            
        a_id = assignment_lookup.get((entry.course_id, entry.faculty_id, entry.section_id, entry.batch_id))
        if not a_id:
            return ValidationResult(
                is_valid=False,
                violations=[ValidationViolation(severity="HARD", message=f"Persisted entry {entry.id} does not match any valid course assignment")]
            )
            
        h_type = "THEORY"
        c = next((c for c in opt_input.courses if c.id == entry.course_id), None)
        if c and c.practical_hours > 0:
            room = next((r for r in opt_input.rooms if r.id == entry.room_id), None)
            if room and room.room_type == 'LAB':
                h_type = "PRACTICAL"
                
        entry_results.append(TimetableEntryResult(
            course_assignment_id=a_id,
            room_id=entry.room_id,
            slot_id=entry.slot_id,
            hour_type=h_type
        ))
        
    val_result = validate_timetable(entry_results, opt_input)
    
    # Update status safely if valid
    if val_result.is_valid and version.status in ("DRAFT", "GENERATED", "REVIEWED"):
        version.status = "VALIDATED"
        db.add(AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VALIDATED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            new_value={"status": "VALIDATED"}
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
        
    if version.status != "FINALIZED":
        raise HTTPException(status_code=409, detail=f"Version must be FINALIZED before publishing (current: {version.status})")
        
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
    return {"message": "Timetable published", "version_id": version.id, "status": version.status}
