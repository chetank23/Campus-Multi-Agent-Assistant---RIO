"""
backend/services/timetable_service.py
-------------------------------------
Authoritative domain service for timetable generation, validation, scoring,
and persistence. Shared by both the REST API route (/timetable/generate)
and the conversational Scheduling Agent.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy import text, or_
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from backend.models.identity import User
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Faculty
from backend.models.courses import Course
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry, TimetableChangeHistory
from backend.models.events import CoordinatorCapability
from backend.models.workflow import AuditLog, Notification
from backend.schemas.timetable_generation import (
    GenerationScope,
    GenerationSummary,
    TimetableScore,
)
from backend.schemas.timetable import (
    CanonicalTimetableResponse,
    CoordinatorRecipientItem,
    ScopeCheckResponse,
    TimetableEntryDetailResponse,
    TimetablePreviewEntry,
    TimetablePreviewResponse,
    TimetableVersionResponse,
    PublishTimetableRequest,
    PublishTimetableResponse,
)
from backend.services.timetable_input_loader import validate_and_load_input
from backend.optimizer.timetable_solver import TimetableSolver
from backend.optimizer.validator import validate_timetable, validate_persisted_timetable
from backend.optimizer.scorer import compute_score
from backend.utils.datetime_utils import utc_now


class TimetableGenerationResult(BaseModel):
    success: bool
    status: str
    message: str
    version_id: Optional[int] = None
    solve_time_seconds: Optional[float] = None
    loaded_sections: int = 0
    loaded_courses: int = 0
    loaded_faculty: int = 0
    loaded_rooms: int = 0
    loaded_time_slots: int = 0
    score: Optional[TimetableScore] = None
    diagnostics: List[str] = []
    error: Optional[str] = None


def execute_timetable_generation(
    db: Session,
    scope: GenerationScope,
    current_user: User,
    strategy: str = "BALANCED",
    time_limit: int = 60,
) -> TimetableGenerationResult:
    """
    Executes the authoritative timetable generation pipeline:
    1. Scope validation & input loading
    2. Google OR-Tools CP-SAT solving
    3. Deterministic independent validation
    4. Deterministic scoring
    5. Persistence of draft TimetableVersion and TimetableEntry rows
    6. Audit log writing within the same transaction

    Must be called only by authorized administrators.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to generate timetables.",
        )

    # 1. Load and validate input (Academic IDs, relationships, selected sections, etc.)
    # Input validation must precede duplicate checking so invalid inputs return 400 Bad Request
    optimizer_input = validate_and_load_input(db, scope)

    # 2. Concurrency-safe Duplicate Scope Prevention Check
    # PostgreSQL transaction-level advisory lock prevents simultaneous duplicate generations
    lock_key = f"tt_scope:{scope.academic_year_id}:{scope.department_id}:{scope.semester_id}:{scope.program_id}"
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": lock_key})
    except Exception:
        pass

    active_statuses = ("DRAFT", "GENERATED", "REVIEWED", "VALIDATED", "FINALIZED", "APPROVED", "PUBLISHED")
    scope_check_q = (
        db.query(TimetableVersion)
        .filter(
            TimetableVersion.academic_year_id == scope.academic_year_id,
            TimetableVersion.department_id == scope.department_id,
            TimetableVersion.semester_id == scope.semester_id,
            TimetableVersion.status.in_(active_statuses),
        )
    )
    if scope.program_id:
        scope_check_q = scope_check_q.filter(
            (TimetableVersion.program_id == scope.program_id)
            | (
                (TimetableVersion.program_id.is_(None))
                & (
                    TimetableVersion.timetable_entries.any(
                        (TimetableEntry.program_id == scope.program_id) & (TimetableEntry.status != "CANCELLED")
                    )
                )
            )
        )

    existing_active = scope_check_q.order_by(TimetableVersion.id.desc()).with_for_update().first()
    if existing_active:
        if not getattr(scope, "force_regenerate", False):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A timetable already exists for this academic scope (Version {existing_active.version_number or existing_active.id}, Status: {existing_active.status}). Please review the existing timetable or confirm replacement.",
            )
        else:
            # Controlled replacement: If existing was draft/unapproved, archive it
            if existing_active.status in ("DRAFT", "GENERATED", "REVIEWED", "VALIDATED"):
                existing_active.status = "ARCHIVED"
                db.flush()

    # 3. Run solver with selected strategy profile
    solver = TimetableSolver(opt_input=optimizer_input, time_limit=time_limit, strategy=strategy)
    solver_res = solver.solve()

    score_data: Optional[TimetableScore] = None
    version_id: Optional[int] = None

    if solver_res.feasible:
        # 3. Independent validation
        val_result = validate_timetable(solver_res.entries, optimizer_input)
        hard_violations = [v for v in val_result.violations if v.severity in ("HARD", "BLOCKER")]
        if hard_violations:
            violation_msgs = ", ".join(v.message for v in hard_violations)
            return TimetableGenerationResult(
                success=False,
                status="VALIDATION_FAILED",
                message=f"Solver produced invalid timetable: {violation_msgs}",
                diagnostics=[v.message for v in val_result.violations],
                error=violation_msgs,
                loaded_sections=len(optimizer_input.sections),
                loaded_courses=len(optimizer_input.courses),
                loaded_faculty=len(optimizer_input.faculty),
                loaded_rooms=len(optimizer_input.rooms),
                loaded_time_slots=len(optimizer_input.time_slots),
            )

        # 4. Deterministic scoring
        score_dict = compute_score(val_result, solver_res.entries, optimizer_input)
        score_data = TimetableScore(**score_dict)

        # 5. Persist as GENERATED version with DRAFT entries (never auto-publish)
        try:
            now_utc = utc_now()
            warnings_list = [v for v in val_result.violations if v.severity in ("WARNING", "SOFT")]
            v_status = "PASSED" if not warnings_list else "PASSED_WITH_WARNINGS"
            new_version = TimetableVersion(
                academic_year_id=scope.academic_year_id,
                curriculum_version_id=scope.curriculum_version_id,
                department_id=scope.department_id,
                program_id=scope.program_id,
                semester_id=scope.semester_id,
                working_days=getattr(scope, "working_days", None) or "MON_SAT",
                status="GENERATED",
                revision=1,
                validated_revision=None,
                validation_status="NOT_VALIDATED",
                validation_errors_count=0,
                validation_warnings_count=0,
                validated_at=None,
                score_summary=score_dict,
                last_saved_at=now_utc,
                last_saved_by=current_user.id,
                created_by=current_user.id,
            )
            db.add(new_version)
            db.flush()
            version_id = new_version.id

            assignments = {a.id: a for a in optimizer_input.course_assignments}
            courses_by_id = {c.id: c for c in optimizer_input.courses}
            slots_by_id = {s.id: s for s in optimizer_input.time_slots}

            # Group consecutive practical/lab slots per (course_assignment_id, day) into logical block_group_id
            grouped_entries: Dict[tuple, List[Any]] = defaultdict(list)
            for entry_res in solver_res.entries:
                a = assignments[entry_res.course_assignment_id]
                c = courses_by_id.get(a.course_id)
                sl = slots_by_id.get(entry_res.slot_id)
                is_lab = bool(c and getattr(c, "course_type", "") == "LAB")
                day_key = sl.day.upper() if (sl and sl.day) else "MON"
                grouped_entries[(a.id, day_key, is_lab)].append((sl.start_time if sl else datetime.time(0, 0), entry_res))

            block_group_map: Dict[int, Optional[str]] = {}
            for (ca_id, day_key, is_lab), items in grouped_entries.items():
                if is_lab and len(items) > 1:
                    items.sort(key=lambda x: x[0])
                    grp_id = f"v{version_id}-ca{ca_id}-{day_key}"
                    for _, er in items:
                        block_group_map[id(er)] = grp_id

            for entry_res in solver_res.entries:
                a = assignments[entry_res.course_assignment_id]
                c = courses_by_id.get(a.course_id)
                hour_type = "PRACTICAL" if (c and getattr(c, "course_type", "") == "LAB") else "THEORY"
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
                    course_assignment_id=a.id,
                    hour_type=hour_type,
                    block_group_id=block_group_map.get(id(entry_res)),
                    status="DRAFT",
                )
                db.add(new_entry)

            # 6. Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action="TIMETABLE_GENERATED",
                entity_type="TimetableVersion",
                entity_id=version_id,
                new_value={
                    "status": "GENERATED",
                    "strategy": strategy,
                    "scope": scope.model_dump(),
                    "score": score_dict.get("total_score"),
                },
            )
            db.add(audit)
            db.commit()

        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database persistence failed: {str(exc)}",
            )

        return TimetableGenerationResult(
            success=True,
            status=solver_res.status,
            message="Timetable generated successfully and saved as a private draft. It is not published.",
            version_id=version_id,
            solve_time_seconds=solver_res.solve_time_seconds,
            loaded_sections=len(optimizer_input.sections),
            loaded_courses=len(optimizer_input.courses),
            loaded_faculty=len(optimizer_input.faculty),
            loaded_rooms=len(optimizer_input.rooms),
            loaded_time_slots=len(optimizer_input.time_slots),
            score=score_data,
            diagnostics=getattr(solver_res, "diagnostics", []),
        )

    else:
        # Infeasible or Timed out
        diagnostics = getattr(solver_res, "diagnostics", [])
        return TimetableGenerationResult(
            success=False,
            status=solver_res.status,
            message=solver_res.message,
            solve_time_seconds=solver_res.solve_time_seconds,
            loaded_sections=len(optimizer_input.sections),
            loaded_courses=len(optimizer_input.courses),
            loaded_faculty=len(optimizer_input.faculty),
            loaded_rooms=len(optimizer_input.rooms),
            loaded_time_slots=len(optimizer_input.time_slots),
            diagnostics=diagnostics,
            error=solver_res.message,
        )


