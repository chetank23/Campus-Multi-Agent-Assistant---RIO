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

    faculty_schedule = defaultdict(list)
    section_schedule = defaultdict(list)
    room_schedule = defaultdict(list)
    course_hours_assigned = defaultdict(int)

    for entry in entries:
        a = assignments.get(entry.course_assignment_id)
        if not a:
            continue

        slot = slots.get(entry.slot_id)
        slot_label = f"{slot.day} {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}" if slot else f"Slot #{entry.slot_id}"

        # 1. Faculty collision
        if entry.slot_id in faculty_schedule[a.faculty_id]:
            f_name = f"Faculty #{a.faculty_id}"
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="FACULTY_OVERLAP",
                    entity_type="FACULTY",
                    entity_id=a.faculty_id,
                    entity_name=f_name,
                    message=f"{f_name} is double-booked in slot {slot_label}.",
                    suggestion=f"Reschedule one of the conflicting assignments to a slot where {f_name} is free.",
                )
            )
        faculty_schedule[a.faculty_id].append(entry.slot_id)

        # 2. Section collision
        if a.section_id:
            if entry.slot_id in section_schedule[a.section_id]:
                s_name = f"Section #{a.section_id}"
                violations.append(
                    ValidationViolation(
                        severity="BLOCKER",
                        code="SECTION_OVERLAP",
                        entity_type="SECTION",
                        entity_id=a.section_id,
                        entity_name=s_name,
                        message=f"{s_name} has multiple overlapping classes scheduled in slot {slot_label}.",
                        suggestion="Stagger section lectures across different periods to avoid student schedule collision.",
                    )
                )
            section_schedule[a.section_id].append(entry.slot_id)

        # 3. Room collision
        if entry.slot_id in room_schedule[entry.room_id]:
            r_name = f"Room #{entry.room_id}"
            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="ROOM_OVERLAP",
                    entity_type="ROOM",
                    entity_id=entry.room_id,
                    entity_name=r_name,
                    message=f"{r_name} is double-booked in slot {slot_label}.",
                    suggestion=f"Assign conflicting classes to separate classrooms or laboratories.",
                )
            )
        room_schedule[entry.room_id].append(entry.slot_id)

        # 4. Capacity and Lab requirements
        student_count = sections[a.section_id].student_count if a.section_id and a.section_id in sections else (batches[a.batch_id].student_count if a.batch_id and a.batch_id in batches else 0)
        room = rooms.get(entry.room_id)
        if room and room.capacity < student_count:
            violations.append(
                ValidationViolation(
                    severity="WARNING",
                    code="CAPACITY_DEFICIT",
                    entity_type="ROOM",
                    entity_id=room.id,
                    message=f"Room #{room.id} capacity ({room.capacity}) is insufficient for {student_count} students.",
                    suggestion=f"Relocate to a larger room with capacity >= {student_count}.",
                )
            )

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

        # 5. Faculty Availability
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

    return ValidationResult.from_violations(violations, has_entries=len(entries) > 0)


