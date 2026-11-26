import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models.identity import User
from backend.dependencies import get_current_user, require_role
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Faculty
from backend.models.space_time import Room
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry, TimetableChangeHistory
from backend.models.workflow import AuditLog
from backend.schemas.timetable_generation import (
    GenerationScope,
    GenerationSummary,
    TimetableEntryResult,
    TimetableScore,
)
from backend.schemas.timetable import (
    CanonicalTimetableResponse,
    CoordinatorRecipientItem,
    PublishPreflightResponse,
    TimetableVersionsSummaryResponse,
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
    RecallTimetableRequest,
    ScopeCheckResponse,
)
from backend.services.timetable_service import (
    generate_timetable_preview,
    publish_canonical_timetable,
    get_canonical_timetables,
    execute_timetable_generation,
    publish_persisted_version_authoritatively,
    resolve_coordinators_for_version,
    recall_persisted_version,
    check_academic_scope_existing,
)
from backend.utils.datetime_utils import utc_now
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


@router.get("/scope/check", response_model=ScopeCheckResponse)
def check_scope_existing_endpoint(
    academic_year_id: int = Query(..., description="Academic year ID"),
    semester_id: int = Query(..., description="Semester ID"),
    department_id: int = Query(..., description="Department ID"),
    program_id: Optional[int] = Query(None, description="Program ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Duplicate prevention preflight check.
    Checks whether an active or draft timetable already exists for this academic scope.
    """
    return check_academic_scope_existing(
        db=db,
        academic_year_id=academic_year_id,
        semester_id=semester_id,
        department_id=department_id,
        program_id=program_id,
    )


@router.get("/versions/summary", response_model=TimetableVersionsSummaryResponse)
def get_versions_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    all_rows = db.query(TimetableVersion.status, TimetableVersion.validation_status).all()
    total = len(all_rows)
    drafts = sum(1 for (st, _) in all_rows if st in ("DRAFT", "GENERATED"))
    awaiting_val = sum(
        1 for (st, val_st) in all_rows
        if st in ("DRAFT", "GENERATED", "REVIEWED") and (val_st in (None, "NOT_VALIDATED", "VALIDATING") or st not in ("VALIDATED", "APPROVED", "PUBLISHED"))
    )
    val_failed = sum(1 for (_, val_st) in all_rows if val_st == "FAILED")
    ready_for_appr = sum(
        1 for (st, val_st) in all_rows
        if (st in ("VALIDATED", "FINALIZED") or (val_st in ("PASSED", "PASSED_WITH_WARNINGS") and st in ("DRAFT", "GENERATED", "REVIEWED", "VALIDATED")))
        and st not in ("APPROVED", "PUBLISHED", "ARCHIVED", "REJECTED", "RECALLED")
    )
    approved = sum(1 for (st, _) in all_rows if st == "APPROVED")
    published = sum(1 for (st, _) in all_rows if st == "PUBLISHED")
    recalled = sum(1 for (st, _) in all_rows if st == "RECALLED")
    archived = sum(1 for (st, _) in all_rows if st in ("ARCHIVED", "REJECTED"))
    awaiting_rev = sum(1 for (st, _) in all_rows if st in ("DRAFT", "GENERATED", "REVIEWED"))

    return TimetableVersionsSummaryResponse(
        total_generated=total,
        drafts=drafts,
        awaiting_validation=awaiting_val,
        validation_failed=val_failed,
        ready_for_approval=ready_for_appr,
        approved=approved,
        published=published,
        recalled=recalled,
        archived=archived,
        awaiting_review=awaiting_rev,
    )


@router.get("/versions", response_model=List[TimetableVersionResponse])
def get_versions(
    academic_year_id: Optional[int] = None,
    department_id: Optional[int] = None,
    program_id: Optional[int] = None,
    semester_id: Optional[int] = None,
    section_id: Optional[int] = None,
    status: Optional[str] = None,
    validation_status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("newest", description="Sorting option: newest, oldest, last_saved, status"),
    response: Response = Response(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    if response:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"

    query = (
        db.query(TimetableVersion)
        .options(
            joinedload(TimetableVersion.academic_year),
            joinedload(TimetableVersion.creator),
            joinedload(TimetableVersion.approver),
            joinedload(TimetableVersion.recaller),
        )
    )
    if academic_year_id:
        query = query.filter(TimetableVersion.academic_year_id == academic_year_id)
    if department_id:
        query = query.filter(TimetableVersion.department_id == department_id)
    if program_id:
        query = query.filter(TimetableVersion.program_id == program_id)
    if semester_id:
        query = query.filter(TimetableVersion.semester_id == semester_id)
    if status:
        query = query.filter(TimetableVersion.status == status.upper())
    if validation_status:
        query = query.filter(TimetableVersion.validation_status == validation_status.upper())
    if section_id:
        sec_ver_ids = (
            db.query(TimetableEntry.version_id)
            .filter(
                TimetableEntry.section_id == section_id,
                TimetableEntry.status != "CANCELLED",
            )
            .distinct()
        )
        query = query.filter(TimetableVersion.id.in_(sec_ver_ids))

    if sort_by == "oldest":
        query = query.order_by(TimetableVersion.created_at.asc(), TimetableVersion.id.asc())
    elif sort_by == "last_saved":
        query = query.order_by(TimetableVersion.last_saved_at.desc().nullslast(), TimetableVersion.id.desc())
    elif sort_by == "status":
        query = query.order_by(TimetableVersion.status.asc(), TimetableVersion.id.desc())
    else:
        query = query.order_by(TimetableVersion.created_at.desc(), TimetableVersion.id.desc())

    versions = query.all()

    depts_map = {d.id: d.name for d in db.query(Department).all()}
    sems_map = {s.id: s.semester_number for s in db.query(Semester).all()}
    progs_map = {p.id: p.program_name for p in db.query(Program).all()}

    ver_ids = [v.id for v in versions]
    entry_info: Dict[int, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "sections": set()})
    if ver_ids:
        rows = (
            db.query(TimetableEntry.version_id, Section.section_name)
            .join(Section, TimetableEntry.section_id == Section.id, isouter=True)
            .filter(
                TimetableEntry.version_id.in_(ver_ids),
                TimetableEntry.status != "CANCELLED",
            )
            .all()
        )
        for vid, sec_name in rows:
            entry_info[vid]["count"] += 1
            if sec_name:
                entry_info[vid]["sections"].add(sec_name)

    results = []
    for v in versions:
        dept_name = depts_map.get(v.department_id) if v.department_id else None
        prog_name = progs_map.get(v.program_id) if v.program_id else None
        sem_num = sems_map.get(v.semester_id) if v.semester_id else None
        ay_name = v.academic_year.name if v.academic_year else None
        sec_names = sorted(list(entry_info[v.id]["sections"]))

        if search:
            q = search.lower().strip()
            text_blob = f"{v.version_number or ''} {dept_name or ''} {prog_name or ''} {ay_name or ''} {' '.join(sec_names)} {v.status or ''} {v.validation_status or ''}".lower()
            if q not in text_blob:
                continue

        results.append(
            TimetableVersionResponse(
                id=v.id,
                academic_year_id=v.academic_year_id,
                version_number=v.version_number,
                status=v.status,
                created_by=v.created_by,
                approved_by=v.approved_by,
                approved_at=v.approved_at,
                approved_revision=v.approved_revision,
                recalled_by=v.recalled_by,
                recalled_at=v.recalled_at,
                recall_reason=v.recall_reason,
                recalled_by_name=v.recaller.name if v.recaller else None,
                validation_status=v.validation_status or "NOT_VALIDATED",
                validation_errors_count=v.validation_errors_count or 0,
                validation_warnings_count=v.validation_warnings_count or 0,
                validated_at=v.validated_at,
                created_at=v.created_at,
                published_at=v.published_at,
                reason=v.reason,
                revision=v.revision or 1,
                validated_revision=v.validated_revision,
                last_saved_at=v.last_saved_at,
                last_saved_by=v.last_saved_by,
                finalized_by=v.finalized_by,
                finalized_at=v.finalized_at,
                working_days=v.working_days or "MON_SAT",
                score_summary=v.score_summary,
                department_id=v.department_id,
                program_id=v.program_id,
                semester_id=v.semester_id,
                department_name=dept_name,
                program_name=prog_name,
                academic_year_name=ay_name,
                semester_number=sem_num,
                created_by_name=v.creator.name if v.creator else None,
                approved_by_name=v.approver.name if v.approver else None,
                entry_count=entry_info[v.id]["count"],
                section_names=sec_names,
            )
        )
    return results

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
    now_utc = utc_now()

    if val_result.is_valid:
        old_status = version.status
        if version.status in ("DRAFT", "GENERATED", "REVIEWED"):
            version.status = "VALIDATED"
        version.validated_revision = version.revision
        version.validation_status = "PASSED_WITH_WARNINGS" if val_result.warning_count > 0 else "PASSED"
        version.validation_errors_count = 0
        version.validation_warnings_count = val_result.warning_count
        version.validated_at = now_utc
        db.add(AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VALIDATED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": version.status, "validated_revision": version.revision, "validation_status": version.validation_status}
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
        version.validation_status = "FAILED"
        version.validation_errors_count = val_result.blocker_count
        version.validation_warnings_count = val_result.warning_count
        version.validated_at = now_utc
        if version.status == "VALIDATED":
            version.status = "REVIEWED"
        db.add(AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VALIDATION_FAILED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": version.status, "blocker_count": val_result.blocker_count, "validation_status": "FAILED"}
        ))
        db.commit()
        broadcast_version_update(
            version_id=version.id,
            revision=version.revision,
            status_value=version.status or "REVIEWED",
            actor_name=current_user.name,
            event_type="VERSION_VALIDATION_FAILED",
        )

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
        expected_revision=version.revision or 1,
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


@router.post("/versions/{version_id}/recall")
def recall_version(
    version_id: int,
    req: RecallTimetableRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Recall an active published timetable:
    - Atomically updates status to RECALLED
    - Revokes canonical publication so students, faculty and coordinators immediately see it as inactive
    - Records recaller, recall_at, recall_reason
    - Logs AuditLog and TimetableChangeHistory
    - Dispatches notifications to affected coordinators with recall reason
    - Broadcasts real-time VERSION_RECALLED event
    """
    if not req.reason or len(req.reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A meaningful recall reason (at least 3 characters) is required to recall a timetable.",
        )
    ver = recall_persisted_version(
        db=db,
        version_id=version_id,
        reason=req.reason.strip(),
        current_user=current_user,
    )
    broadcast_version_update(
        version_id=version_id,
        revision=ver.revision or 1,
        status_value="RECALLED",
        actor_name=current_user.name,
        event_type="VERSION_RECALLED",
    )
    return {
        "message": f"Timetable version #{version_id} has been recalled successfully.",
        "version_id": version_id,
        "status": "RECALLED",
        "recalled_at": ver.recalled_at.isoformat() if ver.recalled_at else None,
        "recall_reason": ver.recall_reason,
    }


@router.post("/versions/{version_id}/approve")
def approve_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Formally approves a timetable version:
    1. Validates that the persisted timetable has zero hard blocker conflicts.
    2. Sets status = 'APPROVED', approved_by, approved_at, approved_revision = revision.
    3. Records AuditLog and TimetableChangeHistory.
    4. Broadcasts real-time VERSION_APPROVED event.
    """
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.status == "PUBLISHED":
        raise HTTPException(status_code=409, detail="Timetable is already PUBLISHED.")

    # Re-validate persisted timetable before approval
    val_result = validate_persisted_timetable(db, version_id)
    if not val_result.is_valid or val_result.blocker_count > 0:
        msgs = "; ".join(v.message for v in val_result.violations if v.severity in ("HARD", "BLOCKER"))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve timetable: {val_result.blocker_count} blocker violation(s) found. {msgs}",
        )

    old_status = version.status
    now_utc = utc_now()
    version.status = "APPROVED"
    version.approved_by = current_user.id
    version.approved_at = now_utc
    version.approved_revision = version.revision
    version.validated_revision = version.revision

    db.add(
        TimetableChangeHistory(
            version_id=version.id,
            revision=version.revision,
            admin_id=current_user.id,
            validation_outcome="APPROVED",
            reason="Admin approved timetable for coordinator publication",
        )
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_APPROVED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": "APPROVED", "revision": version.revision},
        )
    )
    db.commit()

    broadcast_version_update(
        version_id=version.id,
        revision=version.revision,
        status_value="APPROVED",
        actor_name=current_user.name,
        event_type="VERSION_APPROVED",
    )
    return {
        "message": "Timetable approved successfully.",
        "version_id": version.id,
        "status": "APPROVED",
        "revision": version.revision,
        "approved_at": version.approved_at.isoformat() if version.approved_at else None,
    }


@router.get("/versions/{version_id}/coordinators", response_model=PublishPreflightResponse)
def get_version_coordinators(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Preflight coordinator publication inspection:
    Resolves authoritative coordinators for this academic scope, verifies status is APPROVED
    and checks whether publication is allowed.
    """
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    coordinators = resolve_coordinators_for_version(db, version)

    blocking_reasons: List[str] = []
    if version.status not in ("APPROVED", "FINALIZED"):
        blocking_reasons.append(f"Timetable status is '{version.status}'. It must be APPROVED before publishing.")
    if version.approved_revision is not None and version.approved_revision != version.revision:
        blocking_reasons.append("Timetable was modified after approval. Please re-validate and approve before publishing.")
    if not coordinators:
        blocking_reasons.append("Cannot publish: No eligible coordinators mapped for this academic scope. Please assign at least one coordinator before publishing.")

    dept = db.query(Department).filter(Department.id == version.department_id).first() if version.department_id else None
    ay = db.query(AcademicYear).filter(AcademicYear.id == version.academic_year_id).first() if version.academic_year_id else None
    sem = db.query(Semester).filter(Semester.id == version.semester_id).first() if version.semester_id else None

    sec_names = sorted(list({
        e.section.section_name
        for e in db.query(TimetableEntry).options(joinedload(TimetableEntry.section)).filter(
            TimetableEntry.version_id == version.id,
            TimetableEntry.status != "CANCELLED",
        ).all()
        if e.section and e.section.section_name
    }))

    can_pub = len(blocking_reasons) == 0

    return PublishPreflightResponse(
        version_id=version.id,
        academic_year_id=version.academic_year_id,
        academic_year_name=ay.name if ay else None,
        department_id=version.department_id,
        department_name=dept.name if dept else None,
        semester_id=version.semester_id,
        semester_number=sem.semester_number if sem else None,
        section_names=sec_names,
        status=version.status or "DRAFT",
        revision=version.revision or 1,
        approved_revision=version.approved_revision,
        can_publish=can_pub,
        coordinators=coordinators,
        coordinator_count=len(coordinators),
        blocking_reasons=blocking_reasons,
    )


@router.post("/versions/{version_id}/archive")
def archive_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    old_status = version.status
    version.status = "ARCHIVED"
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_ARCHIVED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": old_status},
            new_value={"status": "ARCHIVED"},
        )
    )
    db.commit()
    return {"message": f"Timetable version #{version.id} archived successfully."}


@router.delete("/versions/{version_id}")
def delete_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.status == "PUBLISHED":
        raise HTTPException(status_code=409, detail="Cannot delete a PUBLISHED timetable version.")

    db.query(TimetableChangeHistory).filter(TimetableChangeHistory.version_id == version.id).delete(synchronize_session=False)
    db.query(TimetableEntry).filter(TimetableEntry.version_id == version.id).delete(synchronize_session=False)
    db.delete(version)
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_VERSION_DELETED",
            entity_type="TimetableVersion",
            entity_id=version_id,
            old_value={"id": version_id},
            new_value=None,
        )
    )
    db.commit()
    return {"message": f"Timetable version #{version_id} deleted successfully."}