def generate_timetable_preview(
    db: Session,
    scope: GenerationScope,
    current_user: User,
    strategy: str = "BALANCED",
    time_limit: int = 60,
) -> TimetablePreviewResponse:
    """
    Generates a temporary timetable preview for Admin without saving any
    persistent draft records to the database.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to generate timetables.",
        )

    ay = db.query(AcademicYear).filter(AcademicYear.id == scope.academic_year_id).first()
    if not ay:
        raise HTTPException(status_code=400, detail="Academic year not found.")
    sem = db.query(Semester).filter(Semester.id == scope.semester_id).first()
    if not sem:
        raise HTTPException(status_code=400, detail="Semester not found.")
    dept = db.query(Department).filter(Department.id == scope.department_id).first()
    if not dept:
        raise HTTPException(status_code=400, detail="Department not found.")

    optimizer_input = validate_and_load_input(db, scope)
    solver = TimetableSolver(opt_input=optimizer_input, time_limit=time_limit, strategy=strategy)
    solver_res = solver.solve()

    sections_db = db.query(Section).filter(Section.id.in_([s.id for s in optimizer_input.sections])).all()
    sections_map = {s.id: s for s in sections_db}
    courses_map = {c.id: c for c in db.query(Course).filter(Course.id.in_([c.id for c in optimizer_input.courses])).all()}
    faculty_map = {f.id: f for f in db.query(Faculty).options(joinedload(Faculty.user)).filter(Faculty.id.in_([f.id for f in optimizer_input.faculty])).all()}
    rooms_map = {r.id: r for r in db.query(Room).options(joinedload(Room.building)).filter(Room.id.in_([r.id for r in optimizer_input.rooms])).all()}
    slots_map = {s.id: s for s in db.query(TimeSlot).filter(TimeSlot.id.in_([s.id for s in optimizer_input.time_slots])).all()}
    assignments_map = {a.id: a for a in optimizer_input.course_assignments}

    sections_info = [
        {
            "id": s.id,
            "section_id": s.id,
            "section_name": s.section_name,
            "student_count": s.student_count or 0,
        }
        for s in sections_db
    ]

    has_existing = (
        db.query(Timetable)
        .filter(
            Timetable.academic_year_id == scope.academic_year_id,
            Timetable.semester_id == scope.semester_id,
            Timetable.section_id.in_(list(sections_map.keys())),
            Timetable.status == "PUBLISHED",
        )
        .first() is not None
    )

    if not solver_res.feasible:
        return TimetablePreviewResponse(
            academic_year_id=scope.academic_year_id,
            semester_id=scope.semester_id,
            department_id=scope.department_id,
            academic_year_name=ay.name or "",
            semester_number=sem.semester_number or 0,
            department_name=dept.name or "",
            status=solver_res.status,
            is_valid=False,
            can_publish=False,
            blocker_count=1,
            warning_count=0,
            violations=[
                {
                    "severity": "BLOCKER",
                    "code": "INFEASIBLE_SCHEDULE",
                    "message": solver_res.message or "Constraints could not be satisfied by solver.",
                    "suggestion": "Adjust room availability, faculty teaching load or expand candidate rooms/slots.",
                }
            ],
            sections=sections_info,
            entries=[],
            solve_time_seconds=solver_res.solve_time_seconds,
            score=None,
            existing_published=has_existing,
            working_days=scope.working_days or "MON_SAT",
        )

    # 3. Independent validation
    val_result = validate_timetable(solver_res.entries, optimizer_input)
    blockers = [v for v in val_result.violations if v.severity in ("HARD", "BLOCKER")]
    warnings = [v for v in val_result.violations if v.severity in ("WARNING", "SOFT")]
    is_valid = len(blockers) == 0
    can_publish = is_valid

    # 4. Scoring
    score_dict = compute_score(val_result, solver_res.entries, optimizer_input)

    # 5. Build Preview Entries
    preview_entries = []
    for entry_res in solver_res.entries:
        a = assignments_map.get(entry_res.course_assignment_id)
        if not a:
            continue
        sec = sections_map.get(a.section_id) if a.section_id is not None else None
        c = courses_map.get(a.course_id)
        f = faculty_map.get(a.faculty_id)
        r = rooms_map.get(entry_res.room_id)
        sl = slots_map.get(entry_res.slot_id)

        sec_name = sec.section_name if (sec and sec.section_name) else f"Section #{a.section_id}"
        c_code = c.course_code if (c and c.course_code) else f"Course #{a.course_id}"
        c_name = c.course_name if (c and c.course_name) else c_code
        c_type = c.course_type if (c and c.course_type) else "CORE"
        f_name = f.user.name if (f and f.user and f.user.name) else (f"Faculty #{a.faculty_id}")
        f_desig = f.designation if f else None
        f_contact = f.contact_number if f else None
        r_num = r.room_number if (r and r.room_number) else f"Room #{entry_res.room_id}"
        b_name = r.building.name if (r and r.building) else None
        day_str = sl.day if (sl and sl.day) else "MON"
        st_str = sl.start_time.strftime("%H:%M") if (sl and sl.start_time) else "08:30"
        et_str = sl.end_time.strftime("%H:%M") if (sl and sl.end_time) else "09:25"
        slot_type = sl.slot_type if (sl and sl.slot_type) else "CLASS"

        preview_entries.append(
            TimetablePreviewEntry(
                section_id=a.section_id or 0,
                section_name=sec_name,
                course_assignment_id=a.id,
                course_id=a.course_id,
                course_code=c_code,
                course_name=c_name,
                course_type=c_type,
                faculty_id=a.faculty_id,
                faculty_name=f_name,
                faculty_designation=f_desig,
                faculty_contact=f_contact,
                room_id=entry_res.room_id,
                room_number=r_num,
                building_name=b_name,
                slot_id=entry_res.slot_id,
                day=day_str,
                start_time=st_str,
                end_time=et_str,
                slot_type=slot_type,
                hour_type=entry_res.hour_type,
            )
        )

    day_rank = {"MON": 1, "MONDAY": 1, "TUE": 2, "TUESDAY": 2, "WED": 3, "WEDNESDAY": 3, "THU": 4, "THURSDAY": 4, "FRI": 5, "FRIDAY": 5, "SAT": 6, "SATURDAY": 6}
    preview_entries.sort(key=lambda x: (x.section_name, day_rank.get(x.day.upper(), 9), x.start_time))

    violations_data = [v.model_dump() for v in val_result.violations]

    return TimetablePreviewResponse(
        academic_year_id=scope.academic_year_id,
        semester_id=scope.semester_id,
        department_id=scope.department_id,
        academic_year_name=ay.name or "",
        semester_number=sem.semester_number or 0,
        department_name=dept.name or "",
        status=solver_res.status,
        is_valid=is_valid,
        can_publish=can_publish,
        blocker_count=len(blockers),
        warning_count=len(warnings),
        violations=violations_data,
        sections=sections_info,
        entries=preview_entries,
        solve_time_seconds=solver_res.solve_time_seconds,
        score=score_dict,
        existing_published=has_existing,
        working_days=scope.working_days or "MON_SAT",
    )


def publish_canonical_timetable(
    db: Session,
    request: PublishTimetableRequest,
    current_user: User,
) -> PublishTimetableResponse:
    """
    Authoritatively publishes a timetable from a persisted, approved TimetableVersion.
    Legacy arbitrary raw entry publication without an approved persisted version
    is strictly rejected with HTTP 409 Conflict.
    Accepts 'version_id' of an approved TimetableVersion for compatibility.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to publish timetables.",
        )

    if not request.version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Legacy direct raw entry publication without an approved persisted version is disabled. "
                "All timetables must be generated as a draft version, validated, and explicitly approved "
                "before publication. Please provide the 'version_id' of an APPROVED TimetableVersion "
                "or use the Generated Timetables workflow (/admin/timetable/versions/{version_id}/publish)."
            ),
        )

    return publish_persisted_version_authoritatively(
        db=db,
        version_id=request.version_id,
        current_user=current_user,
    )


