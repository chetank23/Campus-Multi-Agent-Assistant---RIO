"""
backend/optimizer/validator.py
------------------------------
Centralized, deterministic timetable validation engine for RIO-MJP.
Evaluates both in-memory optimizer results and authoritative database-persisted
timetable versions against institutional hard constraints and soft advisories.

Validation Severity:
- BLOCKER: Hard constraint violation preventing timetable finalization and publication.
- WARNING: Soft advisory warning (e.g. room capacity deficit, suboptimal preferences).
- INFO: Informational finding (e.g. preferred slot match, calendar alignment).
"""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.academic import Faculty, Section, AcademicYear
from backend.models.space_time import Room, TimeSlot, FacultyAvailability, AcademicCalendar
from backend.models.courses import Course
from backend.schemas.timetable_generation import OptimizerInput, TimetableEntryResult


class ValidationViolation(BaseModel):
    severity: str = "BLOCKER"  # "BLOCKER", "WARNING", "INFO" (also accepts legacy "HARD", "SOFT")
    message: str
    code: Optional[str] = None  # E.g. "FACULTY_OVERLAP", "ROOM_OVERLAP", etc.
    entry_ids: List[int] = Field(default_factory=list)
    entity_type: Optional[str] = None  # "FACULTY", "ROOM", "SECTION", "COURSE"
    entity_id: Optional[int] = None
    entity_name: Optional[str] = None
    suggestion: Optional[str] = None


class ValidationResult(BaseModel):
    is_valid: bool
    violations: List[ValidationViolation] = Field(default_factory=list)
    blocker_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    @classmethod
    def from_violations(cls, violations: List[ValidationViolation], has_entries: bool = True) -> ValidationResult:
        blockers = sum(1 for v in violations if v.severity in ("BLOCKER", "HARD"))
        warnings = sum(1 for v in violations if v.severity in ("WARNING", "SOFT"))
        infos = sum(1 for v in violations if v.severity == "INFO")
        is_valid = (blockers == 0) and has_entries
        return cls(
            is_valid=is_valid,
            violations=violations,
            blocker_count=blockers,
            warning_count=warnings,
            info_count=infos,
        )


def slots_overlap(s1, s2) -> bool:
    """
    Returns True if slot s1 and slot s2 overlap in time on the same day.
    Works for both OptTimeSlot Pydantic objects and TimeSlot SQLAlchemy models.
    """
    if s1 is None or s2 is None:
        return False
    s1_id = getattr(s1, "id", None)
    s2_id = getattr(s2, "id", None)
    if s1_id is not None and s2_id is not None and s1_id == s2_id:
        return True
    day1 = getattr(s1, "day", None)
    day2 = getattr(s2, "day", None)
    if day1 != day2 or not day1:
        return False
    st1 = getattr(s1, "start_time", None)
    et1 = getattr(s1, "end_time", None)
    st2 = getattr(s2, "start_time", None)
    et2 = getattr(s2, "end_time", None)
    if st1 and et1 and st2 and et2:
        return max(st1, st2) < min(et1, et2)
    return False


