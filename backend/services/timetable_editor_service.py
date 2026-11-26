"""
backend/services/timetable_editor_service.py
--------------------------------------------
Authoritative backend service for Smart Timetable Review & Drag-and-Drop Arrangement:
- Real PostgreSQL availability checks across sections, faculty, rooms, and time slots
- Multi-period practical/lab block preservation
- Move options discovery (GET /timetable/versions/{id}/move-options)
- Dry-run batch validation (POST /timetable/versions/{id}/arrangements/validate)
- Atomic, row-locked, revision-checked arrangement save (POST /timetable/versions/{id}/arrangements)
- Revision creation from published versions & immutable change history
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from backend.models.academic import AcademicYear, Batch, Department, Faculty, Program, Section, Semester
from backend.models.courses import Course
from backend.models.identity import User
from backend.models.space_time import FacultyAvailability, Room, TimeSlot
from backend.models.timetable import Timetable, TimetableChangeHistory, TimetableEntry, TimetableVersion
from backend.models.workflow import AuditLog
from backend.optimizer.validator import DAY_NORM_MAP, slots_overlap
from backend.schemas.timetable import (
    AlternativeRoomOption,
    ArrangementSaveRequest,
    ArrangementSaveResponse,
    ArrangementValidateRequest,
    ArrangementValidateResponse,
    MoveOptionSlot,
    MoveOptionsResponse,
    MoveOutcomeItem,
    ProposedMoveItem,
    TimetableChangeHistoryItem,
    TimetableEntryDetailResponse,
    TimetableVersionDetailResponse,
)
from backend.utils.datetime_utils import utc_now

EDITABLE_STATUSES = {"DRAFT", "GENERATED", "REVIEWED", "VALIDATED", "APPROVED", "RECALLED"}


def _norm_day(d: Optional[str]) -> str:
    if not d:
        return "MON"
    u = d.strip().upper()
    return DAY_NORM_MAP.get(u, u[:3])


def _is_slot_allowed_by_working_days(slot: TimeSlot, working_days: Optional[str]) -> bool:
    day_code = _norm_day(slot.day)
    if day_code == "SUN":
        return False
    if (working_days or "MON_SAT") == "MON_FRI" and day_code == "SAT":
        return False
    return True


def _is_instructional_slot(slot: Optional[TimeSlot]) -> bool:
    if not slot:
        return False
    return (getattr(slot, "slot_type", "") or "").upper() not in ("BREAK", "LUNCH")


def _load_version_context(db: Session, version_id: int) -> Tuple[
    TimetableVersion,
    List[TimetableEntry],
    Dict[int, TimeSlot],
    Dict[int, Room],
    Dict[int, Faculty],
    Dict[int, Course],
    Dict[int, Section],
    Dict[int, Batch],
    Dict[Tuple[int, int], str],
    List[TimetableEntry],
]:
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Timetable version #{version_id} not found.")

    entries = (
        db.query(TimetableEntry)
        .options(
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
            joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableEntry.room).joinedload(Room.lab),
            joinedload(TimetableEntry.slot),
            joinedload(TimetableEntry.section),
            joinedload(TimetableEntry.batch),
        )
        .filter(
            TimetableEntry.version_id == version_id,
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )

    slots_list = db.query(TimeSlot).all()
    slots_map = {s.id: s for s in slots_list}

    rooms_list = db.query(Room).options(joinedload(Room.building), joinedload(Room.lab)).all()
    rooms_map = {r.id: r for r in rooms_list}

    faculty_list = db.query(Faculty).options(joinedload(Faculty.user)).all()
    faculty_map = {f.id: f for f in faculty_list}

    courses_map = {c.id: c for c in db.query(Course).all()}
    sections_map = {s.id: s for s in db.query(Section).all()}
    batches_map = {b.id: b for b in db.query(Batch).all()}

    fa_lookup: Dict[Tuple[int, int], str] = {}
    for fa in db.query(FacultyAvailability).all():
        if fa.faculty_id is not None and fa.slot_id is not None and fa.availability is not None:
            fa_lookup[(fa.faculty_id, fa.slot_id)] = fa.availability

    # Load external active published canonical entries (from other sections/semesters in the same AY)
    # excluding entries belonging to sections already in this version so we don't self-conflict with the
    # old published schedule of the exact sections being revised.
    version_section_ids = {e.section_id for e in entries if e.section_id is not None}
    ext_query = (
        db.query(TimetableEntry)
        .join(Timetable, TimetableEntry.timetable_id == Timetable.id)
        .options(joinedload(TimetableEntry.slot))
        .filter(
            Timetable.status == "PUBLISHED",
            TimetableEntry.status == "ACTIVE",
        )
    )
    if version.academic_year_id:
        ext_query = ext_query.filter(Timetable.academic_year_id == version.academic_year_id)
    if version_section_ids:
        ext_query = ext_query.filter(~TimetableEntry.section_id.in_(list(version_section_ids)))
    external_published_entries = ext_query.all()

    return (
        version,
        entries,
        slots_map,
        rooms_map,
        faculty_map,
        courses_map,
        sections_map,
        batches_map,
        fa_lookup,
        external_published_entries,
    )


def _get_logical_block(
    entry: TimetableEntry,
    all_entries: List[TimetableEntry],
    slots_map: Dict[int, TimeSlot],
    courses_map: Dict[int, Course],
) -> List[TimetableEntry]:
    """
    Returns the ordered list of entries belonging to the same logical session block.
    - If block_group_id is populated, uses all entries sharing that block_group_id.
    - Otherwise, if the entry is a PRACTICAL/LAB session, detects consecutive same-day
      entries for the same (section, batch, course, faculty, room).
    """
    def _entry_start_time(e: TimetableEntry) -> datetime.time:
        if e.slot_id is not None:
            s = slots_map.get(e.slot_id)
            if s is not None and s.start_time is not None:
                return s.start_time
        return datetime.time.min

    if entry.block_group_id:
        grp = [e for e in all_entries if e.block_group_id == entry.block_group_id]
        grp.sort(key=_entry_start_time)
        return grp or [entry]

    course = courses_map.get(entry.course_id) if entry.course_id else None
    is_practical = (
        (entry.hour_type or "").upper() == "PRACTICAL"
        or (course is not None and (getattr(course, "requires_lab", False) or (course.course_type or "").upper() == "LAB"))
    )
    if not is_practical or not entry.slot_id or entry.slot_id not in slots_map:
        return [entry]

    base_slot = slots_map[entry.slot_id]
    base_day = _norm_day(base_slot.day)
    same_group = [
        e for e in all_entries
        if e.section_id == entry.section_id
        and e.batch_id == entry.batch_id
        and e.course_id == entry.course_id
        and e.faculty_id == entry.faculty_id
        and e.room_id == entry.room_id
        and e.slot_id in slots_map
        and _norm_day(slots_map[e.slot_id].day) == base_day
    ]
    if len(same_group) <= 1:
        return [entry]

    same_group.sort(key=_entry_start_time)
    # Check if they are adjacent in time
    day_slots = sorted(
        [s for s in slots_map.values() if _norm_day(s.day) == base_day and _is_instructional_slot(s)],
        key=lambda s: s.start_time or datetime.time.min,
    )
    slot_idx_map = {s.id: idx for idx, s in enumerate(day_slots)}
    indices = [slot_idx_map.get(e.slot_id, -99) if e.slot_id is not None else -99 for e in same_group]
    if all(indices[i] + 1 == indices[i + 1] for i in range(len(indices) - 1)):
        return same_group
    return [entry]


def _expand_block_moves(
    moves: List[ProposedMoveItem],
    entries_map: Dict[int, TimetableEntry],
    all_entries: List[TimetableEntry],
    slots_map: Dict[int, TimeSlot],
    courses_map: Dict[int, Course],
    working_days: Optional[str],
) -> Tuple[List[ProposedMoveItem], List[str]]:
    """
    Expands any single-entry move on a multi-period practical/lab block into consecutive-slot
    moves for the whole block, unless all block entries were already explicitly provided.
    """
    explicit_ids = {m.entry_id for m in moves}
    expanded: List[ProposedMoveItem] = []
    seen_ids: Set[int] = set()
    block_errors: List[str] = []

    for m in moves:
        if m.entry_id in seen_ids:
            continue
        entry = entries_map.get(m.entry_id)
        if not entry:
            expanded.append(m)
            seen_ids.add(m.entry_id)
            continue

        block = _get_logical_block(entry, all_entries, slots_map, courses_map)
        if len(block) <= 1 or all(be.id in explicit_ids for be in block):
            expanded.append(m)
            seen_ids.add(m.entry_id)
            continue

        # Single move provided for a multi-period block -> move entire block consecutively
        target_slot = slots_map.get(m.target_slot_id)
        if not target_slot or not _is_instructional_slot(target_slot) or not _is_slot_allowed_by_working_days(target_slot, working_days):
            block_errors.append(f"Target slot #{m.target_slot_id} is not an active instructional slot for this multi-period block.")
            expanded.append(m)
            seen_ids.add(m.entry_id)
            continue

        target_day = _norm_day(target_slot.day)
        day_slots = sorted(
            [s for s in slots_map.values() if _norm_day(s.day) == target_day],
            key=lambda s: s.start_time or datetime.time.min,
        )
        try:
            start_pos = next(i for i, s in enumerate(day_slots) if s.id == target_slot.id)
        except StopIteration:
            block_errors.append(f"Target slot #{m.target_slot_id} could not be located on {target_day}.")
            expanded.append(m)
            seen_ids.add(m.entry_id)
            continue

        # Must fit len(block) consecutive instructional slots without crossing a BREAK/LUNCH
        if start_pos + len(block) > len(day_slots):
            block_errors.append(
                f"Multi-period session requires {len(block)} consecutive periods on {target_day}, which exceeds remaining slots."
            )
            expanded.append(m)
            seen_ids.add(m.entry_id)
            continue

        candidate_slots = day_slots[start_pos : start_pos + len(block)]
        if any(not _is_instructional_slot(cs) for cs in candidate_slots):
            block_errors.append(
                f"Multi-period session requires {len(block)} consecutive instructional periods without a break or lunch interruption."
            )
            expanded.append(m)
            seen_ids.add(m.entry_id)
            continue

        for be, cs in zip(block, candidate_slots):
            expanded.append(
                ProposedMoveItem(
                    entry_id=be.id,
                    target_slot_id=cs.id,
                    target_room_id=m.target_room_id,
                    target_faculty_id=m.target_faculty_id,
                )
            )
            seen_ids.add(be.id)

    return expanded, block_errors


def _evaluate_moves(
    version: TimetableVersion,
    all_entries: List[TimetableEntry],
    moves: List[ProposedMoveItem],
    slots_map: Dict[int, TimeSlot],
    rooms_map: Dict[int, Room],
    faculty_map: Dict[int, Faculty],
    courses_map: Dict[int, Course],
    sections_map: Dict[int, Section],
    batches_map: Dict[int, Batch],
    fa_lookup: Dict[Tuple[int, int], str],
    external_published_entries: List[TimetableEntry],
) -> Tuple[bool, List[MoveOutcomeItem], List[str], List[str], List[ProposedMoveItem]]:
    entries_map = {e.id: e for e in all_entries}
    expanded_moves, block_errors = _expand_block_moves(
        moves=moves,
        entries_map=entries_map,
        all_entries=all_entries,
        slots_map=slots_map,
        courses_map=courses_map,
        working_days=version.working_days,
    )

    # Build simulated post-move state
    sim_slot: Dict[int, Optional[int]] = {e.id: e.slot_id for e in all_entries}
    sim_room: Dict[int, Optional[int]] = {e.id: e.room_id for e in all_entries}
    sim_faculty: Dict[int, Optional[int]] = {e.id: e.faculty_id for e in all_entries}

    for m in expanded_moves:
        if m.entry_id in entries_map:
            sim_slot[m.entry_id] = m.target_slot_id
            if m.target_room_id is not None:
                sim_room[m.entry_id] = m.target_room_id
            if m.target_faculty_id is not None:
                sim_faculty[m.entry_id] = m.target_faculty_id

    outcomes: List[MoveOutcomeItem] = []
    all_conflicts: List[str] = list(block_errors)
    all_warnings: List[str] = []

    for m in expanded_moves:
        reasons: List[str] = []
        warnings: List[str] = []
        affected: Set[int] = set()

        entry = entries_map.get(m.entry_id)
        if not entry:
            reasons.append(f"Timetable entry #{m.entry_id} does not belong to version #{version.id}.")
            outcomes.append(MoveOutcomeItem(entry_id=m.entry_id, target_slot_id=m.target_slot_id, valid=False, reasons=reasons))
            all_conflicts.extend(reasons)
            continue

        target_slot = slots_map.get(m.target_slot_id)
        if not target_slot:
            reasons.append(f"Target time slot #{m.target_slot_id} does not exist.")
        elif not _is_instructional_slot(target_slot):
            slot_time_str = target_slot.start_time.strftime('%H:%M') if target_slot.start_time else "N/A"
            reasons.append(f"Cannot move a class into a {target_slot.slot_type} slot ({target_slot.day} {slot_time_str}).")
        elif not _is_slot_allowed_by_working_days(target_slot, version.working_days):
            reasons.append(f"Target day {target_slot.day} is outside the configured working-day schedule ({version.working_days}).")

        eff_room_id = sim_room.get(entry.id)
        eff_faculty_id = sim_faculty.get(entry.id)
        room = rooms_map.get(eff_room_id) if eff_room_id else None
        faculty = faculty_map.get(eff_faculty_id) if eff_faculty_id else None
        course = courses_map.get(entry.course_id) if entry.course_id else None
        section = sections_map.get(entry.section_id) if entry.section_id else None
        batch = batches_map.get(entry.batch_id) if entry.batch_id else None

        fac_name = faculty.user.name if (faculty and faculty.user) else f"Faculty #{eff_faculty_id}"
        room_name = room.room_number if room else f"Room #{eff_room_id}"
        sec_name = section.section_name if section else f"Section #{entry.section_id}"

        # Room suitability & capacity checks
        if eff_room_id and not room:
            reasons.append(f"Selected room #{eff_room_id} does not exist.")
        elif room:
            if (getattr(room, "status", "ACTIVE") or "ACTIVE") != "ACTIVE":
                reasons.append(f"Room {room_name} is marked '{room.status}' and cannot be scheduled.")

            is_lab_req = (
                (entry.hour_type or "").upper() == "PRACTICAL"
                or (course is not None and (getattr(course, "requires_lab", False) or (course.course_type or "").upper() == "LAB"))
            )
            is_lab_room = (getattr(room, "room_type", "") == "LAB") or (getattr(room, "lab", None) is not None)
            if is_lab_req and not is_lab_room:
                reasons.append(f"Course requires a laboratory, but {room_name} is not a lab room.")

            req_cap = (batch.student_count if batch and batch.student_count else (section.student_count if section else 0)) or 0
            if room.capacity is not None and req_cap > room.capacity:
                reasons.append(f"Room {room_name} capacity ({room.capacity}) is smaller than class size ({req_cap}).")

        # Faculty declared unavailability
        if eff_faculty_id and target_slot:
            fa_status = fa_lookup.get((eff_faculty_id, target_slot.id))
            if fa_status == "UNAVAILABLE":
                st_str = target_slot.start_time.strftime('%H:%M') if target_slot.start_time else "N/A"
                et_str = target_slot.end_time.strftime('%H:%M') if target_slot.end_time else "N/A"
                reasons.append(f"{fac_name} has declared UNAVAILABLE for {target_slot.day} {st_str}-{et_str}.")

        # Overlap checks against other entries in this version
        if target_slot:
            for other in all_entries:
                if other.id == entry.id:
                    continue
                other_slot_id = sim_slot.get(other.id)
                other_slot = slots_map.get(other_slot_id) if other_slot_id else None
                if not other_slot or not slots_overlap(target_slot, other_slot):
                    continue

                other_room_id = sim_room.get(other.id)
                other_fac_id = sim_faculty.get(other.id)

                # Section overlap (same section & incompatible batch)
                if other.section_id == entry.section_id:
                    if other.batch_id is None or entry.batch_id is None or other.batch_id == entry.batch_id:
                        oc = courses_map.get(other.course_id) if other.course_id is not None else None
                        oc_label = oc.course_code if oc else f"Entry #{other.id}"
                        reasons.append(f"{sec_name} already has {oc_label} scheduled during this period.")
                        affected.add(other.id)

                # Faculty overlap across all sections in version
                if eff_faculty_id and other_fac_id == eff_faculty_id:
                    osec = sections_map.get(other.section_id) if other.section_id is not None else None
                    osec_label = osec.section_name if osec else f"Section #{other.section_id}"
                    reasons.append(f"{fac_name} is already teaching {osec_label} during this period.")
                    affected.add(other.id)

                # Room overlap across all sections in version
                if eff_room_id and other_room_id == eff_room_id:
                    osec = sections_map.get(other.section_id) if other.section_id is not None else None
                    osec_label = osec.section_name if osec else f"Section #{other.section_id}"
                    reasons.append(f"Room {room_name} is already occupied by {osec_label} during this period.")
                    affected.add(other.id)

            # Overlap checks against external published canonical entries (other departments/sections in same AY)
            for ext in external_published_entries:
                if not ext.slot or not slots_overlap(target_slot, ext.slot):
                    continue
                if eff_faculty_id and ext.faculty_id == eff_faculty_id:
                    reasons.append(f"{fac_name} is already scheduled in another published section during this period.")
                if eff_room_id and ext.room_id == eff_room_id:
                    reasons.append(f"Room {room_name} is already occupied by another published section during this period.")

        if block_errors and not reasons:
            reasons.extend(block_errors)

        valid_move = len(reasons) == 0
        if not valid_move:
            all_conflicts.extend(reasons)
        all_warnings.extend(warnings)
        outcomes.append(
            MoveOutcomeItem(
                entry_id=m.entry_id,
                target_slot_id=m.target_slot_id,
                valid=valid_move,
                reasons=list(dict.fromkeys(reasons)),
                warnings=list(dict.fromkeys(warnings)),
                affected_entry_ids=sorted(affected),
            )
        )

    overall_valid = len(all_conflicts) == 0 and all(o.valid for o in outcomes)
    return overall_valid, outcomes, list(dict.fromkeys(all_conflicts)), list(dict.fromkeys(all_warnings)), expanded_moves


def get_move_options(
    db: Session,
    version_id: int,
    entry_id: int,
    current_user: User,
) -> MoveOptionsResponse:
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can inspect timetable move options.")

    (
        version,
        all_entries,
        slots_map,
        rooms_map,
        faculty_map,
        courses_map,
        sections_map,
        batches_map,
        fa_lookup,
        external_published_entries,
    ) = _load_version_context(db, version_id)

    if version.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Timetable version #{version_id} in status '{version.status}' is locked and cannot be edited.",
        )

    entries_map = {e.id: e for e in all_entries}
    entry = entries_map.get(entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entry #{entry_id} not found in version #{version_id}.")

    block = _get_logical_block(entry, all_entries, slots_map, courses_map)
    course = courses_map.get(entry.course_id) if entry.course_id else None
    section = sections_map.get(entry.section_id) if entry.section_id else None
    batch = batches_map.get(entry.batch_id) if entry.batch_id else None
    is_lab_req = (
        (entry.hour_type or "").upper() == "PRACTICAL"
        or (course is not None and (getattr(course, "requires_lab", False) or (course.course_type or "").upper() == "LAB"))
    )
    req_cap = (batch.student_count if batch and batch.student_count else (section.student_count if section else 0)) or 0

    day_order = {"MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6, "SUN": 7}
    sorted_slots = sorted(
        slots_map.values(),
        key=lambda s: (day_order.get(_norm_day(s.day), 9), s.start_time or datetime.time.min),
    )

    options: List[MoveOptionSlot] = []
    for slot in sorted_slots:
        if not _is_slot_allowed_by_working_days(slot, version.working_days):
            continue

        st_str = slot.start_time.strftime("%H:%M") if slot.start_time else ""
        et_str = slot.end_time.strftime("%H:%M") if slot.end_time else ""
        stype = (getattr(slot, "slot_type", "CLASS") or "CLASS").upper()

        if stype in ("BREAK", "LUNCH"):
            options.append(
                MoveOptionSlot(
                    slot_id=slot.id,
                    day=_norm_day(slot.day),
                    start_time=st_str,
                    end_time=et_str,
                    slot_type=stype,
                    can_move=False,
                    blocked_reason=f"Cannot schedule classes during {stype}.",
                )
            )
            continue

        valid, _outcomes, conflicts, warnings, _exp = _evaluate_moves(
            version=version,
            all_entries=all_entries,
            moves=[ProposedMoveItem(entry_id=entry_id, target_slot_id=slot.id)],
            slots_map=slots_map,
            rooms_map=rooms_map,
            faculty_map=faculty_map,
            courses_map=courses_map,
            sections_map=sections_map,
            batches_map=batches_map,
            fa_lookup=fa_lookup,
            external_published_entries=external_published_entries,
        )

        # Compute genuinely available alternative rooms at this slot
        alt_rooms: List[AlternativeRoomOption] = []
        occupied_room_ids: Set[int] = set()
        for other in all_entries:
            if other.id in {be.id for be in block}:
                continue
            oslot = slots_map.get(other.slot_id) if other.slot_id else None
            if oslot and slots_overlap(slot, oslot) and other.room_id:
                occupied_room_ids.add(other.room_id)
        for ext in external_published_entries:
            if ext.slot and slots_overlap(slot, ext.slot) and ext.room_id:
                occupied_room_ids.add(ext.room_id)

        for r in rooms_map.values():
            if r.id in occupied_room_ids:
                continue
            if (getattr(r, "status", "ACTIVE") or "ACTIVE") != "ACTIVE":
                continue
            if r.capacity is not None and req_cap > r.capacity:
                continue
            is_lab_r = (getattr(r, "room_type", "") == "LAB") or (getattr(r, "lab", None) is not None)
            if is_lab_req and not is_lab_r:
                continue
            if not is_lab_req and getattr(r, "room_type", "") == "LAB":
                continue
            alt_rooms.append(
                AlternativeRoomOption(
                    room_id=r.id,
                    room_number=r.room_number or f"Room #{r.id}",
                    building_name=r.building.name if r.building else None,
                    capacity=r.capacity,
                    room_type=r.room_type,
                )
            )
        alt_rooms.sort(key=lambda ar: ar.room_number)

        options.append(
            MoveOptionSlot(
                slot_id=slot.id,
                day=_norm_day(slot.day),
                start_time=st_str,
                end_time=et_str,
                slot_type=stype,
                can_move=valid,
                blocked_reason="; ".join(conflicts) if conflicts else None,
                warnings=warnings,
                alternative_rooms=alt_rooms[:15],
            )
        )

    return MoveOptionsResponse(
        version_id=version.id,
        entry_id=entry_id,
        block_entry_ids=[be.id for be in block],
        revision=version.revision or 1,
        options=options,
    )


def validate_proposed_arrangements(
    db: Session,
    version_id: int,
    req: ArrangementValidateRequest,
    current_user: User,
) -> ArrangementValidateResponse:
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can validate timetable arrangements.")

    (
        version,
        all_entries,
        slots_map,
        rooms_map,
        faculty_map,
        courses_map,
        sections_map,
        batches_map,
        fa_lookup,
        external_published_entries,
    ) = _load_version_context(db, version_id)

    current_rev = version.revision or 1
    if version.status not in EDITABLE_STATUSES:
        return ArrangementValidateResponse(
            valid=False,
            can_save=False,
            current_revision=current_rev,
            conflicts=[f"Timetable version #{version_id} is '{version.status}' and cannot be modified."],
        )

    stale_conflicts: List[str] = []
    if req.expected_revision is not None and req.expected_revision != current_rev:
        stale_conflicts.append(
            f"Stale revision: client expected revision {req.expected_revision}, but server is at revision {current_rev}."
        )

    valid, outcomes, conflicts, warnings, _exp = _evaluate_moves(
        version=version,
        all_entries=all_entries,
        moves=req.moves,
        slots_map=slots_map,
        rooms_map=rooms_map,
        faculty_map=faculty_map,
        courses_map=courses_map,
        sections_map=sections_map,
        batches_map=batches_map,
        fa_lookup=fa_lookup,
        external_published_entries=external_published_entries,
    )

    combined_conflicts = stale_conflicts + conflicts
    can_save = valid and len(stale_conflicts) == 0

    return ArrangementValidateResponse(
        valid=valid,
        can_save=can_save,
        current_revision=current_rev,
        outcomes=outcomes,
        conflicts=combined_conflicts,
        warnings=warnings,
    )


def build_version_detail_response(db: Session, version_id: int) -> TimetableVersionDetailResponse:
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    entries = (
        db.query(TimetableEntry)
        .options(
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
            joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableEntry.slot),
            joinedload(TimetableEntry.section).joinedload(Section.class_teacher).joinedload(Faculty.user),
            joinedload(TimetableEntry.department),
            joinedload(TimetableEntry.program),
            joinedload(TimetableEntry.semester),
        )
        .filter(
            TimetableEntry.version_id == version_id,
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )

    ay_name = None
    if version.academic_year_id:
        ay = db.query(AcademicYear).filter(AcademicYear.id == version.academic_year_id).first()
        ay_name = ay.name if ay else None

    creator_name = None
    if version.created_by:
        cu = db.query(User).filter(User.id == version.created_by).first()
        creator_name = cu.name if cu else None

    approver_name = None
    if version.approved_by:
        au = db.query(User).filter(User.id == version.approved_by).first()
        approver_name = au.name if au else None

    recaller_name = None
    if version.recalled_by:
        ru = db.query(User).filter(User.id == version.recalled_by).first()
        recaller_name = ru.name if ru else None

    dept_name = None
    prog_name = None
    sem_num = None
    sec_name = None
    ct_name = None
    ct_desig = None
    ct_contact = None
    section_ids_in_ver: Set[int] = set()

    if entries:
        first_e = entries[0]
        dept_name = first_e.department.name if first_e.department else None
        prog_name = first_e.program.program_name if first_e.program else None
        sem_num = first_e.semester.semester_number if first_e.semester else None
        sec_name = first_e.section.section_name if first_e.section else None
        if first_e.section and first_e.section.class_teacher:
            ct = first_e.section.class_teacher
            ct_name = ct.user.name if ct.user else None
            ct_desig = ct.designation
            ct_contact = ct.contact_number
        section_ids_in_ver = {e.section_id for e in entries if e.section_id is not None}

    # Compute available instructional slots count for summary cards
    total_instr_slots = sum(
        1
        for s in db.query(TimeSlot).all()
        if _is_instructional_slot(s) and _is_slot_allowed_by_working_days(s, version.working_days)
    )
    total_sections = max(len(section_ids_in_ver), 1) if entries else 0
    occupied_sec_slots = {(e.section_id, e.slot_id) for e in entries if e.section_id and e.slot_id}
    available_periods = max(0, (total_instr_slots * total_sections) - len(occupied_sec_slots)) if total_sections else 0

    detail_entries: List[TimetableEntryDetailResponse] = []
    for e in entries:
        detail_entries.append(
            TimetableEntryDetailResponse(
                id=e.id,
                timetable_id=e.timetable_id,
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
                course_assignment_id=e.course_assignment_id,
                hour_type=e.hour_type,
                block_group_id=e.block_group_id,
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
                section_name=e.section.section_name if e.section else None,
            )
        )

    return TimetableVersionDetailResponse(
        id=version.id,
        academic_year_id=version.academic_year_id,
        version_number=version.version_number,
        status=version.status,
        created_by=version.created_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        approved_revision=version.approved_revision,
        recalled_by=version.recalled_by,
        recalled_at=version.recalled_at,
        recall_reason=version.recall_reason,
        recalled_by_name=recaller_name,
        validation_status=version.validation_status or "NOT_VALIDATED",
        validation_errors_count=version.validation_errors_count or 0,
        validation_warnings_count=version.validation_warnings_count or 0,
        validated_at=version.validated_at,
        created_at=version.created_at,
        published_at=version.published_at,
        reason=version.reason,
        revision=version.revision or 1,
        validated_revision=version.validated_revision,
        last_saved_at=version.last_saved_at,
        last_saved_by=version.last_saved_by,
        finalized_by=version.finalized_by,
        finalized_at=version.finalized_at,
        working_days=version.working_days or "MON_SAT",
        score_summary=version.score_summary,
        department_id=version.department_id or (entries[0].department_id if entries else None),
        program_id=version.program_id or (entries[0].program_id if entries else None),
        semester_id=version.semester_id or (entries[0].semester_id if entries else None),
        department_name=dept_name,
        program_name=prog_name,
        academic_year_name=ay_name,
        semester_number=sem_num,
        section_name=sec_name,
        class_teacher_name=ct_name,
        class_teacher_designation=ct_desig,
        class_teacher_contact=ct_contact,
        created_by_name=creator_name,
        approved_by_name=approver_name,
        entry_count=len(entries),
        section_names=sorted(list({e.section.section_name for e in entries if e.section and e.section.section_name})),
        total_sections=total_sections,
        available_periods=available_periods,
        timetable_entries=detail_entries,
    )


def save_arrangements(
    db: Session,
    version_id: int,
    req: ArrangementSaveRequest,
    current_user: User,
) -> ArrangementSaveResponse:
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can save timetable arrangements.")

    # Row-level lock on TimetableVersion for atomic concurrency control
    locked_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.id == version_id)
        .with_for_update()
        .first()
    )
    if not locked_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Timetable version #{version_id} not found.")

    if locked_version.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Timetable version #{version_id} is '{locked_version.status}' and cannot be edited.",
        )

    current_rev = locked_version.revision or 1
    if locked_version.revision is None:
        locked_version.revision = current_rev
    expected_rev = req.expected_revision if req.expected_revision is not None else current_rev
    if expected_rev != current_rev:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Stale revision: your draft is at revision {req.expected_revision}, but another administrator saved revision {current_rev}. Please reload the latest revision.",
                "expected_revision": req.expected_revision,
                "current_revision": current_rev,
            },
        )

    (
        _ver,
        all_entries,
        slots_map,
        rooms_map,
        faculty_map,
        courses_map,
        sections_map,
        batches_map,
        fa_lookup,
        external_published_entries,
    ) = _load_version_context(db, version_id)

    valid, _outcomes, conflicts, _warnings, expanded_moves = _evaluate_moves(
        version=locked_version,
        all_entries=all_entries,
        moves=req.moves,
        slots_map=slots_map,
        rooms_map=rooms_map,
        faculty_map=faculty_map,
        courses_map=courses_map,
        sections_map=sections_map,
        batches_map=batches_map,
        fa_lookup=fa_lookup,
        external_published_entries=external_published_entries,
    )

    if not valid:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "; ".join(conflicts),
                "conflicts": conflicts,
                "current_revision": current_rev,
            },
        )

    entries_map = {e.id: e for e in all_entries}
    new_revision = current_rev + 1
    now_utc = utc_now()

    try:
        saved_count = 0
        for m in expanded_moves:
            entry = entries_map[m.entry_id]
            prev_slot_id = entry.slot_id
            prev_room_id = entry.room_id
            prev_fac_id = entry.faculty_id
            prev_day = _norm_day(slots_map[prev_slot_id].day) if prev_slot_id and prev_slot_id in slots_map else None

            new_slot_id = m.target_slot_id
            new_room_id = m.target_room_id if m.target_room_id is not None else prev_room_id
            new_fac_id = m.target_faculty_id if m.target_faculty_id is not None else prev_fac_id
            new_day = _norm_day(slots_map[new_slot_id].day) if new_slot_id in slots_map else None

            entry.slot_id = new_slot_id
            entry.room_id = new_room_id
            entry.faculty_id = new_fac_id
            saved_count += 1

            db.add(
                TimetableChangeHistory(
                    version_id=locked_version.id,
                    revision=new_revision,
                    entry_id=entry.id,
                    admin_id=current_user.id,
                    previous_slot_id=prev_slot_id,
                    new_slot_id=new_slot_id,
                    previous_room_id=prev_room_id,
                    new_room_id=new_room_id,
                    previous_faculty_id=prev_fac_id,
                    new_faculty_id=new_fac_id,
                    previous_day=prev_day,
                    new_day=new_day,
                    validation_outcome="VALID",
                    reason=req.reason,
                )
            )

        old_status = locked_version.status
        locked_version.revision = new_revision
        locked_version.status = "REVIEWED"
        locked_version.validated_revision = None  # Invalidate previous validation
        locked_version.validation_status = "NOT_VALIDATED"
        locked_version.validation_errors_count = 0
        locked_version.validation_warnings_count = 0
        locked_version.approved_by = None
        locked_version.approved_at = None
        locked_version.approved_revision = None
        locked_version.finalized_by = None
        locked_version.finalized_at = None
        locked_version.last_saved_at = now_utc
        locked_version.last_saved_by = current_user.id

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="TIMETABLE_ARRANGEMENT_SAVED",
                entity_type="TimetableVersion",
                entity_id=locked_version.id,
                old_value={"status": old_status, "revision": current_rev},
                new_value={"status": "REVIEWED", "revision": new_revision, "moves_saved": saved_count},
            )
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save arrangement: {str(exc)}")

    detail = build_version_detail_response(db, version_id)
    return ArrangementSaveResponse(
        success=True,
        version_id=locked_version.id,
        revision=new_revision,
        status=locked_version.status or "REVIEWED",
        last_saved_at=now_utc,
        saved_count=saved_count,
        version_detail=detail,
    )


def create_revision_from_version(
    db: Session,
    source_version_id: int,
    current_user: User,
) -> TimetableVersionDetailResponse:
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can create timetable revisions.")

    source = db.query(TimetableVersion).filter(TimetableVersion.id == source_version_id).first()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Timetable version #{source_version_id} not found.")

    source_entries = (
        db.query(TimetableEntry)
        .filter(TimetableEntry.version_id == source_version_id, TimetableEntry.status != "CANCELLED")
        .all()
    )
    if not source_entries:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source timetable version has no entries to revise.")

    now_utc = utc_now()
    try:
        new_ver = TimetableVersion(
            academic_year_id=source.academic_year_id,
            curriculum_version_id=source.curriculum_version_id,
            department_id=source.department_id or source_entries[0].department_id,
            program_id=source.program_id or source_entries[0].program_id,
            semester_id=source.semester_id or source_entries[0].semester_id,
            working_days=source.working_days or "MON_SAT",
            status="GENERATED",
            revision=1,
            created_by=current_user.id,
            last_saved_at=now_utc,
            last_saved_by=current_user.id,
            reason=f"Revision from Version #{source.id}",
        )
        db.add(new_ver)
        db.flush()

        for se in source_entries:
            db.add(
                TimetableEntry(
                    version_id=new_ver.id,
                    timetable_id=None,  # Private draft — never linked to canonical published Timetable
                    department_id=se.department_id,
                    program_id=se.program_id,
                    semester_id=se.semester_id,
                    section_id=se.section_id,
                    batch_id=se.batch_id,
                    course_id=se.course_id,
                    faculty_id=se.faculty_id,
                    room_id=se.room_id,
                    slot_id=se.slot_id,
                    course_assignment_id=se.course_assignment_id,
                    hour_type=se.hour_type,
                    block_group_id=se.block_group_id,
                    status="DRAFT",
                )
            )

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="TIMETABLE_REVISION_CREATED",
                entity_type="TimetableVersion",
                entity_id=new_ver.id,
                old_value={"source_version_id": source.id, "source_status": source.status},
                new_value={"status": "GENERATED", "revision": 1},
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create revision: {str(exc)}")

    return build_version_detail_response(db, new_ver.id)


def get_change_history(
    db: Session,
    version_id: int,
    current_user: User,
) -> List[TimetableChangeHistoryItem]:
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can view timetable change history.")

    rows = (
        db.query(TimetableChangeHistory)
        .options(joinedload(TimetableChangeHistory.admin))
        .filter(TimetableChangeHistory.version_id == version_id)
        .order_by(TimetableChangeHistory.revision.desc(), TimetableChangeHistory.id.desc())
        .all()
    )
    return [
        TimetableChangeHistoryItem(
            id=r.id,
            version_id=r.version_id,
            revision=r.revision,
            entry_id=r.entry_id,
            admin_id=r.admin_id,
            admin_name=r.admin.name if r.admin else None,
            previous_slot_id=r.previous_slot_id,
            new_slot_id=r.new_slot_id,
            previous_room_id=r.previous_room_id,
            new_room_id=r.new_room_id,
            previous_faculty_id=r.previous_faculty_id,
            new_faculty_id=r.new_faculty_id,
            previous_day=r.previous_day,
            new_day=r.new_day,
            validation_outcome=r.validation_outcome,
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]
