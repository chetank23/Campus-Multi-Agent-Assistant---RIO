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
    """
    optimizer_input = validate_and_load_input(db, scope)
    solver = TimetableSolver(opt_input=optimizer_input, time_limit=60)
    result = solver.solve()
    
    score_data = None
    version_id = None

    if result.feasible:
        val_result = validate_timetable(result.entries, optimizer_input)
        if len([v for v in val_result.violations if v.severity == "HARD"]) > 0:
            violations = ", ".join([v.message for v in val_result.violations if v.severity == "HARD"])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Solver produced invalid timetable: {violations}"
            )
        
        score_dict = compute_score(val_result, result.entries, optimizer_input)
        score_data = TimetableScore(**score_dict)

        try:
            new_version = TimetableVersion(
                academic_year_id=scope.academic_year_id,
                status="GENERATED",
                created_by=current_user.id
            )
            db.add(new_version)
            db.flush()
            version_id = new_version.id

            assignments = {a.id: a for a in optimizer_input.course_assignments}
            
            for entry_res in result.entries:
                a = assignments[entry_res.course_assignment_id]
                new_entry = TimetableEntry(
                    version_id=version_id,
                    department_id=scope.department_id,
                    program_id=scope.program_id,
                    semester_id=scope.semester_id,
                    section_id=a.section_id,
                    batch_id=a.batch_id,
                    course_id=a.course_id,
                    faculty_id=a.faculty_id,
                    room_id=entry_res.room_id,
                    slot_id=entry_res.slot_id,
                    status="DRAFT"
                )
                db.add(new_entry)

            audit = AuditLog(
                user_id=current_user.id,
                action="TIMETABLE_GENERATED",
                entity_type="TimetableVersion",
                entity_id=version_id,
                new_value={"status": "GENERATED"}
            )
            db.add(audit)
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Database persistence failed: {str(e)}")
            
    if not result.feasible:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail={
                "message": result.message,
                "diagnostics": getattr(result, 'diagnostics', [])
            }
        )

    return GenerationSummary(
        status=result.status,
        message=result.message,
        loaded_sections=len(optimizer_input.sections),
        loaded_courses=len(optimizer_input.courses),
        loaded_faculty=len(optimizer_input.faculty),
        loaded_rooms=len(optimizer_input.rooms),
        loaded_time_slots=len(optimizer_input.time_slots),
        solve_time_seconds=result.solve_time_seconds,
        generated_entries=result.entries,
        diagnostics=getattr(result, 'diagnostics', []),
        score=score_data,
        version_id=version_id
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

@router.get("/versions/{version_id}", response_model=TimetableVersionDetailResponse)
def get_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version

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