def validate_timetable(entries: List[TimetableEntryResult], opt_input: OptimizerInput) -> ValidationResult:
    """
    Validates in-memory solver output against optimizer input constraints.
    Preserves exact backward compatibility with solver and scorer pipelines.
    """
    violations: List[ValidationViolation] = []

    courses = {c.id: c for c in opt_input.courses}
    sections = {s.id: s for s in opt_input.sections}
    batches = {b.id: b for b in opt_input.batches}
    rooms = {r.id: r for r in opt_input.rooms}
    labs = {l.room_id: l for l in opt_input.labs}
    faculty = {f.id: f for f in opt_input.faculty}
    slots = {t.id: t for t in opt_input.time_slots}
    assignments = {a.id: a for a in opt_input.course_assignments}

    faculty_availability = defaultdict(dict)
    for fa in opt_input.faculty_availability:
        faculty_availability[fa.faculty_id][fa.slot_id] = fa

    course_hours_assigned = defaultdict(int)

    for entry in entries:
        a = assignments.get(entry.course_assignment_id)
        if not a:
            continue

        slot = slots.get(entry.slot_id)
        slot_label = f"{slot.day} {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}" if slot else f"Slot #{entry.slot_id}"

        # 1. Invalid Slot Type check (e.g. BREAK or LUNCH)
        if slot and getattr(slot, "slot_type", "") in ("BREAK", "LUNCH"):
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="INVALID_SLOT_TYPE",
                    message=f"Assignment #{a.id} is scheduled during {slot.slot_type} slot ({slot_label}). Classes cannot be scheduled during breaks.",
                    suggestion="Move assignment to an active teaching slot.",
                )
            )

        # 2. Capacity requirement (H4 - Hard Constraint)
        student_count = sections[a.section_id].student_count if a.section_id and a.section_id in sections else (batches[a.batch_id].student_count if a.batch_id and a.batch_id in batches else 0)
        room = rooms.get(entry.room_id)
        if room and room.capacity < student_count:
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="CAPACITY_DEFICIT",
                    entity_type="ROOM",
                    entity_id=room.id,
                    message=f"Room #{room.id} capacity ({room.capacity}) is insufficient for {student_count} students.",
                    suggestion=f"Relocate to a larger room with capacity >= {student_count}.",
                )
            )

        # 3. Lab / Practical suitability check
        if entry.hour_type == "PRACTICAL":
            if room and (room.room_type != "LAB" or room.id not in labs):
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="LAB_SUITABILITY",
                        entity_type="ROOM",
                        entity_id=room.id if room else entry.room_id,
                        message=f"Practical hour for assignment #{a.id} scheduled in non-lab room #{entry.room_id}.",
                        suggestion="Relocate this practical session to an active laboratory.",
                    )
                )

        # 4. Faculty Availability adherence
        fa = faculty_availability[a.faculty_id].get(entry.slot_id)
        if fa and fa.availability == "UNAVAILABLE":
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="FACULTY_UNAVAILABLE",
                    entity_type="FACULTY",
                    entity_id=a.faculty_id,
                    message=f"Faculty #{a.faculty_id} is scheduled during an UNAVAILABLE slot {slot_label}.",
                    suggestion="Move assignment to an available time slot.",
                )
            )

        course_hours_assigned[(entry.course_assignment_id, entry.hour_type)] += 1

    # 5. Pairwise Overlap Checks (H1: Faculty, H2: Room, H3: Batch / Section)
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            e1 = entries[i]
            e2 = entries[j]
            a1 = assignments.get(e1.course_assignment_id)
            a2 = assignments.get(e2.course_assignment_id)
            if not a1 or not a2:
                continue

            sl1 = slots.get(e1.slot_id)
            sl2 = slots.get(e2.slot_id)
            if not slots_overlap(sl1, sl2):
                continue

            s_desc = f"{sl1.day} {sl1.start_time.strftime('%H:%M')}-{sl1.end_time.strftime('%H:%M')}" if sl1 else f"Slot #{e1.slot_id}"

            # H1 - Faculty collision
            if a1.faculty_id == a2.faculty_id:
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="FACULTY_OVERLAP",
                        entity_type="FACULTY",
                        entity_id=a1.faculty_id,
                        entity_name=f"Faculty #{a1.faculty_id}",
                        message=f"Faculty #{a1.faculty_id} is double-booked during overlapping time window {s_desc}.",
                        suggestion=f"Reschedule one of the conflicting assignments to a slot where Faculty #{a1.faculty_id} is free.",
                    )
                )

            # H2 - Room collision
            if e1.room_id == e2.room_id:
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="ROOM_OVERLAP",
                        entity_type="ROOM",
                        entity_id=e1.room_id,
                        entity_name=f"Room #{e1.room_id}",
                        message=f"Room #{e1.room_id} is double-booked during overlapping time window {s_desc}.",
                        suggestion="Assign conflicting classes to separate classrooms or laboratories.",
                    )
                )

            # H3 - Batch collision
            if a1.batch_id and a2.batch_id and a1.batch_id == a2.batch_id:
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="BATCH_OVERLAP",
                        entity_type="SECTION",
                        entity_id=a1.batch_id,
                        entity_name=f"Batch #{a1.batch_id}",
                        message=f"Batch #{a1.batch_id} has multiple classes scheduled at overlapping times in {s_desc}.",
                        suggestion="Stagger practical or tutorial batch sessions across different time slots.",
                    )
                )

            # H3 - Section collision (whole-section vs whole-section OR whole-section vs batch in same section)
            if a1.section_id and a2.section_id and a1.section_id == a2.section_id:
                if a1.batch_id is None or a2.batch_id is None or a1.batch_id == a2.batch_id:
                    violations.append(
                        ValidationViolation(
                            severity="BLOCKER",
                            code="SECTION_OVERLAP",
                            entity_type="SECTION",
                            entity_id=a1.section_id,
                            entity_name=f"Section #{a1.section_id}",
                            message=f"Section #{a1.section_id} has overlapping classes scheduled in {s_desc}.",
                            suggestion="Stagger section lectures across different periods to avoid student schedule collision.",
                        )
                    )

    # 6. Required Course Hours
    for a in assignments.values():
        c = courses.get(a.course_id)
        if not c:
            continue
        req_theory = c.lecture_hours + c.tutorial_hours
        req_practical = c.practical_hours

        if req_theory > 0:
            assigned = course_hours_assigned.get((a.id, "THEORY"), 0)
            if assigned != req_theory:
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="INSUFFICIENT_HOURS",
                        entity_type="COURSE",
                        entity_id=c.id,
                        message=f"Assignment #{a.id} missing THEORY hours: required {req_theory}, got {assigned}.",
                        suggestion=f"Ensure all {req_theory} theory hours are scheduled.",
                    )
                )

        if req_practical > 0:
            assigned = course_hours_assigned.get((a.id, "PRACTICAL"), 0)
            if assigned != req_practical:
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="INSUFFICIENT_HOURS",
                        entity_type="COURSE",
                        entity_id=c.id,
                        message=f"Assignment #{a.id} missing PRACTICAL hours: required {req_practical}, got {assigned}.",
                        suggestion=f"Ensure all {req_practical} practical hours are scheduled.",
                    )
                )

    # 7. Elective Groups
    eg_courses = defaultdict(list)
    for egc in opt_input.elective_group_courses:
        eg_courses[egc.group_id].append(egc.course_id)

    for eg_id, course_ids in eg_courses.items():
        eg_schedule = defaultdict(int)
        for entry in entries:
            a = assignments.get(entry.course_assignment_id)
            if a and a.course_id in course_ids:
                if a.section_id is not None:
                    eg_schedule[(a.section_id, entry.slot_id)] += 1
                else:
                    for s_id in sections.keys():
                        eg_schedule[(s_id, entry.slot_id)] += 1

        for (s_id, t_id), count in eg_schedule.items():
            if count > 1:
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="ELECTIVE_CONFLICT",
                        entity_type="SECTION",
                        entity_id=s_id,
                        message=f"Elective group #{eg_id} has {count} overlapping courses in slot #{t_id} for section #{s_id}.",
                        suggestion="Schedule parallel elective options during common parallel slots without double-counting.",
                    )
                )

    # Deduplicate violations
    seen = set()
    deduped: List[ValidationViolation] = []
    for v in violations:
        sig = (v.code, v.entity_id, v.message)
        if sig not in seen:
            seen.add(sig)
            deduped.append(v)

    return ValidationResult.from_violations(deduped, has_entries=len(entries) > 0)


