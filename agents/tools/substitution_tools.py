"""
agents/tools/substitution_tools.py
----------------------------------
Authoritative LangGraph agent tools for Faculty Substitution:
- Checking upcoming scheduled classes and substitution status
- Inspecting submitted unavailability requests and assigned substitute duties
- Review queue inspection for Admins and Substitution Coordinators
- Checking date-specific substituted faculty for students and faculty
- Strictly grounded in PostgreSQL records; enforces role-based privacy barriers
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session, joinedload

from backend.models.academic import Faculty, Student
from backend.models.identity import User
from backend.models.space_time import Room, TimeSlot
from backend.models.substitution import FacultySubstitution
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.services.event_service import check_user_has_capability
from backend.services.substitution_service import (
    day_matches_date,
    get_active_substitutions_for_date,
    list_faculty_upcoming_classes,
)


def _parse_date(val: Any) -> Optional[datetime.date]:
    if not val:
        return None
    if isinstance(val, datetime.date):
        return val
    if isinstance(val, datetime.datetime):
        return val.date()
    val_str = str(val).strip()
    if val_str.upper() == "TODAY":
        return datetime.date.today()
    if val_str.upper() == "TOMORROW":
        return datetime.date.today() + datetime.timedelta(days=1)
    try:
        return datetime.date.fromisoformat(val_str)
    except Exception:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(val_str, fmt).date()
            except ValueError:
                continue
    return None


def list_my_substitution_requests_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Returns substitution requests submitted by or concerning the authenticated faculty member.
    """
    if user.role not in ("FACULTY", "ADMIN"):
        return {
            "error": "Only faculty members and administrators can inspect substitution requests.",
            "requests": [],
        }

    query = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
        )
    )

    if user.role != "ADMIN":
        fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
        if not fac:
            return {"requests": [], "total": 0}
        query = query.filter(FacultySubstitution.original_faculty_id == fac.id)

    subs = query.order_by(FacultySubstitution.substitution_date.desc(), FacultySubstitution.id.desc()).all()

    requests_list = []
    for s in subs:
        entry = s.timetable_entry
        course_str = entry.course.course_code if (entry and entry.course) else "N/A"
        sub_name = s.substitute_faculty.user.name if (s.substitute_faculty and s.substitute_faculty.user) else None
        slot_time = ""
        if entry and entry.slot and entry.slot.start_time:
            slot_time = f"{entry.slot.start_time.strftime('%H:%M')} - {entry.slot.end_time.strftime('%H:%M') if entry.slot.end_time else ''}"

        requests_list.append({
            "id": s.id,
            "substitution_date": s.substitution_date.isoformat(),
            "course": course_str,
            "slot_time": slot_time,
            "status": s.status,
            "substitute_faculty": sub_name,
            "reason": s.reason,
            "rejection_reason": s.rejection_reason,
        })

    return {
        "total": len(requests_list),
        "requests": requests_list,
    }


