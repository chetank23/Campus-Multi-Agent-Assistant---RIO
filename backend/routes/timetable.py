import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
    MoveOptionsResponse,
    ArrangementValidateRequest,
    ArrangementValidateResponse,
    ArrangementSaveRequest,
    ArrangementSaveResponse,
    TimetableChangeHistoryItem,
)
from backend.services.timetable_service import (
    generate_timetable_preview,
    publish_canonical_timetable,
    get_canonical_timetables,
    execute_timetable_generation,
    publish_persisted_version_authoritatively,
)
from backend.services.timetable_editor_service import (
    get_move_options,
    validate_proposed_arrangements,
    build_version_detail_response,
    save_arrangements,
    create_revision_from_version,
    get_change_history,
)
from backend.realtime.timetable_sync import broadcast_version_update
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


@router.post("/batch-generate")
def batch_generate_timetable(
    scope: GenerationScope,
    async_mode: bool = Query(False, description="Whether to dispatch via Celery background queue"),
    strategy: str = Query("BALANCED", description="Optimization strategy"),
    time_limit: int = Query(60, description="Solver time limit in seconds"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Department-level multi-section CP-SAT timetable generation.
    Accounts for shared faculty, shared classrooms/labs, sections, and faculty availability.
    Supports both synchronous preview execution and asynchronous Celery/Redis queue dispatch.
    """
    if async_mode:
        from backend.tasks.timetable_tasks import batch_generate_timetable_task
        task = batch_generate_timetable_task.delay(
            scope.model_dump(),
            user_id=current_user.id,
            strategy=strategy,
            time_limit=time_limit,
        )
        return {
            "status": "QUEUED",
            "task_id": task.id,
            "message": "Batch timetable generation task submitted to background queue.",
        }

    return generate_timetable_preview(
        db=db,
        scope=scope,
        current_user=current_user,
        strategy=strategy,
        time_limit=time_limit,
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
    return build_version_detail_response(db, version_id)


@router.get("/versions/{version_id}/move-options", response_model=MoveOptionsResponse)
def get_version_move_options(
    version_id: int,
    entry_id: int = Query(..., description="TimetableEntry ID being dragged"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    return get_move_options(db=db, version_id=version_id, entry_id=entry_id, current_user=current_user)


@router.post("/versions/{version_id}/arrangements/validate", response_model=ArrangementValidateResponse)
def validate_version_arrangements(
    version_id: int,
    req: ArrangementValidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    return validate_proposed_arrangements(db=db, version_id=version_id, req=req, current_user=current_user)


@router.post("/versions/{version_id}/arrangements", response_model=ArrangementSaveResponse)
def save_version_arrangements(
    version_id: int,
    req: ArrangementSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    res = save_arrangements(db=db, version_id=version_id, req=req, current_user=current_user)
    broadcast_version_update(
        version_id=version_id,
        revision=res.revision,
        status_value=res.status,
        actor_name=current_user.name,
        event_type="ARRANGEMENTS_SAVED",
    )
    return res


@router.post("/versions/{version_id}/revise", response_model=TimetableVersionDetailResponse)
def revise_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    return create_revision_from_version(db=db, source_version_id=version_id, current_user=current_user)


@router.get("/versions/{version_id}/history", response_model=List[TimetableChangeHistoryItem])
def version_history(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    return get_change_history(db=db, version_id=version_id, current_user=current_user)


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

    if val_result.is_valid:
        old_status = version.status
        if version.status in ("DRAFT", "GENERATED", "REVIEWED"):
            version.status = "VALIDATED"
        version.validated_revision = version.revision
        db.add(AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VALIDATED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": version.status, "validated_revision": version.revision}
        ))
        db.commit()
        broadcast_version_update(
            version_id=version.id,
            revision=version.revision,
            status_value=version.status or "VALIDATED",
            actor_name=current_user.name,
            event_type="VERSION_VALIDATED",
        )
    else:
        old_status = version.status
        version.validated_revision = None
        if version.status == "VALIDATED":
            version.status = "REVIEWED"
        db.add(AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VALIDATION_FAILED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": version.status, "blocker_count": val_result.blocker_count}
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
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    if version.status in ("PUBLISHED", "FINALIZED", "ARCHIVED"):
        raise HTTPException(status_code=409, detail="Cannot edit an entry in a finalized/published timetable")

    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        return entry

    move_req = ArrangementSaveRequest(
        expected_revision=version.revision,
        moves=[
            {
                "entry_id": entry.id,
                "target_slot_id": update_data.get("slot_id", entry.slot_id),
                "target_room_id": update_data.get("room_id", entry.room_id),
                "target_faculty_id": update_data.get("faculty_id", entry.faculty_id),
            }
        ],
    )
    save_res = save_arrangements(db=db, version_id=version.id, req=move_req, current_user=current_user)
    broadcast_version_update(
        version_id=version.id,
        revision=save_res.revision,
        status_value=save_res.status,
        actor_name=current_user.name,
        event_type="ARRANGEMENTS_SAVED",
    )
    db.refresh(entry)
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

    if version.validated_revision != version.revision:
        raise HTTPException(
            status_code=409,
            detail="Timetable was modified after its last validation. Please revalidate before finalizing.",
        )

    # Authoritative re-validation before finalization
    val_result = validate_persisted_timetable(db, version_id)
    if not val_result.is_valid or val_result.blocker_count > 0:
        version.status = "REVIEWED"
        version.validated_revision = None
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=f"Cannot finalize timetable: {val_result.blocker_count} blocker violation(s) found. Please resolve conflicts before finalizing."
        )

    old_status = version.status
    now_utc = datetime.datetime.now(datetime.UTC)
    version.status = "FINALIZED"
    version.finalized_by = current_user.id
    version.finalized_at = now_utc

    audit = AuditLog(
        user_id=current_user.id,
        action="TIMETABLE_FINALIZED",
        entity_type="TimetableVersion",
        entity_id=version.id,
        old_value={"status": old_status},
        new_value={"status": "FINALIZED", "revision": version.revision}
    )
    db.add(audit)
    db.commit()
    broadcast_version_update(
        version_id=version.id,
        revision=version.revision,
        status_value=version.status or "FINALIZED",
        actor_name=current_user.name,
        event_type="VERSION_FINALIZED",
    )
    return {"message": "Timetable finalized", "version_id": version.id, "status": version.status, "revision": version.revision}


@router.post("/versions/{version_id}/publish")
def publish_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    pub_res = publish_persisted_version_authoritatively(
        db=db,
        version_id=version_id,
        current_user=current_user,
    )

    # Trigger authoritative notifications for affected faculty and students
    dispatch_res = notify_timetable_published(db=db, version_id=version_id)

    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    broadcast_version_update(
        version_id=version_id,
        revision=version.revision if version else 1,
        status_value="PUBLISHED",
        actor_name=current_user.name,
        event_type="VERSION_PUBLISHED",
    )

    return {
        "message": pub_res.message,
        "version_id": version_id,
        "status": "PUBLISHED",
        "total_entries_published": pub_res.total_entries_published,
        "published_timetables": [tt.model_dump() for tt in pub_res.published_timetables],
        "notifications": dispatch_res,
    }