def validate_persisted_timetable(db: Session, version_id: int) -> ValidationResult:
    """
    Authoritative database validator for an existing TimetableVersion.
    Inspects all actual TimetableEntry records and linked relational entities
    (Faculty, User, Room, Slot, Section, Batch, Course) in the active database.

    Enforces:
    1. Non-empty schedule verification.
    2. Complete entry attribute checking.
    3. Invalid slot type check (BREAK / LUNCH flagged as BLOCKER).
    4. Faculty double-booking detection (interval-overlap aware).
    5. Room collision detection (interval-overlap aware).
    6. Batch collision detection (interval-overlap aware).
    7. Section schedule overlap detection (interval-overlap aware).
    8. Room active status check (room.status == 'ACTIVE').
    9. Lab / Practical suitability (practical courses must use LAB rooms).
    10. Room capacity sufficiency check against section/batch size (H4 BLOCKER).
    11. Faculty availability adherence (UNAVAILABLE slots flagged as BLOCKER).
    """
    version = (
        db.query(TimetableVersion)
        .options(
            joinedload(TimetableVersion.academic_year),
            joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.course),
            joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
            joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.slot),
            joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.section),
            joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.batch),
            joinedload(TimetableVersion.timetable_entries).joinedload(TimetableEntry.department),
        )
        .filter(TimetableVersion.id == version_id)
        .first()
    )

    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Timetable version #{version_id} not found.")

    entries: List[TimetableEntry] = version.timetable_entries or []
    violations: List[ValidationViolation] = []

    # 1. Non-empty schedule check
    if not entries:
        violations.append(
            ValidationViolation(
                severity="BLOCKER",
                code="EMPTY_TIMETABLE",
                message=f"Timetable version #{version_id} contains no scheduled class entries.",
                suggestion="Generate schedule entries or populate the timetable before attempting validation.",
            )
        )
        return ValidationResult.from_violations(violations, has_entries=False)

    # Pre-load availability lookup for assigned faculty
    faculty_ids = {e.faculty_id for e in entries if e.faculty_id}
    slot_ids = {e.slot_id for e in entries if e.slot_id}

    fa_lookup = {}
    if faculty_ids and slot_ids:
        fa_records = (
            db.query(FacultyAvailability)
            .filter(FacultyAvailability.faculty_id.in_(faculty_ids), FacultyAvailability.slot_id.in_(slot_ids))
            .all()
        )
        for fa in fa_records:
            fa_lookup[(fa.faculty_id, fa.slot_id)] = fa.availability

    for entry in entries:
        # 2. Incomplete entry check
        if entry.course_id is None or entry.faculty_id is None or entry.room_id is None or entry.slot_id is None:
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="INCOMPLETE_ENTRY",
                    entry_ids=[entry.id],
                    message=f"Timetable Entry #{entry.id} is missing essential scheduling fields (course, faculty, room, or slot).",
                    suggestion="Ensure all required assignment fields are set before finalizing.",
                )
            )
            continue

        slot = entry.slot
        slot_label = f"{slot.day} {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}" if slot and slot.start_time and slot.end_time else f"Slot #{entry.slot_id}"
        room = entry.room
        room_label = f"{room.room_number or f'Room #{room.id}'} ({room.building.name if room.building else 'Campus'})" if room else f"Room #{entry.room_id}"
        course = entry.course
        course_label = f"{course.course_code} - {course.course_name}" if course else f"Course #{entry.course_id}"
        faculty = entry.faculty
        faculty_label = faculty.user.name if (faculty and faculty.user and faculty.user.name) else f"Faculty #{entry.faculty_id}"
        section = entry.section
        section_label = section.section_name if section else f"Section #{entry.section_id}"

        # 3. Invalid Slot Type (e.g. BREAK / LUNCH)
        if slot and getattr(slot, "slot_type", None) in ("BREAK", "LUNCH"):
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="INVALID_SLOT_TYPE",
                    entry_ids=[entry.id],
                    entity_type="SLOT",
                    entity_id=slot.id,
                    message=f"Entry #{entry.id} is scheduled during a {slot.slot_type} slot ({slot_label}). Classes cannot be scheduled during breaks.",
                    suggestion="Move assignment to an active teaching slot.",
                )
            )

        # 4. Room Active Status check
        if room and getattr(room, "status", "ACTIVE") != "ACTIVE":
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="ROOM_INACTIVE",
                    entry_ids=[entry.id],
                    entity_type="ROOM",
                    entity_id=room.id,
                    entity_name=room_label,
                    message=f"Room {room_label} (Entry #{entry.id}) is marked '{room.status}' and cannot be scheduled.",
                    suggestion=f"Reassign Entry #{entry.id} to an active classroom or laboratory.",
                )
            )

        # 5. Lab / Practical suitability check
        is_lab_required = (
            getattr(course, "requires_lab", False) is True
            or (getattr(course, "course_type", "") or "").upper() == "LAB"
        )

        if is_lab_required:
            is_lab_room = (room and getattr(room, "room_type", "") == "LAB") or (room and getattr(room, "lab", None) is not None)
            if not is_lab_room:
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="LAB_SUITABILITY",
                        entry_ids=[entry.id],
                        entity_type="COURSE",
                        entity_id=entry.course_id,
                        entity_name=course_label,
                        message=f"Course '{course_label}' (Entry #{entry.id}) requires a laboratory but is scheduled in non-laboratory room {room_label}.",
                        suggestion="Relocate this practical session to an active laboratory equipped for practical coursework.",
                    )
                )

        # 6. Room Capacity vs Class Size check (H4 - BLOCKER)
        class_size = getattr(entry.batch, "student_count", None) if entry.batch_id and entry.batch else getattr(section, "student_count", None)
        rm_cap = getattr(room, "capacity", None)
        if class_size is not None and rm_cap is not None and class_size > rm_cap:
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="CAPACITY_DEFICIT",
                    entry_ids=[entry.id],
                    entity_type="ROOM",
                    entity_id=room.id if room else None,
                    entity_name=room_label,
                    message=f"Room {room_label} capacity ({rm_cap}) is smaller than required class size ({class_size} students) for Entry #{entry.id}.",
                    suggestion=f"Move Entry #{entry.id} to a room with capacity >= {class_size}.",
                )
            )

        # 7. Faculty Availability adherence
        fa_status = fa_lookup.get((entry.faculty_id, entry.slot_id))
        if fa_status == "UNAVAILABLE":
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="FACULTY_UNAVAILABLE",
                    entry_ids=[entry.id],
                    entity_type="FACULTY",
                    entity_id=entry.faculty_id,
                    entity_name=faculty_label,
                    message=f"Faculty {faculty_label} is scheduled during an UNAVAILABLE slot {slot_label} (Entry #{entry.id}).",
                    suggestion=f"Reschedule Entry #{entry.id} to a slot when {faculty_label} is marked AVAILABLE.",
                )
            )
        elif fa_status == "PREFERRED":
            violations.append(
                ValidationViolation(
                    severity="INFO",
                    code="FACULTY_PREFERENCE",
                    entry_ids=[entry.id],
                    entity_type="FACULTY",
                    entity_id=entry.faculty_id,
                    entity_name=faculty_label,
                    message=f"Faculty {faculty_label} assignment in {slot_label} matches faculty preferred window.",
                )
            )

    # 8. Pairwise Overlap Collisions across all entries (Interval-Overlap Semantics)
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            e1 = entries[i]
            e2 = entries[j]
            if not e1.slot or not e2.slot:
                continue
            if not slots_overlap(e1.slot, e2.slot):
                continue

            s_obj = e1.slot
            slot_label = f"{s_obj.day} {s_obj.start_time.strftime('%H:%M')}-{s_obj.end_time.strftime('%H:%M')}" if (s_obj and s_obj.start_time and s_obj.end_time) else f"Slot #{e1.slot_id}"

            # H1 - Faculty collision
            if e1.faculty_id and e2.faculty_id and e1.faculty_id == e2.faculty_id:
                f_name = e1.faculty.user.name if (e1.faculty and e1.faculty.user and e1.faculty.user.name) else f"Faculty #{e1.faculty_id}"
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="FACULTY_OVERLAP",
                        entry_ids=[e1.id, e2.id],
                        entity_type="FACULTY",
                        entity_id=e1.faculty_id,
                        entity_name=f_name,
                        message=f"Faculty {f_name} is double-booked across conflicting classes at overlapping times in {slot_label} (Entries: #{e1.id}, #{e2.id}).",
                        suggestion=f"Reschedule one of the conflicting entries (#{e1.id}, #{e2.id}) to an alternate slot where {f_name} is free.",
                    )
                )

            # H2 - Room collision
            if e1.room_id and e2.room_id and e1.room_id == e2.room_id:
                r_name = e1.room.room_number if (e1.room and e1.room.room_number) else f"Room #{e1.room_id}"
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="ROOM_OVERLAP",
                        entry_ids=[e1.id, e2.id],
                        entity_type="ROOM",
                        entity_id=e1.room_id,
                        entity_name=r_name,
                        message=f"Room {r_name} is double-booked across conflicting classes at overlapping times in {slot_label} (Entries: #{e1.id}, #{e2.id}).",
                        suggestion=f"Assign conflicting classes (#{e1.id}, #{e2.id}) to separate rooms.",
                    )
                )

            # H3 - Batch collision
            if e1.batch_id and e2.batch_id and e1.batch_id == e2.batch_id:
                b_name = getattr(e1.batch, "batch_name", f"Batch #{e1.batch_id}")
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="BATCH_OVERLAP",
                        entry_ids=[e1.id, e2.id],
                        entity_type="SECTION",
                        entity_id=e1.batch_id,
                        entity_name=b_name,
                        message=f"{b_name} has multiple overlapping classes scheduled in {slot_label} (Entries: #{e1.id}, #{e2.id}).",
                        suggestion="Stagger batch classes to avoid student schedule collision.",
                    )
                )

            # H3 - Section collision (whole-section vs whole-section OR whole-section vs batch)
            if e1.section_id and e2.section_id and e1.section_id == e2.section_id:
                if e1.batch_id is None or e2.batch_id is None or e1.batch_id == e2.batch_id:
                    sec_name = e1.section.section_name if e1.section else f"Section #{e1.section_id}"
                    violations.append(
                        ValidationViolation(
                            severity="BLOCKER",
                            code="SECTION_OVERLAP",
                            entry_ids=[e1.id, e2.id],
                            entity_type="SECTION",
                            entity_id=e1.section_id,
                            entity_name=sec_name,
                            message=f"Section {sec_name} has overlapping classes scheduled in {slot_label} (Entries: #{e1.id}, #{e2.id}).",
                            suggestion="Stagger section lectures across different periods to avoid student schedule collision.",
                        )
                    )

    # 9. Deduplicate violations by (code, entity_id, sorted_entry_ids, message)
    seen = set()
    deduped_violations = []
    for v in violations:
        sorted_eids = tuple(sorted(v.entry_ids))
        sig = (v.code, v.entity_id, sorted_eids, v.message)
        if sig not in seen:
            seen.add(sig)
            deduped_violations.append(v)

    return ValidationResult.from_violations(deduped_violations, has_entries=len(entries) > 0)