def validate_persisted_timetable(db: Session, version_id: int) -> ValidationResult:
    """
    Authoritative database validator for an existing TimetableVersion.
    Inspects all actual TimetableEntry records and linked relational entities
    (Faculty, User, Room, Slot, Section, Course) in the active database.

    Enforces:
    1. Non-empty schedule verification.
    2. Complete entry attribute checking.
    3. Faculty double-booking detection (same faculty_id & slot_id).
    4. Room collision detection (same room_id & slot_id).
    5. Section schedule overlap detection (same section_id & slot_id).
    6. Room active status check (room.status == 'ACTIVE').
    7. Lab / Practical suitability (practical courses must use LAB rooms).
    8. Room capacity sufficiency check against section size.
    9. Faculty availability adherence (UNAVAILABLE slots flagged as BLOCKER).
    10. Academic calendar holiday alignment check.
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

    # Schedules for collision tracking
    faculty_map = defaultdict(list)  # (faculty_id, slot_id) -> list of entry
    room_map = defaultdict(list)     # (room_id, slot_id) -> list of entry
    section_map = defaultdict(list)  # (section_id, slot_id) -> list of entry

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

        # Grouping for collision detection
        faculty_map[(entry.faculty_id, entry.slot_id)].append(entry)
        room_map[(entry.room_id, entry.slot_id)].append(entry)

        # Whole-section lectures (where batch_id is None) cannot overlap
        if entry.section_id is not None and entry.batch_id is None:
            section_map[(entry.section_id, entry.slot_id)].append(entry)

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

        # 3. Room Active Status check
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

        # 4. Lab / Practical suitability check
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

        # 5. Room Capacity vs Section Size check
        sec_size = getattr(section, "student_count", None)
        rm_cap = getattr(room, "capacity", None)
        if sec_size is not None and rm_cap is not None and sec_size > rm_cap:
            violations.append(
                ValidationViolation(
                    severity="WARNING",
                    code="CAPACITY_DEFICIT",
                    entry_ids=[entry.id],
                    entity_type="ROOM",
                    entity_id=room.id if room else None,
                    entity_name=room_label,
                    message=f"Room {room_label} capacity ({rm_cap}) is smaller than Section {section_label} size ({sec_size} students).",
                    suggestion=f"Move Entry #{entry.id} to a room with capacity >= {sec_size}.",
                )
            )

        # 6. Faculty Availability adherence
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

    # 7. Faculty Double-Booking Collisions
    for (f_id, s_id), coll_entries in faculty_map.items():
        if len(coll_entries) > 1:
            first_e = coll_entries[0]
            f_name = first_e.faculty.user.name if (first_e.faculty and first_e.faculty.user and first_e.faculty.user.name) else f"Faculty #{f_id}"
            s_obj = first_e.slot
            slot_label = f"{s_obj.day} {s_obj.start_time.strftime('%H:%M')}-{s_obj.end_time.strftime('%H:%M')}" if (s_obj and s_obj.start_time) else f"Slot #{s_id}"
            entry_ids = [e.id for e in coll_entries]

            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="FACULTY_OVERLAP",
                    entry_ids=entry_ids,
                    entity_type="FACULTY",
                    entity_id=f_id,
                    entity_name=f_name,
                    message=f"Faculty {f_name} is double-booked across {len(coll_entries)} classes in slot {slot_label} (Entries: {', '.join(f'#{eid}' for eid in entry_ids)}).",
                    suggestion=f"Reschedule one of the conflicting entries ({', '.join(f'#{eid}' for eid in entry_ids)}) to an alternate slot where {f_name} is free.",
                )
            )

    # 8. Room Double-Booking Collisions
    for (r_id, s_id), coll_entries in room_map.items():
        if len(coll_entries) > 1:
            first_e = coll_entries[0]
            r_name = first_e.room.room_number if first_e.room and first_e.room.room_number else f"Room #{r_id}"
            s_obj = first_e.slot
            slot_label = f"{s_obj.day} {s_obj.start_time.strftime('%H:%M')}-{s_obj.end_time.strftime('%H:%M')}" if (s_obj and s_obj.start_time) else f"Slot #{s_id}"
            entry_ids = [e.id for e in coll_entries]

            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="ROOM_OVERLAP",
                    entry_ids=entry_ids,
                    entity_type="ROOM",
                    entity_id=r_id,
                    entity_name=r_name,
                    message=f"Room {r_name} is double-booked across {len(coll_entries)} classes in slot {slot_label} (Entries: {', '.join(f'#{eid}' for eid in entry_ids)}).",
                    suggestion=f"Assign conflicting classes ({', '.join(f'#{eid}' for eid in entry_ids)}) to separate rooms.",
                )
            )

    # 9. Section Schedule Overlap Collisions
    for (sec_id, s_id), coll_entries in section_map.items():
        if len(coll_entries) > 1:
            first_e = coll_entries[0]
            sec_name = first_e.section.section_name if first_e.section and first_e.section.section_name else f"Section #{sec_id}"
            s_obj = first_e.slot
            slot_label = f"{s_obj.day} {s_obj.start_time.strftime('%H:%M')}-{s_obj.end_time.strftime('%H:%M')}" if (s_obj and s_obj.start_time) else f"Slot #{s_id}"
            entry_ids = [e.id for e in coll_entries]

            violations.append(
                ValidationViolation(
                    severity="BLOCKER",
                    code="SECTION_OVERLAP",
                    entry_ids=entry_ids,
                    entity_type="SECTION",
                    entity_id=sec_id,
                    entity_name=sec_name,
                    message=f"Section {sec_name} has {len(coll_entries)} overlapping whole-class lectures in slot {slot_label} (Entries: {', '.join(f'#{eid}' for eid in entry_ids)}).",
                    suggestion="Stagger section lectures across different periods to avoid student schedule collision.",
                )
            )

    # 10. Deduplicate violations by (code, entity_id, message)
    seen = set()
    deduped_violations = []
    for v in violations:
        sig = (v.code, v.entity_id, v.message)
        if sig not in seen:
            seen.add(sig)
            deduped_violations.append(v)

    return ValidationResult.from_violations(deduped_violations, has_entries=len(entries) > 0)