def get_canonical_timetables(
    db: Session,
    academic_year_id: int,
    semester_id: int,
    department_id: int,
) -> List[CanonicalTimetableResponse]:
    """
    Retrieves the published canonical timetables and entries for the given academic scope.
    """
    sections = db.query(Section).filter(
        Section.department_id == department_id,
        Section.semester_id == semester_id,
    ).all()
    if not sections:
        return []
    sec_ids = [s.id for s in sections]

    timetables = (
        db.query(Timetable)
        .options(
            joinedload(Timetable.academic_year),
            joinedload(Timetable.semester),
            joinedload(Timetable.section).joinedload(Section.class_teacher).joinedload(Faculty.user),
            joinedload(Timetable.section).joinedload(Section.program),
            joinedload(Timetable.timetable_entries).joinedload(TimetableEntry.course),
            joinedload(Timetable.timetable_entries).joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
            joinedload(Timetable.timetable_entries).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(Timetable.timetable_entries).joinedload(TimetableEntry.slot),
        )
        .filter(
            Timetable.academic_year_id == academic_year_id,
            Timetable.semester_id == semester_id,
            Timetable.section_id.in_(sec_ids),
            Timetable.status == "PUBLISHED",
        )
        .all()
    )

    day_rank = {"MON": 1, "MONDAY": 1, "TUE": 2, "TUESDAY": 2, "WED": 3, "WEDNESDAY": 3, "THU": 4, "THURSDAY": 4, "FRI": 5, "FRIDAY": 5, "SAT": 6, "SATURDAY": 6}

    result = []
    for tt in timetables:
        sec = tt.section
        ct = sec.class_teacher if sec else None
        ct_name = ct.user.name if (ct and ct.user) else None
        ct_desig = ct.designation if ct else None
        ct_contact = ct.contact_number if ct else None

        sorted_entries = sorted(
            tt.timetable_entries,
            key=lambda e: (day_rank.get(e.slot.day.upper() if (e.slot and e.slot.day) else "MON", 9), e.slot.start_time if (e.slot and e.slot.start_time) else datetime.time(0, 0))
        )

        entries_data = [
            TimetableEntryDetailResponse(
                id=e.id,
                timetable_id=tt.id,
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
                faculty_name=e.faculty.user.name if (e.faculty and e.faculty.user) else None,
                faculty_designation=e.faculty.designation if e.faculty else None,
                faculty_contact=e.faculty.contact_number if e.faculty else None,
                room_number=e.room.room_number if e.room else None,
                building_name=e.room.building.name if (e.room and e.room.building) else None,
                day=e.slot.day if e.slot else None,
                start_time=e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else None,
                end_time=e.slot.end_time.strftime("%H:%M") if (e.slot and e.slot.end_time) else None,
                slot_type=e.slot.slot_type if e.slot else None,
                section_name=sec.section_name if sec else None,
            )
            for e in sorted_entries if e.status == "ACTIVE"
        ]

        dept = sec.department if sec else None

        result.append(
            CanonicalTimetableResponse(
                id=tt.id,
                academic_year_id=tt.academic_year_id,
                semester_id=tt.semester_id,
                section_id=tt.section_id,
                academic_year_name=tt.academic_year.name if tt.academic_year else None,
                semester_number=tt.semester.semester_number if tt.semester else None,
                section_name=sec.section_name if sec else None,
                department_id=dept.id if dept else department_id,
                department_name=dept.name if dept else None,
                program_name=sec.program.program_name if (sec and sec.program) else None,
                status=tt.status,
                working_days=tt.working_days or "MON_SAT",
                created_at=tt.created_at,
                published_at=tt.published_at,
                class_teacher_name=ct_name,
                class_teacher_designation=ct_desig,
                class_teacher_contact=ct_contact,
                entries=entries_data,
            )
        )
    return result


