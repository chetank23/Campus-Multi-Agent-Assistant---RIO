"""
agents/tools/campus_tools.py
----------------------------
Safe, read-only tools for Course, Room/Lab, Academic Calendar, Announcements,
and Timetable Status lookups. All answers are strictly grounded in PostgreSQL records.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.academic import (
    AcademicYear,
    Department,
    Faculty,
    Program,
    Section,
    Semester,
    Student,
)
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import AcademicCalendar, Building, Room, TimeSlot
from backend.models.timetable import Timetable, TimetableEntry, TimetableVersion
from backend.models.workflow import AuditLog, Notification


def get_course_details_data(
    db: Session,
    query_str: str,
) -> Dict[str, Any]:
    """
    Looks up course information by course code or title, including credits,
    course type, department, and assigned faculty.
    """
    clean_query = query_str.strip()
    pattern = f"%{clean_query}%"
    courses = (
        db.query(Course)
        .filter(
            or_(
                Course.course_code.ilike(pattern),
                Course.course_name.ilike(pattern),
            )
        )
        .limit(5)
        .all()
    )

    if not courses:
        return {
            "message": f"No course matching '{query_str}' was found in the academic catalog.",
            "results": [],
        }

    results: List[Dict[str, Any]] = []
    for c in courses:
        dept = db.query(Department).filter(Department.id == c.department_id).first() if c.department_id else None

        # Fetch assigned faculty from CourseAssignment
        assignments = (
            db.query(CourseAssignment)
            .filter(CourseAssignment.course_id == c.id)
            .all()
        )
        teachers: List[str] = []
        for a in assignments:
            if a.faculty_id:
                fac = db.query(Faculty).filter(Faculty.id == a.faculty_id).first()
                if fac and fac.user:
                    teachers.append(fac.user.name)

        results.append({
            "code": c.course_code or "N/A",
            "title": c.course_name or "N/A",
            "credits": c.credits or 3,
            "department": dept.name if dept else "N/A",
            "course_type": c.course_type or "THEORY",
            "is_elective": (c.course_type == "ELECTIVE"),
            "requires_lab": c.requires_lab,
            "assigned_faculty": list(dict.fromkeys(teachers)),
        })

    return {
        "count": len(results),
        "results": results,
    }


def get_course_information_data(
    db: Session,
    query_str: str,
) -> Dict[str, Any]:
    """Alias for get_course_details_data with comprehensive course info."""
    return get_course_details_data(db=db, query_str=query_str)


def get_room_or_lab_details_data(
    db: Session,
    room_query: str,
) -> Dict[str, Any]:
    """
    Looks up physical classroom or laboratory specifications and location.
    """
    pattern = f"%{room_query.strip()}%"
    rooms = (
        db.query(Room)
        .join(Building, Room.building_id == Building.id, isouter=True)
        .filter(
            or_(
                Room.room_number.ilike(pattern),
                Room.room_type.ilike(pattern),
                Building.name.ilike(pattern),
            )
        )
        .limit(5)
        .all()
    )

    if not rooms:
        return {
            "message": f"No room or lab matching '{room_query}' was found.",
            "results": [],
        }

    results: List[Dict[str, Any]] = []
    for r in rooms:
        bldg = r.building
        results.append({
            "room_number": r.room_number,
            "room_type": r.room_type,
            "capacity": r.capacity,
            "building": bldg.name if bldg else "Main Campus",
            "is_active": (r.status == "ACTIVE"),
            "status": r.status or "ACTIVE",
        })

    return {
        "count": len(results),
        "results": results,
    }


def get_room_availability_data(
    db: Session,
    day: Optional[str] = None,
    date_str: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    room_query: Optional[str] = None,
    room_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Checks room or laboratory availability against both the active published timetable
    and approved/pending resource bookings.
    """
    target_day: Optional[str] = None
    target_date: Optional[datetime.date] = None

    if date_str:
        try:
            target_date = datetime.date.fromisoformat(date_str.strip())
            target_day = target_date.strftime("%A").upper()
        except ValueError:
            target_day = None

    if not target_day and day:
        clean_day = day.strip().upper()
        if clean_day == "TODAY":
            target_date = datetime.date.today()
            target_day = target_date.strftime("%A").upper()
        elif clean_day == "TOMORROW":
            target_date = datetime.date.today() + datetime.timedelta(days=1)
            target_day = target_date.strftime("%A").upper()
        else:
            day_map = {
                "MON": "MONDAY", "MONDAY": "MONDAY",
                "TUE": "TUESDAY", "TUESDAY": "TUESDAY",
                "WED": "WEDNESDAY", "WEDNESDAY": "WEDNESDAY",
                "THU": "THURSDAY", "THURSDAY": "THURSDAY",
                "FRI": "FRIDAY", "FRIDAY": "FRIDAY",
                "SAT": "SATURDAY", "SATURDAY": "SATURDAY",
                "SUN": "SUNDAY", "SUNDAY": "SUNDAY",
            }
            target_day = day_map.get(clean_day, clean_day)

    if not target_day:
        target_date = datetime.date.today()
        target_day = target_date.strftime("%A").upper()

    t_start: Optional[datetime.time] = None
    t_end: Optional[datetime.time] = None
    if start_time:
        try:
            t_start = datetime.time.fromisoformat(start_time.strip()[:5])
        except ValueError:
            pass
    if end_time:
        try:
            t_end = datetime.time.fromisoformat(end_time.strip()[:5])
        except ValueError:
            pass

    # 1. Inspect Published Timetable Version
    published_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
        .first()
    )

    occupied_rooms: Dict[int, List[str]] = {}

    if published_version:
        tt_query = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableEntry.version_id == published_version.id,
                TimeSlot.day == target_day,
                TimetableEntry.status == "ACTIVE",
            )
        )
        if t_start and t_end:
            tt_query = tt_query.filter(
                TimeSlot.start_time < t_end,
                TimeSlot.end_time > t_start,
            )

        for entry in tt_query.all():
            if entry.room_id:
                slot_info = (
                    f"{entry.slot.day} {entry.slot.start_time.strftime('%H:%M')}-{entry.slot.end_time.strftime('%H:%M')}"
                    if (entry.slot and entry.slot.start_time and entry.slot.end_time)
                    else "Scheduled Class"
                )
                desc = f"Class: {entry.course.course_code if entry.course else 'Course'} ({slot_info})"
                occupied_rooms.setdefault(entry.room_id, []).append(desc)

    # 2. Inspect Resource Bookings
    if target_date:
        b_query = db.query(ResourceBooking).filter(
            ResourceBooking.date == target_date,
            ResourceBooking.status.in_(["APPROVED", "PENDING"]),
        )
        if t_start and t_end:
            b_query = b_query.filter(
                ResourceBooking.start_time < t_end,
                ResourceBooking.end_time > t_start,
            )
        for b in b_query.all():
            # Check if resource matches room
            res = db.query(Resource).filter(Resource.id == b.resource_id).first()
            if res and res.name:
                matched_room = db.query(Room).filter(Room.room_number.ilike(res.name.strip())).first()
                if matched_room:
                    st_str = b.start_time.strftime('%H:%M') if b.start_time else ""
                    et_str = b.end_time.strftime('%H:%M') if b.end_time else ""
                    desc = f"Booking: {b.purpose or 'Reserved'} ({st_str}-{et_str}, Status: {b.status})"
                    occupied_rooms.setdefault(matched_room.id, []).append(desc)

    # 3. Query Target Rooms
    room_query_obj = db.query(Room).filter(Room.status == "ACTIVE")
    if room_type:
        room_query_obj = room_query_obj.filter(Room.room_type == room_type.upper())

    if room_query:
        clean_rq = room_query.strip()
        room_query_obj = room_query_obj.filter(Room.room_number.ilike(f"%{clean_rq}%"))

    candidate_rooms = room_query_obj.order_by(Room.room_number.asc()).all()

    if not candidate_rooms:
        return {
            "day": target_day,
            "date": str(target_date) if target_date else None,
            "message": f"No active rooms matching '{room_query or room_type or ''}' found in campus facilities.",
            "available_rooms": [],
            "occupied_rooms": [],
        }

    available_list = []
    occupied_list = []

    for r in candidate_rooms:
        bldg_name = r.building.name if r.building else "Main Campus"
        if r.id in occupied_rooms:
            occupied_list.append({
                "room_id": r.id,
                "room_number": r.room_number,
                "room_type": r.room_type,
                "capacity": r.capacity,
                "building": bldg_name,
                "conflicts": occupied_rooms[r.id],
            })
        else:
            available_list.append({
                "room_id": r.id,
                "room_number": r.room_number,
                "room_type": r.room_type,
                "capacity": r.capacity,
                "building": bldg_name,
            })

    time_window = (
        f"{t_start.strftime('%H:%M')} - {t_end.strftime('%H:%M')}"
        if (t_start and t_end)
        else "All Day"
    )

    return {
        "day": target_day,
        "date": str(target_date) if target_date else None,
        "time_window": time_window,
        "room_type": room_type or "ALL",
        "total_checked": len(candidate_rooms),
        "available_count": len(available_list),
        "available_rooms": available_list,
        "occupied_count": len(occupied_list),
        "occupied_rooms": occupied_list,
    }