def list_my_substitution_assignments_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Returns classes where the authenticated faculty member is assigned as the substitute teacher.
    """
    if user.role != "FACULTY":
        return {
            "error": "Only faculty members have substitute teaching assignments.",
            "assignments": [],
        }

    fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
    if not fac:
        return {"assignments": [], "total": 0}

    subs = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
        )
        .filter(
            FacultySubstitution.substitute_faculty_id == fac.id,
            FacultySubstitution.status == "APPROVED",
        )
        .order_by(FacultySubstitution.substitution_date.asc())
        .all()
    )

    assignments_list = []
    for s in subs:
        entry = s.timetable_entry
        course_code = entry.course.course_code if (entry and entry.course) else "N/A"
        course_name = entry.course.course_name if (entry and entry.course) else ""
        orig_name = s.original_faculty.user.name if (s.original_faculty and s.original_faculty.user) else "Regular Faculty"
        room_name = entry.room.room_number if (entry and entry.room) else "N/A"
        slot_time = ""
        if entry and entry.slot and entry.slot.start_time:
            slot_time = f"{entry.slot.start_time.strftime('%H:%M')} - {entry.slot.end_time.strftime('%H:%M') if entry.slot.end_time else ''}"

        assignments_list.append({
            "id": s.id,
            "substitution_date": s.substitution_date.isoformat(),
            "course_code": course_code,
            "course_name": course_name,
            "covering_for": orig_name,
            "room": room_name,
            "time": slot_time,
            "status": s.status,
        })

    return {
        "total": len(assignments_list),
        "assignments": assignments_list,
    }


def list_pending_substitutions_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Lists pending substitution requests awaiting approval for Admins and Reviewers.
    """
    is_admin = user.role == "ADMIN"
    has_cap = (
        check_user_has_capability(db, user, "SUBSTITUTION_COORDINATOR")
        or check_user_has_capability(db, user, "SUBSTITUTION_REVIEWER")
    )
    if not (is_admin or has_cap):
        return {
            "error": "Access denied: You lack administrative or substitution coordinator capabilities.",
            "pending_requests": [],
        }

    subs = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
        )
        .filter(FacultySubstitution.status.in_(["REQUESTED", "PROPOSED"]))
        .order_by(FacultySubstitution.substitution_date.asc(), FacultySubstitution.id.asc())
        .all()
    )

    pending_list = []
    for s in subs:
        entry = s.timetable_entry
        course_str = entry.course.course_code if (entry and entry.course) else "N/A"
        orig_name = s.original_faculty.user.name if (s.original_faculty and s.original_faculty.user) else "Unknown"
        slot_time = ""
        if entry and entry.slot and entry.slot.start_time:
            slot_time = f"{entry.slot.start_time.strftime('%H:%M')} - {entry.slot.end_time.strftime('%H:%M') if entry.slot.end_time else ''}"

        pending_list.append({
            "id": s.id,
            "substitution_date": s.substitution_date.isoformat(),
            "course": course_str,
            "faculty": orig_name,
            "time": slot_time,
            "reason": s.reason,
            "status": s.status,
            "version": s.version,
        })

    return {
        "total": len(pending_list),
        "pending_requests": pending_list,
    }


def get_date_substitutions_data(
    db: Session,
    user: User,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Checks active faculty substitutions for a given date.
    Protects private absence reasons from student inquiries.
    """
    target_date = _parse_date(date) or datetime.date.today()
    sub_map = get_active_substitutions_for_date(db, target_date)

    if not sub_map:
        return {
            "date": target_date.isoformat(),
            "total_substitutions": 0,
            "message": f"No faculty substitutions are active for {target_date}.",
            "substitutions": [],
        }

    subs = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
        )
        .filter(
            FacultySubstitution.substitution_date == target_date,
            FacultySubstitution.status == "APPROVED",
        )
        .all()
    )

    items = []
    for s in subs:
        entry = s.timetable_entry
        course_code = entry.course.course_code if (entry and entry.course) else "N/A"
        course_name = entry.course.course_name if (entry and entry.course) else ""
        orig_name = s.original_faculty.user.name if (s.original_faculty and s.original_faculty.user) else "Regular Faculty"
        sub_name = s.substitute_faculty.user.name if (s.substitute_faculty and s.substitute_faculty.user) else "Substitute Faculty"
        room_name = entry.room.room_number if (entry and entry.room) else "N/A"
        time_str = ""
        if entry and entry.slot and entry.slot.start_time:
            time_str = f"{entry.slot.start_time.strftime('%H:%M')} - {entry.slot.end_time.strftime('%H:%M') if entry.slot.end_time else ''}"

        item = {
            "id": s.id,
            "course_code": course_code,
            "course_name": course_name,
            "original_faculty": orig_name,
            "substitute_faculty": sub_name,
            "room": room_name,
            "time": time_str,
            "status": "APPROVED",
        }
        # Enforce privacy: never include s.reason for student callers
        if user.role != "STUDENT":
            item["reason"] = s.reason

        items.append(item)

    return {
        "date": target_date.isoformat(),
        "total_substitutions": len(items),
        "substitutions": items,
    }