def resolve_coordinators_for_version(
    db: Session,
    version: TimetableVersion,
) -> List[CoordinatorRecipientItem]:
    """
    Authoritatively resolves all coordinators associated with the timetable's academic scope:
    1. CoordinatorCapability records with capability in ('TIMETABLE_COORDINATOR', 'ACADEMIC_COORDINATOR', 'DEPARTMENT_COORDINATOR')
       that are active and either GLOBAL or scoped to the timetable's department.
    2. Section class teachers (Section.class_teacher) for all sections present in the version's entries.
    3. Faculty belonging to the version's department whose designation contains 'Coordinator'.
    """
    # 0. Active entries in this version to resolve sections, department, and program scope
    entries = (
        db.query(TimetableEntry)
        .filter(
            TimetableEntry.version_id == version.id,
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )
    dept_id = version.department_id
    if not dept_id and entries:
        dept_id = next((e.department_id for e in entries if e.department_id is not None), None)
    prog_id = version.program_id
    if not prog_id and entries:
        prog_id = next((e.program_id for e in entries if e.program_id is not None), None)

    # 1. Active capabilities
    cap_conditions = [CoordinatorCapability.scope_type == "GLOBAL"]
    if dept_id:
        cap_conditions.append(
            (CoordinatorCapability.scope_type == "DEPARTMENT")
            & (
                (CoordinatorCapability.scope_id == dept_id)
                | (CoordinatorCapability.scope_id.is_(None))
            )
        )
    if prog_id:
        cap_conditions.append(
            (CoordinatorCapability.scope_type == "PROGRAM")
            & (
                (CoordinatorCapability.scope_id == prog_id)
                | (CoordinatorCapability.scope_id.is_(None))
            )
        )
    cap_q = (
        db.query(CoordinatorCapability)
        .filter(
            CoordinatorCapability.is_active == True,  # noqa: E712
            CoordinatorCapability.capability.in_([
                "TIMETABLE_COORDINATOR",
                "ACADEMIC_COORDINATOR",
                "DEPARTMENT_COORDINATOR",
            ]),
            or_(*cap_conditions),
        )
    )
    capabilities = cap_q.all()

    # 2. Sections in version entries
    section_ids = {e.section_id for e in entries if e.section_id is not None}
    sections = (
        db.query(Section)
        .options(joinedload(Section.class_teacher).joinedload(Faculty.user))
        .filter(Section.id.in_(section_ids))
        .all()
        if section_ids
        else []
    )

    # 3. Department faculty coordinators
    dept_coordinators = []
    if dept_id:
        dept_coordinators = (
            db.query(Faculty)
            .options(joinedload(Faculty.user), joinedload(Faculty.department))
            .filter(
                Faculty.department_id == dept_id,
                Faculty.designation.ilike("%Coordinator%"),
            )
            .all()
        )

    dept_name = None
    if dept_id:
        dept = db.query(Department).filter(Department.id == dept_id).first()
        dept_name = dept.name if dept else None

    coordinators_by_user_id: Dict[int, CoordinatorRecipientItem] = {}

    for cap in capabilities:
        u = db.query(User).filter(User.id == cap.user_id).first()
        if not u:
            continue
        scope_desc = "Global Scope" if cap.scope_type == "GLOBAL" else f"Department: {dept_name or cap.scope_id}"
        role_label = cap.capability.replace("_", " ").title()
        coordinators_by_user_id[u.id] = CoordinatorRecipientItem(
            id=cap.id,
            user_id=u.id,
            name=u.name,
            email=u.email,
            role_or_designation=role_label,
            scope_type="COORDINATOR_CAPABILITY",
            scope_description=scope_desc,
            department_name=dept_name,
        )

    for s in sections:
        ct = s.class_teacher
        if ct and ct.user:
            u = ct.user
            scope_desc = f"Section: {s.section_name}"
            role_label = f"Class Teacher / Section Coordinator ({s.section_name})"
            if u.id in coordinators_by_user_id:
                prev = coordinators_by_user_id[u.id]
                prev.scope_description = f"{prev.scope_description}, {scope_desc}"
            else:
                coordinators_by_user_id[u.id] = CoordinatorRecipientItem(
                    id=ct.id,
                    user_id=u.id,
                    name=u.name,
                    email=u.email,
                    role_or_designation=role_label,
                    scope_type="CLASS_TEACHER",
                    scope_description=scope_desc,
                    department_name=dept_name,
                    section_name=s.section_name,
                )

    for f in dept_coordinators:
        if f.user and f.user.id not in coordinators_by_user_id:
            u = f.user
            coordinators_by_user_id[u.id] = CoordinatorRecipientItem(
                id=f.id,
                user_id=u.id,
                name=u.name,
                email=u.email,
                role_or_designation=f.designation or "Department Coordinator",
                scope_type="DEPARTMENT_COORDINATOR",
                scope_description=f"Department: {dept_name or f.department_id}",
                department_name=dept_name,
            )

    return list(coordinators_by_user_id.values())


def publish_persisted_version_authoritatively(
    db: Session,
    version_id: int,
    current_user: User,
) -> PublishTimetableResponse:
    """
    Authoritatively publishes an APPROVED or FINALIZED TimetableVersion into canonical Timetable records
    inside a single atomic transaction:
    1. Locks the TimetableVersion row and verifies status in ('APPROVED', 'FINALIZED') and revision match.
    2. Verifies at least 1 coordinator is mapped for the academic scope (blocks with 422 if 0).
    3. Re-runs validate_persisted_timetable(db, version_id) to guarantee zero conflicts.
    4. Archives previously PUBLISHED TimetableVersion rows in the same scope without deleting history.
    5. Unlinks old canonical entries (preserving them under their archived version_id) and binds
       the new version's entries to canonical Timetable rows per (academic_year_id, semester_id, section_id).
    6. Dispatches notification to related coordinators.
    7. Transitions version to PUBLISHED and writes AuditLog + TimetableChangeHistory.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to publish timetables.",
        )

    version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.id == version_id)
        .with_for_update()
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Timetable version not found")

    if version.status == "PUBLISHED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Timetable version is already PUBLISHED.",
        )

    if version.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot publish timetable from status '{version.status}'. Version must be APPROVED by an administrator before publishing.",
        )

    if not version.approved_by or not version.approved_at or version.approved_revision is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish timetable: Version is missing formal approval metadata (approved_by, approved_at, approved_revision). Please complete the approval process.",
        )

    if version.approved_revision != version.revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version was modified after approval (approved revision {version.approved_revision} != current revision {version.revision}). Please re-validate and approve before publishing.",
        )

    if version.validated_revision is None or version.validated_revision != version.revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version has unvalidated changes (validated revision {version.validated_revision} != current revision {version.revision}). Please run validation at the current revision before publishing.",
        )

    if version.validation_status not in ("PASSED", "PASSED_WITH_WARNINGS"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot publish timetable: Validation status is '{version.validation_status}'. Timetable must pass validation before publishing.",
        )

    # Preflight coordinator resolution: Must have at least one coordinator mapped
    coordinators = resolve_coordinators_for_version(db, version)
    if not coordinators:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot publish: No eligible coordinators mapped for this academic scope. Please assign at least one coordinator before publishing.",
        )

    val_result = validate_persisted_timetable(db, version_id)
    if not val_result.is_valid:
        msgs = "; ".join(v.message for v in val_result.violations if v.severity in ("HARD", "BLOCKER"))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Publication rejected: {msgs or 'Hard conflicts detected.'}",
        )

    entries = (
        db.query(TimetableEntry)
        .options(
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
            joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableEntry.slot),
        )
        .filter(
            TimetableEntry.version_id == version_id,
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish a timetable version with zero active entries.",
        )

    entries_by_sec: Dict[int, List[TimetableEntry]] = defaultdict(list)
    for e in entries:
        if e.section_id is not None:
            entries_by_sec[e.section_id].append(e)

    now_utc = utc_now()
    published_canonical_tts: List[CanonicalTimetableResponse] = []
    total_entries_count = 0

    try:
        with db.begin_nested():
            # Scope-isolated archival: Archive previous PUBLISHED versions strictly for the same academic scope
            archive_q = db.query(TimetableVersion).filter(
                TimetableVersion.academic_year_id == version.academic_year_id,
                TimetableVersion.id != version.id,
                TimetableVersion.status == "PUBLISHED",
            )
            if version.semester_id is not None:
                archive_q = archive_q.filter(
                    (TimetableVersion.semester_id == version.semester_id)
                    | (TimetableVersion.semester_id.is_(None))
                )
            if version.department_id is not None:
                archive_q = archive_q.filter(
                    (TimetableVersion.department_id == version.department_id)
                    | (TimetableVersion.department_id.is_(None))
                )
            if version.program_id is not None:
                archive_q = archive_q.filter(
                    (TimetableVersion.program_id == version.program_id)
                    | (
                        (TimetableVersion.program_id.is_(None))
                        & (
                            TimetableVersion.timetable_entries.any(
                                (TimetableEntry.program_id == version.program_id)
                                & (TimetableEntry.status != "CANCELLED")
                            )
                        )
                    )
                )
            affected_sec_ids = set(entries_by_sec.keys())
            if affected_sec_ids:
                archive_q = archive_q.filter(
                    TimetableVersion.timetable_entries.any(
                        TimetableEntry.section_id.in_(affected_sec_ids)
                    )
                )
            archive_q.update({"status": "ARCHIVED"}, synchronize_session=False)

            for sec_id, sec_entries in entries_by_sec.items():
                section = (
                    db.query(Section)
                    .options(
                        joinedload(Section.class_teacher).joinedload(Faculty.user),
                        joinedload(Section.program),
                        joinedload(Section.department),
                    )
                    .filter(Section.id == sec_id)
                    .first()
                )
                if not section:
                    raise HTTPException(status_code=400, detail=f"Section {sec_id} not found during publication.")

                sem_id = version.semester_id or sec_entries[0].semester_id or section.semester_id
                canonical_tt = (
                    db.query(Timetable)
                    .filter(
                        Timetable.academic_year_id == version.academic_year_id,
                        Timetable.semester_id == sem_id,
                        Timetable.section_id == sec_id,
                    )
                    .with_for_update()
                    .first()
                )

                if canonical_tt:
                    # Detach prior canonical entries without deleting them so old versions retain history
                    db.query(TimetableEntry).filter(
                        TimetableEntry.timetable_id == canonical_tt.id,
                        TimetableEntry.version_id != version.id,
                    ).update({"timetable_id": None, "status": "CANCELLED"}, synchronize_session=False)

                    canonical_tt.status = "PUBLISHED"
                    canonical_tt.published_at = now_utc
                    canonical_tt.created_by = current_user.id
                    canonical_tt.working_days = version.working_days or "MON_SAT"
                else:
                    canonical_tt = Timetable(
                        academic_year_id=version.academic_year_id,
                        semester_id=sem_id,
                        section_id=sec_id,
                        status="PUBLISHED",
                        working_days=version.working_days or "MON_SAT",
                        published_at=now_utc,
                        created_at=now_utc,
                        created_by=current_user.id,
                    )
                    db.add(canonical_tt)
                    db.flush()

                # Supersede any unlinked legacy ACTIVE entries for this section
                db.query(TimetableEntry).filter(
                    TimetableEntry.section_id == sec_id,
                    TimetableEntry.timetable_id == None,  # noqa: E711
                    TimetableEntry.version_id != version.id,
                    TimetableEntry.status == "ACTIVE",
                ).update({"status": "CANCELLED"}, synchronize_session=False)

                entry_responses: List[TimetableEntryDetailResponse] = []
                for e in sec_entries:
                    e.timetable_id = canonical_tt.id
                    e.status = "ACTIVE"
                    total_entries_count += 1
                    entry_responses.append(
                        TimetableEntryDetailResponse(
                            id=e.id,
                            timetable_id=canonical_tt.id,
                            version_id=version.id,
                            department_id=e.department_id,
                            program_id=e.program_id,
                            semester_id=e.semester_id,
                            section_id=e.section_id,
                            batch_id=e.batch_id,
                            course_id=e.course_id,
                            faculty_id=e.faculty_id,
                            room_id=e.room_id,
                            slot_id=e.slot_id,
                            course_assignment_id=e.course_assignment_id,
                            hour_type=e.hour_type,
                            block_group_id=e.block_group_id,
                            status="ACTIVE",
                            course_code=e.course.course_code if e.course else None,
                            course_name=e.course.course_name if e.course else None,
                            course_type=e.course.course_type if e.course else None,
                            faculty_name=e.faculty.user.name if (e.faculty and e.faculty.user) else None,
                            faculty_designation=e.faculty.designation if e.faculty else None,
                            faculty_contact=e.faculty.contact_number if e.faculty else None,
                            room_number=e.room.room_number if e.room else None,
                            building_name=e.room.building.name if (e.room and e.room.building) else None,
                            day=e.slot.day if e.slot else None,
                            start_time=e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else None,
                            end_time=e.slot.end_time.strftime("%H:%M") if (e.slot and e.slot.end_time) else None,
                            slot_type=e.slot.slot_type if e.slot else None,
                            section_name=section.section_name,
                        )
                    )

                ct = section.class_teacher
                acad_year = db.query(AcademicYear).filter(AcademicYear.id == version.academic_year_id).first()
                sem_obj = db.query(Semester).filter(Semester.id == sem_id).first()
                dept = section.department

                published_canonical_tts.append(
                    CanonicalTimetableResponse(
                        id=canonical_tt.id,
                        academic_year_id=canonical_tt.academic_year_id,
                        semester_id=canonical_tt.semester_id,
                        section_id=canonical_tt.section_id,
                        academic_year_name=acad_year.name if acad_year else None,
                        semester_number=sem_obj.semester_number if sem_obj else None,
                        section_name=section.section_name,
                        department_id=dept.id if dept else (version.department_id or section.department_id),
                        department_name=dept.name if dept else None,
                        program_name=section.program.program_name if section.program else None,
                        status="PUBLISHED",
                        working_days=canonical_tt.working_days or "MON_SAT",
                        created_at=canonical_tt.created_at,
                        published_at=canonical_tt.published_at,
                        class_teacher_name=ct.user.name if (ct and ct.user) else None,
                        class_teacher_designation=ct.designation if ct else None,
                        class_teacher_contact=ct.contact_number if ct else None,
                        entries=entry_responses,
                    )
                )

            version.status = "PUBLISHED"
            version.published_at = now_utc
            version.last_saved_at = now_utc
            version.last_saved_by = current_user.id

            db.add(
                TimetableChangeHistory(
                    version_id=version.id,
                    revision=version.revision,
                    admin_id=current_user.id,
                    validation_outcome="PUBLISHED",
                    reason=f"Published version {version.id} across {len(published_canonical_tts)} section(s)",
                )
            )
            db.add(
                AuditLog(
                    user_id=current_user.id,
                    action="TIMETABLE_PUBLISHED",
                    entity_type="TimetableVersion",
                    entity_id=version.id,
                    new_value={
                        "version_id": version.id,
                        "revision": version.revision,
                        "status": "PUBLISHED",
                        "sections_count": len(published_canonical_tts),
                        "entries_count": total_entries_count,
                    },
                )
            )

            # Notify resolved coordinators
            ver_num = version.version_number or str(version.id)
            d_name = version.department_id and (db.query(Department.name).filter(Department.id == version.department_id).scalar() or "Department")
            for coord in coordinators:
                if coord.user_id:
                    db.add(
                        Notification(
                            user_id=coord.user_id,
                            title=f"Timetable Published: Department Schedule v{ver_num}",
                            message=f"Timetable v{ver_num} has been officially approved and published for {d_name or 'your department'}. Please review the schedule.",
                            type="TIMETABLE_PUBLISHED",
                            link="/faculty/dept-timetable",
                            entity_type="TimetableVersion",
                            entity_id=version.id,
                            is_read=False,
                        )
                    )

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publication failed: {str(exc)}. Previous timetable was preserved.",
        )

    return PublishTimetableResponse(
        success=True,
        message=f"Timetable version {version.id} published across {len(published_canonical_tts)} section(s).",
        published_timetables=published_canonical_tts,
        total_entries_published=total_entries_count,
    )


def recall_persisted_version(
    db: Session,
    version_id: int,
    reason: str,
    current_user: User,
) -> TimetableVersionResponse:
    """
    Recalls an active published TimetableVersion:
    1. Verifies current_user has ADMIN role.
    2. Validates that reason is provided (min 3 chars).
    3. Verifies version is currently in PUBLISHED status.
    4. Atomically in transaction:
       - Sets version.status = 'RECALLED', recalled_by, recalled_at, recall_reason.
       - Marks matching canonical Timetable records as RECALLED.
       - Unlinks TimetableEntry.timetable_id = None for entries in this version.
       - Logs AuditLog and TimetableChangeHistory.
       - Notifies coordinators.
       - Commits.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to recall timetables.",
        )
    if not reason or len(reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid recall reason (minimum 3 characters) is required.",
        )

    version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.id == version_id)
        .with_for_update()
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Timetable version not found")

    if version.status != "PUBLISHED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot recall timetable in status '{version.status}'. Only PUBLISHED timetables can be recalled.",
        )

    now_utc = utc_now()
    version.status = "RECALLED"
    version.recalled_by = current_user.id
    version.recalled_at = now_utc
    version.recall_reason = reason.strip()

    # Find canonical timetables matching this version's scope and entries, and mark RECALLED
    affected_sections = {
        e.section_id
        for e in db.query(TimetableEntry.section_id)
        .filter(
            TimetableEntry.version_id == version.id,
            TimetableEntry.section_id.isnot(None),
            TimetableEntry.status != "CANCELLED",
        )
        .distinct()
        .all()
    }
    linked_tt_ids = {
        e.timetable_id
        for e in db.query(TimetableEntry.timetable_id)
        .filter(
            TimetableEntry.version_id == version.id,
            TimetableEntry.timetable_id.isnot(None),
        )
        .distinct()
        .all()
    }

    canonical_tt_q = db.query(Timetable).filter(
        Timetable.academic_year_id == version.academic_year_id,
        Timetable.status == "PUBLISHED",
    )
    if version.semester_id is not None:
        canonical_tt_q = canonical_tt_q.filter(Timetable.semester_id == version.semester_id)

    if linked_tt_ids or affected_sections:
        c_conditions = []
        if linked_tt_ids:
            c_conditions.append(Timetable.id.in_(linked_tt_ids))
        if affected_sections:
            c_conditions.append(Timetable.section_id.in_(affected_sections))
        canonical_tt_q = canonical_tt_q.filter(or_(*c_conditions))

    canonical_tts = canonical_tt_q.all()
    for c_tt in canonical_tts:
        c_tt.status = "RECALLED"

    # Unlink canonical timetable_id from entries of this version
    db.query(TimetableEntry).filter(
        TimetableEntry.version_id == version.id
    ).update({"timetable_id": None}, synchronize_session=False)

    # Audit & change history
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="TIMETABLE_RECALLED",
            entity_type="TimetableVersion",
            entity_id=version.id,
            old_value={"status": "PUBLISHED"},
            new_value={"status": "RECALLED", "reason": reason.strip(), "recalled_by": current_user.id},
        )
    )
    db.add(
        TimetableChangeHistory(
            version_id=version.id,
            revision=version.revision,
            admin_id=current_user.id,
            validation_outcome="RECALLED",
            reason=f"Recalled: {reason.strip()}",
            created_at=now_utc,
        )
    )

    # Notify coordinators
    coordinators = resolve_coordinators_for_version(db, version)
    ver_num = version.version_number or str(version.id)
    d_name = version.department_id and (db.query(Department.name).filter(Department.id == version.department_id).scalar() or "Department")
    for coord in coordinators:
        if coord.user_id:
            db.add(
                Notification(
                    user_id=coord.user_id,
                    title=f"Timetable Recalled: Department Schedule v{ver_num}",
                    message=f"Timetable v{ver_num} for {d_name} has been recalled by admin. Reason: {reason.strip()}. Active schedule availability has been withdrawn.",
                    type="TIMETABLE_RECALLED",
                    link="/faculty/dept-timetable",
                    entity_type="TimetableVersion",
                    entity_id=version.id,
                    is_read=False,
                )
            )

    db.commit()
    db.refresh(version)

    return build_version_summary_response_item(db, version)