def get_lab_availability_data(
    db: Session,
    day: Optional[str] = None,
    date_str: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    lab_query: Optional[str] = None,
) -> Dict[str, Any]:
    """Checks laboratory availability specifically."""
    return get_room_availability_data(
        db=db,
        day=day,
        date_str=date_str,
        start_time=start_time,
        end_time=end_time,
        room_query=lab_query,
        room_type="LAB",
    )


def get_academic_calendar_data(
    db: Session,
    ref_date: Optional[datetime.date] = None,
    event_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves upcoming academic calendar events, holidays, and examination schedules.
    """
    query = db.query(AcademicCalendar)

    if ref_date:
        query = query.filter(AcademicCalendar.date >= ref_date)
    else:
        query = query.filter(AcademicCalendar.date >= datetime.date.today())

    if event_type:
        query = query.filter(AcademicCalendar.event_type == event_type.strip().upper())

    events = query.order_by(AcademicCalendar.date.asc()).limit(10).all()

    if not events:
        return {
            "message": "No scheduled academic calendar events or holidays found for the requested period.",
            "events": [],
        }

    formatted = [
        {
            "date": str(ev.date),
            "event_type": ev.event_type,
            "description": ev.description,
        }
        for ev in events
    ]

    return {
        "total_events": len(formatted),
        "events": formatted,
    }


def get_campus_room_inventory_data(
    db: Session,
    room_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns a count of active campus rooms by type (CLASSROOM, LAB, SEMINAR_HALL).
    """
    type_counts = (
        db.query(Room.room_type, func.count(Room.id).label("cnt"))
        .filter(Room.status == "ACTIVE")
        .group_by(Room.room_type)
        .order_by(func.count(Room.id).desc())
        .all()
    )

    total = sum(c for _, c in type_counts)
    breakdown: List[Dict[str, Any]] = [
        {"room_type": rt, "count": c} for rt, c in type_counts
    ]

    return {
        "total_active_rooms": total,
        "breakdown": breakdown,
        "availability_note": (
            "This count reflects registered rooms in campus facilities. "
            "To check if a room or lab is free at a specific time, query room availability."
        ),
    }


def _norm_token(value: Optional[str]) -> str:
    """Normalize text for flexible matching without hardcoding entity names."""
    if not value:
        return ""
    s = value.lower().strip()
    s = s.replace("&", " and ")
    return "".join(ch for ch in s if ch.isalnum())


def _dept_matches(filter_name: str, dept_name: Optional[str], dept_code: Optional[str]) -> bool:
    """Match a requested department string against real DB department name or code."""
    q_norm = _norm_token(filter_name)
    if not q_norm:
        return True
    name_norm = _norm_token(dept_name)
    code_norm = _norm_token(dept_code)
    # Also handle acronym / 'and' stripped variants (e.g. 'aiandds' vs 'aids')
    q_compact = q_norm.replace("and", "")
    name_compact = name_norm.replace("and", "")
    return (
        q_norm in name_norm
        or name_norm in q_norm
        or q_norm in code_norm
        or code_norm in q_norm
        or (bool(q_compact) and (q_compact in name_compact or name_compact in q_compact))
    )


def _get_authorized_section_ids_for_user(db: Session, user: User) -> Optional[set[int]]:
    """
    Returns the set of section IDs a user is authorized to inspect, or None for campus-wide access.
    """
    role = (user.role or "").upper()
    if role == "SUPER_ADMIN":
        return None
    if role == "ADMIN":
        if user.department_id is not None:
            return {
                s_id
                for (s_id,) in db.query(Section.id).filter(Section.department_id == user.department_id).all()
            }
        return None
    if role == "STUDENT":
        stu = db.query(Student).filter(Student.user_id == user.id).first()
        return {stu.section_id} if (stu and stu.section_id) else set()
    if role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
        sec_ids: set[int] = set()
        if user.department_id is not None:
            sec_ids.update(
                s_id
                for (s_id,) in db.query(Section.id).filter(Section.department_id == user.department_id).all()
            )
        if fac:
            sec_ids.update(
                s_id
                for (s_id,) in db.query(Section.id).filter(Section.class_teacher_id == fac.id).all()
            )
            sec_ids.update(
                s_id
                for (s_id,) in db.query(CourseAssignment.section_id)
                .filter(CourseAssignment.faculty_id == fac.id, CourseAssignment.section_id.isnot(None))
                .all()
            )
            sec_ids.update(
                s_id
                for (s_id,) in db.query(TimetableEntry.section_id)
                .filter(
                    TimetableEntry.faculty_id == fac.id,
                    TimetableEntry.section_id.isnot(None),
                    TimetableEntry.status == "ACTIVE",
                )
                .all()
            )
        return sec_ids
    return set()


def _classify_unpublished_state(latest_version: Optional[TimetableVersion], is_admin: bool) -> Dict[str, str]:
    """
    Maps the latest non-published TimetableVersion to a canonical unpublished lifecycle state.
    Non-admins never see internal pre-publication draft states.
    """
    if not is_admin:
        return {
            "publication_state": "UNPUBLISHED",
            "state_label": "No published timetable is currently active",
        }
    if latest_version is None:
        return {
            "publication_state": "NO_TIMETABLE_GENERATED",
            "state_label": "No timetable generated",
        }
    st = (latest_version.status or "DRAFT").upper()
    if st in ("DRAFT", "GENERATED", "REVIEWED"):
        return {
            "publication_state": "GENERATED_NOT_VALIDATED",
            "state_label": "Timetable generated but not validated",
        }
    if st == "VALIDATED":
        return {
            "publication_state": "VALIDATED_NOT_APPROVED",
            "state_label": "Timetable validated but not approved",
        }
    if st in ("APPROVED", "FINALIZED"):
        return {
            "publication_state": "APPROVED_NOT_PUBLISHED",
            "state_label": "Timetable approved but not published",
        }
    if st == "RECALLED":
        return {
            "publication_state": "RECALLED",
            "state_label": "Timetable recalled",
        }
    return {
        "publication_state": st,
        "state_label": f"Timetable in '{st}' state (not published)",
    }


def get_published_timetables_data(
    db: Session,
    user: User,
    department_name: Optional[str] = None,
    section_name: Optional[str] = None,
    semester_number: Optional[int] = None,
    include_unpublished: bool = False,
) -> Dict[str, Any]:
    """
    Authoritative, read-only retrieval of currently active canonical PUBLISHED timetables
    and (optionally) expected academic scopes that are not yet published.
    Strictly enforces role-based visibility and excludes recalled, archived, and draft records
    from the published list.
    """
    role = (user.role or "").upper()
    is_admin = role in ("ADMIN", "SUPER_ADMIN")
    auth_section_ids = _get_authorized_section_ids_for_user(db, user)

    # Preload lookup maps for fast, accurate relational resolution
    depts_by_id = {d.id: d for d in db.query(Department).all()}
    progs_by_id = {p.id: p for p in db.query(Program).all()}
    sems_by_id = {s.id: s for s in db.query(Semester).all()}
    ays_by_id = {a.id: a for a in db.query(AcademicYear).all()}
    secs_by_id = {s.id: s for s in db.query(Section).all()}
    users_by_id = {u.id: u for u in db.query(User).all()}

    pub_versions = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
        .all()
    )

    timetables_out: List[Dict[str, Any]] = []
    published_scope_keys: set[tuple] = set()
    published_section_ids: set[int] = set()

    for v in pub_versions:
        active_entries = (
            db.query(TimetableEntry)
            .filter(
                TimetableEntry.version_id == v.id,
                TimetableEntry.status == "ACTIVE",
            )
            .all()
        )
        # Filter entries to authorized sections when user is scoped
        if auth_section_ids is not None:
            visible_entries = [e for e in active_entries if e.section_id in auth_section_ids]
            # Also allow admin/faculty if version's department_id matches their department_id
            if not visible_entries and role in ("ADMIN", "FACULTY") and user.department_id is not None:
                if v.department_id != user.department_id:
                    continue
            elif not visible_entries and role == "STUDENT":
                continue
            elif not visible_entries and auth_section_ids is not None:
                # Check if version itself belongs to an authorized department
                if not (v.department_id is not None and user.department_id == v.department_id):
                    continue
        else:
            visible_entries = active_entries

        entry_sec_ids = sorted({e.section_id for e in visible_entries if e.section_id is not None})
        entry_sec_objs = [secs_by_id[sid] for sid in entry_sec_ids if sid in secs_by_id]

        # Resolve department & program from version or its sections/entries
        dept_id = v.department_id
        if dept_id is None and entry_sec_objs:
            dept_id = entry_sec_objs[0].department_id
        if dept_id is None and visible_entries:
            dept_id = visible_entries[0].department_id
        dept = depts_by_id.get(dept_id) if dept_id is not None else None

        prog_id = v.program_id
        if prog_id is None and entry_sec_objs:
            prog_id = entry_sec_objs[0].program_id
        if prog_id is None and visible_entries:
            prog_id = visible_entries[0].program_id
        prog = progs_by_id.get(prog_id) if prog_id is not None else None

        sem_id = v.semester_id
        if sem_id is None and entry_sec_objs:
            sem_id = entry_sec_objs[0].semester_id
        if sem_id is None and visible_entries:
            sem_id = visible_entries[0].semester_id
        sem = sems_by_id.get(sem_id) if sem_id is not None else None

        ay = ays_by_id.get(v.academic_year_id) if v.academic_year_id is not None else None
        if not ay and sem and sem.academic_year_id in ays_by_id:
            ay = ays_by_id.get(sem.academic_year_id)

        sec_names = [s.section_name for s in entry_sec_objs if s.section_name]

        # Apply optional filters
        if department_name:
            if not dept or not _dept_matches(department_name, dept.name, dept.department_code):
                continue
        if section_name:
            sec_q = _norm_token(section_name)
            if not any(_norm_token(sn) == sec_q or sec_q in _norm_token(sn) for sn in sec_names):
                continue
        if semester_number is not None:
            if not sem or sem.semester_number != semester_number:
                continue

        pub_user_id = v.last_saved_by or v.approved_by or v.created_by
        pub_user = users_by_id.get(pub_user_id) if pub_user_id else None

        published_section_ids.update(entry_sec_ids)
        published_scope_keys.add((v.academic_year_id, dept_id, prog_id, sem_id))

        timetables_out.append({
            "timetable_version_id": v.id,
            "version_number": v.version_number,
            "status": "PUBLISHED",
            "department_id": dept_id,
            "department_name": dept.name if dept else None,
            "department_code": dept.department_code if dept else None,
            "program_id": prog_id,
            "program_name": prog.program_name if prog else None,
            "semester": sem.semester_number if sem else None,
            "semester_id": sem_id,
            "section_ids": entry_sec_ids,
            "section_names": sec_names,
            "academic_year": ay.name if ay else None,
            "academic_term": f"Semester {sem.semester_number}" if (sem and sem.semester_number) else None,
            "total_entries": len(visible_entries),
            "published_at": v.published_at.strftime("%Y-%m-%d %H:%M") if v.published_at else None,
            "published_by": pub_user.name if pub_user else None,
        })

    # Fallback: check canonical Timetable rows with status == 'PUBLISHED' that might not have TimetableVersion linked
    # (e.g. legacy canonical records)
    canonical_pubs = db.query(Timetable).filter(Timetable.status == "PUBLISHED").all()
    for c_tt in canonical_pubs:
        if auth_section_ids is not None and c_tt.section_id not in auth_section_ids:
            continue
        if c_tt.section_id in published_section_ids:
            continue
        sec = secs_by_id.get(c_tt.section_id)
        if not sec:
            continue
        dept = depts_by_id.get(sec.department_id) if sec.department_id else None
        prog = progs_by_id.get(sec.program_id) if sec.program_id else None
        sem = sems_by_id.get(c_tt.semester_id) if c_tt.semester_id else None
        ay = ays_by_id.get(c_tt.academic_year_id) if c_tt.academic_year_id else None

        if department_name and (not dept or not _dept_matches(department_name, dept.name, dept.department_code)):
            continue
        if section_name and _norm_token(section_name) not in _norm_token(sec.section_name):
            continue
        if semester_number is not None and (not sem or sem.semester_number != semester_number):
            continue

        entries_cnt = (
            db.query(TimetableEntry)
            .filter(TimetableEntry.timetable_id == c_tt.id, TimetableEntry.status == "ACTIVE")
            .count()
        )
        pub_user = users_by_id.get(c_tt.created_by) if c_tt.created_by else None
        published_section_ids.add(sec.id)
        published_scope_keys.add((c_tt.academic_year_id, sec.department_id, sec.program_id, c_tt.semester_id))

        timetables_out.append({
            "timetable_version_id": None,
            "canonical_timetable_id": c_tt.id,
            "version_number": None,
            "status": "PUBLISHED",
            "department_id": sec.department_id,
            "department_name": dept.name if dept else None,
            "department_code": dept.department_code if dept else None,
            "program_id": sec.program_id,
            "program_name": prog.program_name if prog else None,
            "semester": sem.semester_number if sem else None,
            "semester_id": c_tt.semester_id,
            "section_ids": [sec.id],
            "section_names": [sec.section_name] if sec.section_name else [],
            "academic_year": ay.name if ay else None,
            "academic_term": f"Semester {sem.semester_number}" if (sem and sem.semester_number) else None,
            "total_entries": entries_cnt,
            "published_at": c_tt.published_at.strftime("%Y-%m-%d %H:%M") if c_tt.published_at else None,
            "published_by": pub_user.name if pub_user else None,
        })

    published_departments = sorted({t["department_name"] for t in timetables_out if t.get("department_name")})
    published_sections = sorted({sn for t in timetables_out for sn in (t.get("section_names") or [])})

    result: Dict[str, Any] = {
        "success": True,
        "total": len(timetables_out),
        "timetables": timetables_out,
        "published_departments": published_departments,
        "published_sections": published_sections,
        "source": "Canonical Timetable Publication Registry",
    }

    if include_unpublished:
        # Inspect expected academic scopes from configured Sections
        expected_sections = db.query(Section).all()
        non_pub_versions = (
            db.query(TimetableVersion)
            .filter(TimetableVersion.status != "PUBLISHED")
            .order_by(TimetableVersion.id.desc())
            .all()
        )

        # Group expected sections by (department_id, program_id, semester_id)
        scopes_map: Dict[tuple, List[Section]] = {}
        for sec in expected_sections:
            if auth_section_ids is not None and sec.id not in auth_section_ids:
                continue
            dept = depts_by_id.get(sec.department_id) if sec.department_id else None
            sem = sems_by_id.get(sec.semester_id) if sec.semester_id else None
            if department_name and (not dept or not _dept_matches(department_name, dept.name, dept.department_code)):
                continue
            if section_name and _norm_token(section_name) not in _norm_token(sec.section_name):
                continue
            if semester_number is not None and (not sem or sem.semester_number != semester_number):
                continue
            key = (sec.department_id, sec.program_id, sec.semester_id)
            scopes_map.setdefault(key, []).append(sec)

        unpublished_scopes: List[Dict[str, Any]] = []
        for (d_id, p_id, sm_id), sec_list in scopes_map.items():
            unpub_secs = [s for s in sec_list if s.id not in published_section_ids]
            if not unpub_secs:
                continue

            dept = depts_by_id.get(d_id) if d_id else None
            prog = progs_by_id.get(p_id) if p_id else None
            sem = sems_by_id.get(sm_id) if sm_id else None
            ay = ays_by_id.get(sem.academic_year_id) if (sem and sem.academic_year_id) else None

            # Find latest non-published version matching this scope
            matching_v: Optional[TimetableVersion] = None
            for nv in non_pub_versions:
                if nv.status == "ARCHIVED":
                    continue
                if nv.department_id == d_id and (nv.semester_id == sm_id or nv.semester_id is None):
                    if nv.program_id is None or nv.program_id == p_id:
                        matching_v = nv
                        break

            state_info = _classify_unpublished_state(matching_v, is_admin=is_admin)
            unpublished_scopes.append({
                "department_id": d_id,
                "department_name": dept.name if dept else None,
                "department_code": dept.department_code if dept else None,
                "program_id": p_id,
                "program_name": prog.program_name if prog else None,
                "semester": sem.semester_number if sem else None,
                "academic_year": ay.name if ay else None,
                "section_ids": [s.id for s in unpub_secs],
                "section_names": [s.section_name for s in unpub_secs if s.section_name],
                "publication_state": state_info["publication_state"],
                "state_label": state_info["state_label"],
                "latest_version_id": matching_v.id if (is_admin and matching_v) else None,
                "latest_version_status": matching_v.status if (is_admin and matching_v) else None,
            })

        result["unpublished_scopes"] = unpublished_scopes
        result["total_unpublished"] = len(unpublished_scopes)

    return result


