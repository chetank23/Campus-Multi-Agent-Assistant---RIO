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
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from backend.models.identity import User
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Faculty
from backend.models.courses import Course
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry
from backend.models.workflow import AuditLog
from backend.schemas.timetable_generation import (
    GenerationScope,
    GenerationSummary,
    TimetableScore,
)
from backend.schemas.timetable import (
    CanonicalTimetableResponse,
    TimetableEntryDetailResponse,
    TimetablePreviewEntry,
    TimetablePreviewResponse,
    PublishTimetableRequest,
    PublishTimetableResponse,
)
from backend.services.timetable_input_loader import validate_and_load_input
from backend.optimizer.timetable_solver import TimetableSolver
from backend.optimizer.validator import validate_timetable
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

    # 1. Load and validate input
    optimizer_input = validate_and_load_input(db, scope)

    # 2. Run solver with selected strategy profile
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

        # 5. Persist as GENERATED version with DRAFT entries
        try:
            new_version = TimetableVersion(
                academic_year_id=scope.academic_year_id,
                curriculum_version_id=scope.curriculum_version_id,
                status="GENERATED",
                created_by=current_user.id,
            )
            db.add(new_version)
            db.flush()
            version_id = new_version.id

            assignments = {a.id: a for a in optimizer_input.course_assignments}
            for entry_res in solver_res.entries:
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
            message=solver_res.message,
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
    Atomically publishes or replaces the canonical timetable for the given scope.
    Exactly ONE canonical timetable is maintained per (Academic Year + Semester + Section).
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to publish timetables.",
        )

    ay = db.query(AcademicYear).filter(AcademicYear.id == request.academic_year_id).first()
    if not ay:
        raise HTTPException(status_code=400, detail="Academic year not found.")
    sem = db.query(Semester).filter(Semester.id == request.semester_id).first()
    if not sem:
        raise HTTPException(status_code=400, detail="Semester not found.")
    dept = db.query(Department).filter(Department.id == request.department_id).first()
    if not dept:
        raise HTTPException(status_code=400, detail="Department not found.")

    if not request.entries:
        raise HTTPException(status_code=400, detail="No timetable entries provided to publish.")

    # 1. Independent validation: check breaks and collision constraints
    slots_db = {s.id: s for s in db.query(TimeSlot).filter(TimeSlot.id.in_([e.slot_id for e in request.entries])).all()}
    for e in request.entries:
        sl = slots_db.get(e.slot_id)
        if sl and getattr(sl, "slot_type", "") in ("BREAK", "LUNCH"):
            raise HTTPException(
                status_code=400,
                detail=f"Publication rejected: Entry {e.course_code} is assigned to non-instructional slot {sl.slot_type} ({sl.day} {sl.start_time})."
            )

    fac_slot = defaultdict(list)
    room_slot = defaultdict(list)
    sec_slot = defaultdict(list)
    for e in request.entries:
        fac_slot[(e.faculty_id, e.slot_id)].append(e)
        room_slot[(e.room_id, e.slot_id)].append(e)
        sec_slot[(e.section_id, e.slot_id)].append(e)

    for (f_id, s_id), clash in fac_slot.items():
        if len(clash) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Publication rejected: Faculty #{f_id} ({clash[0].faculty_name}) has conflict on {clash[0].day} at {clash[0].start_time}."
            )
    for (r_id, s_id), clash in room_slot.items():
        if len(clash) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Publication rejected: Room #{r_id} ({clash[0].room_number}) has collision on {clash[0].day} at {clash[0].start_time}."
            )
    for (sec_id, s_id), clash in sec_slot.items():
        if len(clash) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Publication rejected: Section #{sec_id} ({clash[0].section_name}) has multiple classes scheduled on {clash[0].day} at {clash[0].start_time}."
            )

    now_utc = utc_now()
    published_canonical_tts: List[CanonicalTimetableResponse] = []
    total_entries_count = 0

    entries_by_sec = defaultdict(list)
    for e in request.entries:
        entries_by_sec[e.section_id].append(e)

    # 2. Transactional upsert and replacement
    try:
        with db.begin_nested():
            for sec_id, sec_entries in entries_by_sec.items():
                section = db.query(Section).options(
                    joinedload(Section.class_teacher).joinedload(Faculty.user),
                    joinedload(Section.program),
                ).filter(Section.id == sec_id).first()
                if not section:
                    continue

                canonical_tt = db.query(Timetable).filter(
                    Timetable.academic_year_id == request.academic_year_id,
                    Timetable.semester_id == request.semester_id,
                    Timetable.section_id == sec_id,
                ).first()

                if canonical_tt:
                    # Replace existing timetable entries transactionally
                    db.query(TimetableEntry).filter(TimetableEntry.timetable_id == canonical_tt.id).delete(synchronize_session=False)
                    canonical_tt.status = "PUBLISHED"
                    canonical_tt.published_at = now_utc
                    canonical_tt.created_by = current_user.id
                    canonical_tt.working_days = request.working_days or "MON_SAT"
                else:
                    canonical_tt = Timetable(
                        academic_year_id=request.academic_year_id,
                        semester_id=request.semester_id,
                        section_id=sec_id,
                        status="PUBLISHED",
                        working_days=request.working_days or "MON_SAT",
                        published_at=now_utc,
                        created_at=now_utc,
                        created_by=current_user.id,
                    )
                    db.add(canonical_tt)
                    db.flush()

                # Legacy mirror version for compatibility (version_number max length 10)
                version_code = f"CANON-{sec_id}"[:10]
                legacy_ver = db.query(TimetableVersion).filter(
                    TimetableVersion.academic_year_id == request.academic_year_id,
                    TimetableVersion.version_number == version_code,
                ).first()
                if not legacy_ver:
                    legacy_ver = TimetableVersion(
                        academic_year_id=request.academic_year_id,
                        version_number=version_code,
                        status="PUBLISHED",
                        published_at=now_utc,
                        created_at=now_utc,
                        created_by=current_user.id,
                    )
                    db.add(legacy_ver)
                    db.flush()
                else:
                    legacy_ver.status = "PUBLISHED"
                    legacy_ver.published_at = now_utc
                    db.query(TimetableEntry).filter(TimetableEntry.version_id == legacy_ver.id).delete(synchronize_session=False)

                entry_responses = []
                for e in sec_entries:
                    new_entry = TimetableEntry(
                        timetable_id=canonical_tt.id,
                        version_id=legacy_ver.id,
                        department_id=request.department_id,
                        program_id=section.program_id,
                        semester_id=request.semester_id,
                        section_id=sec_id,
                        course_id=e.course_id,
                        faculty_id=e.faculty_id,
                        room_id=e.room_id,
                        slot_id=e.slot_id,
                        status="ACTIVE",
                    )
                    db.add(new_entry)
                    db.flush()
                    total_entries_count += 1

                    entry_responses.append(
                        TimetableEntryDetailResponse(
                            id=new_entry.id,
                            timetable_id=canonical_tt.id,
                            version_id=legacy_ver.id,
                            department_id=request.department_id,
                            program_id=section.program_id,
                            semester_id=request.semester_id,
                            section_id=sec_id,
                            batch_id=None,
                            course_id=e.course_id,
                            faculty_id=e.faculty_id,
                            room_id=e.room_id,
                            slot_id=e.slot_id,
                            status="ACTIVE",
                            course_code=e.course_code,
                            course_name=e.course_name,
                            course_type=e.course_type,
                            faculty_name=e.faculty_name,
                            faculty_designation=e.faculty_designation,
                            faculty_contact=e.faculty_contact,
                            room_number=e.room_number,
                            building_name=e.building_name,
                            day=e.day,
                            start_time=e.start_time,
                            end_time=e.end_time,
                            slot_type=e.slot_type,
                            section_name=section.section_name,
                        )
                    )

                ct = section.class_teacher
                ct_name = ct.user.name if (ct and ct.user) else None
                ct_desig = ct.designation if ct else None
                ct_contact = ct.contact_number if ct else None

                published_canonical_tts.append(
                    CanonicalTimetableResponse(
                        id=canonical_tt.id,
                        academic_year_id=canonical_tt.academic_year_id,
                        semester_id=canonical_tt.semester_id,
                        section_id=canonical_tt.section_id,
                        academic_year_name=ay.name,
                        semester_number=sem.semester_number,
                        section_name=section.section_name,
                        department_id=dept.id,
                        department_name=dept.name,
                        program_name=section.program.program_name if section.program else None,
                        status="PUBLISHED",
                        working_days=canonical_tt.working_days or "MON_SAT",
                        created_at=canonical_tt.created_at,
                        published_at=canonical_tt.published_at,
                        class_teacher_name=ct_name,
                        class_teacher_designation=ct_desig,
                        class_teacher_contact=ct_contact,
                        entries=entry_responses,
                    )
                )

                db.add(AuditLog(
                    user_id=current_user.id,
                    action="TIMETABLE_PUBLISHED",
                    entity_type="Timetable",
                    entity_id=canonical_tt.id,
                    new_value={
                        "academic_year_id": request.academic_year_id,
                        "semester_id": request.semester_id,
                        "section_id": sec_id,
                        "status": "PUBLISHED",
                        "entries_count": len(sec_entries),
                    }
                ))

        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publication failed: {str(exc)}. Previous timetable was preserved.",
        )

    return PublishTimetableResponse(
        success=True,
        message=f"Timetable published successfully across {len(published_canonical_tts)} section(s).",
        published_timetables=published_canonical_tts,
        total_entries_published=total_entries_count,
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
            for e in sorted_entries if e.status != "CANCELLED"
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