def check_academic_scope_existing(
    db: Session,
    academic_year_id: int,
    semester_id: int,
    department_id: int,
    program_id: Optional[int] = None,
) -> ScopeCheckResponse:
    active_statuses = ("DRAFT", "GENERATED", "REVIEWED", "VALIDATED", "FINALIZED", "APPROVED", "PUBLISHED")
    q = (
        db.query(TimetableVersion)
        .filter(
            TimetableVersion.academic_year_id == academic_year_id,
            TimetableVersion.department_id == department_id,
            TimetableVersion.semester_id == semester_id,
            TimetableVersion.status.in_(active_statuses),
        )
    )
    if program_id:
        q = q.filter(
            (TimetableVersion.program_id == program_id)
            | (
                (TimetableVersion.program_id.is_(None))
                & (
                    TimetableVersion.timetable_entries.any(
                        (TimetableEntry.program_id == program_id) & (TimetableEntry.status != "CANCELLED")
                    )
                )
            )
        )
    existing = q.order_by(TimetableVersion.id.desc()).first()
    if not existing:
        return ScopeCheckResponse(has_existing=False, existing_version=None)

    resp = build_version_summary_response_item(db, existing)
    return ScopeCheckResponse(
        has_existing=True,
        existing_version=resp,
        message=f"A timetable already exists for this academic scope (Version {existing.version_number or existing.id}, Status: {existing.status}).",
    )


