"""
agents/tools/faculty_tools.py
-----------------------------
Safe, read-only tools for Faculty schedule retrieval and academic directory lookups.
Masks sensitive private fields and enforces role boundaries.
"""

from __future__ import annotations

from datetime import date, datetime as dt, time
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.academic import Department, Faculty, Section
from backend.models.courses import Course
from backend.models.identity import User
from backend.models.space_time import Room, TimeSlot, FacultyAvailability
from backend.models.timetable import TimetableEntry, TimetableVersion



def get_faculty_schedule_data(
    db: Session,
    user: User,
    day: Optional[str] = None,
    target_faculty_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Retrieves the published teaching schedule for faculty.
    - FACULTY role: returns their own teaching schedule.
    - ADMIN role: returns teaching schedule for target_faculty_id (or first if unspecified).
    - STUDENT role: denied (students query their own student timetable or look up directory info).
    """
    if user.role == "FACULTY":
        faculty = db.query(Faculty).filter(Faculty.user_id == user.id).first()
    elif user.role == "ADMIN" and target_faculty_id:
        faculty = db.query(Faculty).filter(Faculty.id == target_faculty_id).first()
    elif user.role == "ADMIN":
        faculty = db.query(Faculty).first()
    else:
        return {
            "error": "Access denied. Students are not authorized to inspect personal faculty schedules.",
            "entries": [],
        }

    if not faculty:
        return {
            "error": "Faculty academic profile not found.",
            "entries": [],
        }

    published_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
        .first()
    )

    if not published_version:
        return {
            "message": "No published timetable is currently active.",
            "entries": [],
        }

    query = (
        db.query(TimetableEntry)
        .filter(
            TimetableEntry.version_id == published_version.id,
            TimetableEntry.faculty_id == faculty.id,
        )
    )

    if day:
        normalized_day = day.strip().upper()
        query = query.join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id).filter(
            TimeSlot.day == normalized_day
        )

    entries = query.all()

    day_order = {"MONDAY": 1, "TUESDAY": 2, "WEDNESDAY": 3, "THURSDAY": 4, "FRIDAY": 5, "SATURDAY": 6, "SUNDAY": 7}
    formatted: List[Dict[str, Any]] = []

    for e in entries:
        slot = e.slot
        course = e.course
        room = e.room
        section = e.section
        batch = e.batch

        formatted.append({
            "day": slot.day if slot else "N/A",
            "start_time": slot.start_time.strftime("%H:%M") if (slot and slot.start_time) else "",
            "end_time": slot.end_time.strftime("%H:%M") if (slot and slot.end_time) else "",
            "course_code": course.course_code if course else "N/A",
            "course_title": course.course_name if course else "N/A",
            "room": room.room_number if room else "N/A",
            "section": section.section_name if section else "N/A",
            "batch": batch.batch_name if batch else "All",
            "status": e.status or "ACTIVE",
        })

    formatted.sort(key=lambda x: (day_order.get(x["day"], 99), x["start_time"]))

    return {
        "faculty_name": faculty.user.name if (faculty and faculty.user) else "Faculty Member",
        "faculty_id": faculty.faculty_id if faculty else "N/A",
        "designation": faculty.designation or "Faculty",
        "total_teaching_slots": len(formatted),
        "entries": formatted,
    }


def get_faculty_profile_data(
    db: Session,
    viewer: User,
    search_query: str,
) -> Dict[str, Any]:
    """
    Looks up public directory profile for faculty members.
    Masks private contact number for student viewers. Never exposes password hash or token data.
    """
    pattern = f"%{search_query.strip()}%"
    faculties = (
        db.query(Faculty)
        .join(User, Faculty.user_id == User.id)
        .filter(
            or_(
                User.name.ilike(pattern),
                Faculty.faculty_id.ilike(pattern),
                Faculty.designation.ilike(pattern),
                Faculty.specialization.ilike(pattern),
                Faculty.areas_of_interest.ilike(pattern),
            )
        )
        .limit(5)
        .all()
    )

    if not faculties:
        return {
            "message": f"No faculty profile matching '{search_query}' was found.",
            "results": [],
        }

    results: List[Dict[str, Any]] = []
    for f in faculties:
        u = f.user
        dept = db.query(Department).filter(Department.id == f.department_id).first() if f.department_id else None

        # Mask private contact info for students
        contact = f.contact_number if viewer.role in ["ADMIN", "FACULTY"] else None

        results.append({
            "name": u.name if u else "Faculty Member",
            "faculty_id": f.faculty_id,
            "department": dept.name if dept else "N/A",
            "designation": f.designation or "Faculty",
            "specialization": f.specialization or "N/A",
            "areas_of_interest": f.areas_of_interest or "N/A",
            "contact_number": contact,
        })

    return {
        "count": len(results),
        "results": results,
    }


def get_available_faculty_data(
    db: Session,
    date: Union[str, date],
    start_time: Union[str, time],
    end_time: Union[str, time],
    department_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Identifies active faculty members who are genuinely available for a specific date and time interval.
    Authoritative checks:
    1. No overlapping published timetable assignments.
    2. No UNAVAILABLE status in faculty_availability for overlapping slots.
    3. User account is active.
    """
    if isinstance(date, str):
        target_date = dt.strptime(date, "%Y-%m-%d").date()
    else:
        target_date = date

    day_full = target_date.strftime("%A").upper()
    day_3 = day_full[:3]

    if isinstance(start_time, str):
        parts = [int(p) for p in start_time.split(":")[:2]]
        st = time(parts[0], parts[1])
    else:
        st = start_time

    if isinstance(end_time, str):
        parts = [int(p) for p in end_time.split(":")[:2]]
        et = time(parts[0], parts[1])
    else:
        et = end_time

    busy_faculty_ids: set[int] = set()

    # 1. Published timetable conflicts
    published_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
        .first()
    )

    if published_version:
        tt_conflicts = (
            db.query(TimetableEntry.faculty_id)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableEntry.version_id == published_version.id,
                TimeSlot.day.in_([day_3, day_full]),
                TimeSlot.start_time < et,
                TimeSlot.end_time > st,
                TimetableEntry.faculty_id.isnot(None),
            )
            .all()
        )
        for (fid,) in tt_conflicts:
            if fid:
                busy_faculty_ids.add(fid)

    # 2. Explicit faculty availability records (UNAVAILABLE)
    fa_conflicts = (
        db.query(FacultyAvailability.faculty_id)
        .join(TimeSlot, FacultyAvailability.slot_id == TimeSlot.id)
        .filter(
            FacultyAvailability.availability == "UNAVAILABLE",
            TimeSlot.day.in_([day_3, day_full]),
            TimeSlot.start_time < et,
            TimeSlot.end_time > st,
            FacultyAvailability.faculty_id.isnot(None),
        )
        .all()
    )
    for (fid,) in fa_conflicts:
        if fid:
            busy_faculty_ids.add(fid)

    # 3. Query all active faculty
    faculty_query = (
        db.query(Faculty)
        .join(User, Faculty.user_id == User.id)
        .filter(User.is_active.is_(True))
    )
    if department_id:
        faculty_query = faculty_query.filter(Faculty.department_id == department_id)

    all_faculty = faculty_query.all()

    available_list: List[Dict[str, Any]] = []
    for f in all_faculty:
        if f.id not in busy_faculty_ids:
            dept = db.query(Department).filter(Department.id == f.department_id).first() if f.department_id else None
            available_list.append({
                "id": f.id,
                "faculty_id": f.faculty_id,
                "name": f.user.name if f.user else "Faculty Member",
                "department": dept.name if dept else "N/A",
                "designation": f.designation or "Faculty",
                "specialization": f.specialization or "N/A",
            })

    return {
        "date": target_date.isoformat(),
        "day": day_full,
        "interval": f"{st.strftime('%H:%M')} - {et.strftime('%H:%M')}",
        "total_available": len(available_list),
        "busy_count": len(busy_faculty_ids),
        "available_faculty": available_list,
    }