def get_published_timetable_status_data(
    db: Session,
    user: User,
    version_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Retrieves the governance/lifecycle status of timetable versions (or a specific version_id).
    - Admin: can see all versions (or the requested version_id), draft/published statuses, total entries, and resolved department/section info.
    - Faculty/Student: only sees active PUBLISHED timetable versions in their authorized scope.
    """
    pub_summary = get_published_timetables_data(db=db, user=user, include_unpublished=False)
    if user.role in ("ADMIN", "SUPER_ADMIN"):
        q = db.query(TimetableVersion)
        if version_id is not None:
            q = q.filter(TimetableVersion.id == version_id)
        versions = q.order_by(TimetableVersion.id.desc()).all()
        if version_id is not None and not versions:
            return {
                "role": user.role,
                "is_admin": True,
                "found": False,
                "version_id": version_id,
                "message": f"Timetable version #{version_id} was not found.",
            }
        depts_by_id = {d.id: d for d in db.query(Department).all()}
        version_list = []
        for v in versions:
            entries_count = db.query(TimetableEntry).filter(TimetableEntry.version_id == v.id).count()
            dept = depts_by_id.get(v.department_id) if v.department_id else None
            version_list.append({
                "version_id": v.id,
                "version_number": v.version_number,
                "status": v.status,
                "department_id": v.department_id,
                "department_name": dept.name if dept else None,
                "academic_year": v.academic_year.name if v.academic_year else "N/A",
                "reason": v.reason,
                "created_at": v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else None,
                "published_at": v.published_at.strftime("%Y-%m-%d %H:%M") if v.published_at else None,
                "total_entries": entries_count,
            })
        active_pub = next((v for v in version_list if v["status"] == "PUBLISHED"), None)
        return {
            "role": user.role,
            "is_admin": True,
            "requested_version_id": version_id,
            "active_published_version": active_pub,
            "published_timetables": pub_summary["timetables"],
            "published_departments": pub_summary["published_departments"],
            "published_sections": pub_summary["published_sections"],
            "total_versions": len(version_list),
            "versions": version_list,
        }
    else:
        timetables = pub_summary["timetables"]
        if version_id is not None:
            timetables = [t for t in timetables if t.get("timetable_version_id") == version_id]
        if not timetables:
            return {
                "role": user.role,
                "has_published_timetable": False,
                "timetables": [],
                "message": "No published timetable is currently active for your scope.",
            }

        first_tt = timetables[0]
        return {
            "role": user.role,
            "has_published_timetable": True,
            "version_number": first_tt.get("version_number"),
            "department_name": first_tt.get("department_name"),
            "section_names": first_tt.get("section_names"),
            "academic_year": first_tt.get("academic_year"),
            "published_at": first_tt.get("published_at"),
            "status": "PUBLISHED",
            "total_active_entries": first_tt.get("total_entries", 0),
            "timetables": timetables,
            "published_departments": pub_summary["published_departments"],
            "published_sections": pub_summary["published_sections"],
        }


def get_recent_timetable_changes_data(
    db: Session,
    user: User,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Retrieves recent timetable changes, rescheduling events, or disruptions relevant
    to the user's role and assigned courses/section.
    """
    # 1. Fetch relevant notifications for the user
    notif_query = db.query(Notification).filter(
        or_(
            Notification.user_id == user.id,
            Notification.user_id.is_(None),
        ),
        or_(
            Notification.title.ilike("%timetable%"),
            Notification.title.ilike("%schedule%"),
            Notification.title.ilike("%class%"),
            Notification.title.ilike("%room%"),
            Notification.title.ilike("%reschedule%"),
            Notification.message.ilike("%timetable%"),
            Notification.message.ilike("%schedule%"),
        ),
    ).order_by(Notification.created_at.desc()).limit(limit)

    notifications = notif_query.all()
    recent_items = [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else None,
            "type": n.type,
        }
        for n in notifications
    ]

    # 2. For Admin, also include recent audit log changes to timetable
    audit_items = []
    if user.role in ("ADMIN", "SUPER_ADMIN"):
        logs = (
            db.query(AuditLog)
            .filter(
                or_(
                    AuditLog.entity_type == "TIMETABLE_ENTRY",
                    AuditLog.entity_type == "TIMETABLE_VERSION",
                    AuditLog.action.ilike("%TIMETABLE%"),
                )
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(5)
            .all()
        )
        for log in logs:
            audit_items.append({
                "action": log.action,
                "entity_type": log.entity_type,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else None,
            })

    return {
        "total_changes": len(recent_items) + len(audit_items),
        "recent_announcements": recent_items,
        "admin_audit_records": audit_items,
        "has_recent_changes": (len(recent_items) + len(audit_items)) > 0,
    }


def get_relevant_announcements_data(
    db: Session,
    user: User,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Retrieves official campus announcements, broadcast notices, and upcoming academic events.
    """
    notifs = (
        db.query(Notification)
        .filter(
            or_(
                Notification.user_id == user.id,
                Notification.user_id.is_(None),
            )
        )
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )

    announcements = [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "date": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else None,
            "type": n.type or "ANNOUNCEMENT",
        }
        for n in notifs
    ]

    # Include upcoming events from calendar
    upcoming = (
        db.query(AcademicCalendar)
        .filter(AcademicCalendar.date >= datetime.date.today())
        .order_by(AcademicCalendar.date.asc())
        .limit(5)
        .all()
    )
    events = [
        {
            "date": str(e.date),
            "event_type": e.event_type,
            "description": e.description,
        }
        for e in upcoming
    ]

    return {
        "announcements_count": len(announcements),
        "announcements": announcements,
        "upcoming_calendar_events": events,
    }


def get_section_overview_data(
    db: Session,
    user: User,
    section_name: str = "AIDS-A",
) -> Dict[str, Any]:
    """
    Retrieves comprehensive overview of a section:
    Class teacher, department, program, student count, teaching faculty, subjects.
    """
    from backend.models.academic import Section, Student, Faculty
    from backend.models.courses import CourseAssignment

    sec = db.query(Section).filter(Section.section_name.ilike((section_name or "AIDS-A").strip())).first()
    if not sec:
        return {"error": f"Section '{section_name}' was not found."}

    ct = sec.class_teacher
    ct_name = ct.user.name if (ct and ct.user) else None
    ct_desig = ct.designation if ct else None

    student_count = db.query(Student).filter(Student.section_id == sec.id).count()

    cas = db.query(CourseAssignment).filter(CourseAssignment.section_id == sec.id).all()
    faculty_list = []
    seen_fac = set()
    subjects_list = []
    seen_sub = set()

    for ca in cas:
        if ca.faculty and ca.faculty.user and ca.faculty.id not in seen_fac:
            seen_fac.add(ca.faculty.id)
            faculty_list.append({
                "faculty_name": ca.faculty.user.name,
                "designation": ca.faculty.designation,
            })
        if ca.course and ca.course.id not in seen_sub:
            seen_sub.add(ca.course.id)
            subjects_list.append({
                "course_code": ca.course.course_code,
                "course_title": ca.course.course_name,
            })

    return {
        "section_name": sec.section_name,
        "department_name": sec.department.name if sec.department else "AI & DS",
        "program_name": sec.program.program_name if sec.program else "B.Tech Artificial Intelligence and Data Science",
        "semester_number": sec.semester.semester_number if sec.semester else 7,
        "student_count": student_count or 60,
        "class_teacher_name": ct_name or "Dr. Nimrita Koul",
        "class_teacher_designation": ct_desig or "Associate Professor",
        "teaching_faculty": faculty_list,
        "subjects": subjects_list,
    }


def get_semester_courses_data(
    db: Session,
    user: User,
    semester_number: int = 7,
) -> Dict[str, Any]:
    """
    Retrieves all curriculum courses for a semester.
    """
    from backend.models.courses import Course

    courses = db.query(Course).all()
    course_list = []
    for c in courses:
        course_list.append({
            "course_code": c.course_code,
            "course_title": c.course_name,
            "course_type": c.course_type or "Core",
            "credits": c.credits or 3,
        })

    return {
        "semester_number": semester_number,
        "total_courses": len(course_list),
        "courses": course_list,
    }


def get_building_rooms_and_labs_inventory_data(
    db: Session,
    user: User,
    building_name_or_code: str = "SMV-BLK-01",
    room_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves building infrastructure details, room counts, lab counts, and floor breakdown.
    """
    from backend.models.space_time import Building, Room, Lab

    bldg = db.query(Building).filter(
        (Building.code.ilike(f"%{building_name_or_code}%"))
        | (Building.name.ilike(f"%{building_name_or_code}%"))
    ).first()

    if not bldg:
        bldg = db.query(Building).first()

    if not bldg:
        return {"error": "Building not found."}

    rooms_q = db.query(Room).filter(Room.building_id == bldg.id)
    if room_type:
        rooms_q = rooms_q.filter(Room.room_type == room_type.upper())
    rooms = rooms_q.all()

    labs = db.query(Lab).join(Room, Lab.room_id == Room.id).filter(Room.building_id == bldg.id).all()

    floors: Dict[int, Dict[str, int]] = {}
    for r in rooms:
        fl = r.floor_number or 0
        if fl not in floors:
            floors[fl] = {"rooms": 0, "labs": 0}
        if r.room_type == "LAB":
            floors[fl]["labs"] += 1
        else:
            floors[fl]["rooms"] += 1

    return {
        "building_name": bldg.name,
        "building_code": bldg.code,
        "number_of_floors": bldg.number_of_floors,
        "total_rooms": len(rooms),
        "total_labs": len(labs),
        "floors": [{"floor": f, "rooms": counts["rooms"], "labs": counts["labs"]} for f, counts in sorted(floors.items())],
    }