def build_version_summary_response_item(
    db: Session,
    v: TimetableVersion,
) -> TimetableVersionResponse:
    ay = v.academic_year or (db.query(AcademicYear).filter(AcademicYear.id == v.academic_year_id).first() if v.academic_year_id else None)
    dept = db.query(Department).filter(Department.id == v.department_id).first() if v.department_id else None
    prog = db.query(Program).filter(Program.id == v.program_id).first() if v.program_id else None
    sem = db.query(Semester).filter(Semester.id == v.semester_id).first() if v.semester_id else None

    creator = v.creator or (db.query(User).filter(User.id == v.created_by).first() if v.created_by else None)
    approver = v.approver or (db.query(User).filter(User.id == v.approved_by).first() if v.approved_by else None)
    recaller = v.recaller or (db.query(User).filter(User.id == v.recalled_by).first() if v.recalled_by else None)

    sec_rows = (
        db.query(Section.section_name)
        .join(TimetableEntry, TimetableEntry.section_id == Section.id)
        .filter(
            TimetableEntry.version_id == v.id,
            TimetableEntry.status != "CANCELLED",
        )
        .distinct()
        .all()
    )
    sec_names = sorted([r[0] for r in sec_rows if r[0]])
    entry_cnt = db.query(TimetableEntry).filter(
        TimetableEntry.version_id == v.id,
        TimetableEntry.status != "CANCELLED",
    ).count()

    pub_status = "PUBLISHED" if (v.status == "PUBLISHED" and v.published_at is not None) else ("RECALLED" if v.status == "RECALLED" else "UNPUBLISHED")

    return TimetableVersionResponse(
        id=v.id,
        academic_year_id=v.academic_year_id,
        version_number=v.version_number,
        status=v.status,
        lifecycle_status=v.status,
        publication_status=pub_status,
        created_by=v.created_by,
        approved_by=v.approved_by,
        approved_at=v.approved_at,
        approved_revision=v.approved_revision,
        recalled_by=v.recalled_by,
        recalled_at=v.recalled_at,
        recall_reason=v.recall_reason,
        recalled_by_name=recaller.name if recaller else None,
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
        department_name=dept.name if dept else None,
        program_name=prog.program_name if prog else None,
        academic_year_name=ay.name if ay else None,
        semester_number=sem.semester_number if sem else None,
        created_by_name=creator.name if creator else None,
        approved_by_name=approver.name if approver else None,
        entry_count=entry_cnt,
        section_names=sec_names,
    )
