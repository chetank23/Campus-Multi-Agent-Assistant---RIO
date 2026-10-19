"""
agents/tools/department_tools.py
--------------------------------
Safe, read-only tools for Department Timetable retrieval.
Enforces departmental authorization:
- ADMIN: can view any department
- FACULTY: can only view their assigned department
- STUDENT: forbidden (students are restricted to their section/batch timetable)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.academic import Department
from backend.models.identity import User
from backend.models.space_time import TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion


def get_department_timetable_data(
    db: Session,
    user: User,
    department_id: Optional[int] = None,
    day: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves the published schedule for an academic department.
    """
    if user.role == "STUDENT":
        return {
            "error": "Access denied. Students are restricted to their assigned section timetable.",
            "entries": [],
        }

    target_dept_id = department_id
    if user.role == "FACULTY":
        if not user.department_id:
            return {"error": "Faculty has no assigned department.", "entries": []}
        if target_dept_id and target_dept_id != user.department_id:
            return {
                "error": "Access denied. Faculty cannot view other departments' internal schedules.",
                "entries": [],
            }
        target_dept_id = user.department_id

    if not target_dept_id:
        dept = db.query(Department).first()
        target_dept_id = dept.id if dept else None

    if not target_dept_id:
        return {"error": "No academic department found.", "entries": []}

    dept_record = db.query(Department).filter(Department.id == target_dept_id).first()

    published_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc())
        .first()
    )

    if not published_version:
        return {
            "department_name": dept_record.name if dept_record else f"Department #{target_dept_id}",
            "department_code": dept_record.department_code if dept_record else "N/A",
            "message": "No published timetable active.",
            "total_entries": 0,
            "entries": [],
        }

    query = (
        db.query(TimetableEntry)
        .filter(
            TimetableEntry.version_id == published_version.id,
            TimetableEntry.department_id == target_dept_id,
        )
    )

    if day:
        normalized_day = day.strip().upper()
        query = query.join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id).filter(
            TimeSlot.day == normalized_day
        )

    entries = query.limit(50).all()

    formatted: List[Dict[str, Any]] = []
    for e in entries:
        slot = e.slot
        course = e.course
        fac = e.faculty
        fac_u = fac.user if fac else None
        room = e.room
        sec = e.section

        formatted.append({
            "day": slot.day if slot else "N/A",
            "start_time": slot.start_time.strftime("%H:%M") if (slot and slot.start_time) else "",
            "end_time": slot.end_time.strftime("%H:%M") if (slot and slot.end_time) else "",
            "course": course.course_code if course else "N/A",
            "section": sec.section_name if sec else "N/A",
            "faculty": fac_u.name if fac_u else "N/A",
            "room": room.room_number if room else "N/A",
        })

    return {
        "department_name": dept_record.name if dept_record else f"Department #{target_dept_id}",
        "department_code": dept_record.department_code if dept_record else "N/A",
        "total_entries": len(formatted),
        "entries": formatted,
    }
