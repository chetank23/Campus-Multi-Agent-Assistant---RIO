"""
agents/tools/faculty_tools.py
-----------------------------
Safe, read-only tools for Faculty schedule retrieval and academic directory lookups.
Masks sensitive private fields and enforces strict role boundaries.
"""

from __future__ import annotations

from datetime import date, datetime as dt, time
import datetime
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.academic import Department, Faculty, Section
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.space_time import Room, TimeSlot, FacultyAvailability
from backend.models.timetable import TimetableEntry, TimetableVersion


def _normalize_day(day_input: Optional[str]) -> Optional[str]:
    if not day_input:
        return None
    d = day_input.strip().upper()
    if d == "TODAY":
        return datetime.date.today().strftime("%A").upper()
    if d == "TOMORROW":
        return (datetime.date.today() + datetime.timedelta(days=1)).strftime("%A").upper()

    day_map = {
        "MON": "MONDAY", "MONDAY": "MONDAY",
        "TUE": "TUESDAY", "TUESDAY": "TUESDAY",
        "WED": "WEDNESDAY", "WEDNESDAY": "WEDNESDAY",
        "THU": "THURSDAY", "THURSDAY": "THURSDAY",
        "FRI": "FRIDAY", "FRIDAY": "FRIDAY",
        "SAT": "SATURDAY", "SATURDAY": "SATURDAY",
        "SUN": "SUNDAY", "SUNDAY": "SUNDAY",
    }
    return day_map.get(d, d)


def get_faculty_schedule_data(
    db: Session,
    user: User,
    day: Optional[str] = None,
    target_faculty_id: Optional[int] = None,
    target_faculty_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves the published teaching schedule for faculty.
    - FACULTY role: returns their own teaching schedule.
      If faculty attempts to query another faculty ID, access is strictly denied.
    - ADMIN role: returns teaching schedule for target_faculty_id or target_faculty_name.
    - STUDENT role: denied (students query their own student timetable or look up directory info).
    """
    faculty: Optional[Faculty] = None

    if user.role == "FACULTY":
        own_fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
        if not own_fac:
            return {
                "error": "Faculty academic profile not found.",
                "entries": [],
            }
        # Cross-faculty privacy barrier
        if target_faculty_id is not None and target_faculty_id != own_fac.id:
            return {
                "error": "Access denied: Faculty cannot inspect other faculty members' personal schedules.",
                "entries": [],
            }
        faculty = own_fac
    elif user.role == "ADMIN":
        if target_faculty_id:
            faculty = db.query(Faculty).filter(Faculty.id == target_faculty_id).first()
        elif target_faculty_name:
            clean_name = target_faculty_name.strip()
            faculty = (
                db.query(Faculty)
                .join(User, Faculty.user_id == User.id)
                .filter(User.name.ilike(f"%{clean_name}%"))
                .first()
            )
        else:
            faculty = db.query(Faculty).first()
    else:
        return {
            "error": "Access denied. Students are not authorized to inspect personal faculty schedules.",
            "entries": [],
        }

    if not faculty:
        target_repr = target_faculty_name or (f"#{target_faculty_id}" if target_faculty_id else "Faculty")
        return {
            "error": f"Faculty academic profile '{target_repr}' not found.",
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
            "faculty_name": faculty.user.name if faculty.user else "Faculty Member",
            "message": "No published timetable is currently active.",
            "entries": [],
        }

    query = (
        db.query(TimetableEntry)
        .filter(
            TimetableEntry.version_id == published_version.id,
            TimetableEntry.faculty_id == faculty.id,
            TimetableEntry.status != "CANCELLED",
        )
    )

    norm_day = _normalize_day(day)
    if norm_day:
        query = query.join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id).filter(
            TimeSlot.day == norm_day
        )

    entries = query.all()

    day_order = {
        "MONDAY": 1, "TUESDAY": 2, "WEDNESDAY": 3,
        "THURSDAY": 4, "FRIDAY": 5, "SATURDAY": 6, "SUNDAY": 7,
    }
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

    formatted.sort(
        key=lambda x: (
            day_order.get(x["day"], 99),
            x["start_time"],
        )
    )

    return {
        "faculty_name": faculty.user.name if faculty.user else "Faculty Member",
        "faculty_id": faculty.id,
        "designation": faculty.designation or "Faculty",
        "day": norm_day or "ALL",
        "total_teaching_slots": len(formatted),
        "entries": formatted,
    }


def get_faculty_timetable_data(
    db: Session,
    user: User,
    day: Optional[str] = None,
    target_faculty_id: Optional[int] = None,
    target_faculty_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias for get_faculty_schedule_data."""
    return get_faculty_schedule_data(
        db=db,
        user=user,
        day=day,
        target_faculty_id=target_faculty_id,
        target_faculty_name=target_faculty_name,
    )


def get_faculty_profile_data(
    db: Session,
    viewer: User,
    search_query: str,
) -> Dict[str, Any]:
    """
    Looks up academic directory profile information for faculty members.
    Enforces privacy by masking phone numbers from students.
    Includes courses currently assigned to the faculty.
    """
    clean_query = search_query.strip()
    pattern = f"%{clean_query}%"
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

        # Fetch assigned courses
        assigned_courses = (
            db.query(Course)
            .join(CourseAssignment, Course.id == CourseAssignment.course_id)
            .filter(CourseAssignment.faculty_id == f.id)
            .distinct()
            .all()
        )
        course_names = [f"{c.course_code} ({c.course_name})" for c in assigned_courses]

        results.append({
            "name": u.name if u else "Faculty Member",
            "faculty_id": f.faculty_id,
            "department": dept.name if dept else "N/A",
            "designation": f.designation or "Faculty",
            "specialization": f.specialization or "N/A",
            "areas_of_interest": f.areas_of_interest or "N/A",
            "contact_number": contact,
            "courses_taught": course_names,
        })

    return {
        "count": len(results),
        "results": results,
    }


def get_faculty_information_data(
    db: Session,
    viewer: User,
    search_query: str,
) -> Dict[str, Any]:
    """Alias for get_faculty_profile_data."""
    return get_faculty_profile_data(db=db, viewer=viewer, search_query=search_query)


def get_available_faculty_data(
    db: Session,
    date: Union[str, date],
    start_time: Union[str, time],
    end_time: Union[str, time],
    department_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Identifies active faculty members who are genuinely available for a specific date and time interval.
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
                or_(TimeSlot.day == day_full, TimeSlot.day == day_3),
                TimeSlot.start_time < et,
                TimeSlot.end_time > st,
                TimetableEntry.status != "CANCELLED",
            )
            .distinct()
            .all()
        )
        for row in tt_conflicts:
            if row[0]:
                busy_faculty_ids.add(row[0])

    # 2. Declared unavailability
    unavail = (
        db.query(FacultyAvailability.faculty_id)
        .join(TimeSlot, FacultyAvailability.slot_id == TimeSlot.id)
        .filter(
            or_(TimeSlot.day == day_full, TimeSlot.day == day_3),
            TimeSlot.start_time < et,
            TimeSlot.end_time > st,
            FacultyAvailability.availability == "UNAVAILABLE",
        )
        .distinct()
        .all()
    )
    for row in unavail:
        if row[0]:
            busy_faculty_ids.add(row[0])

    # 3. Query candidate active faculty
    query = (
        db.query(Faculty)
        .join(User, Faculty.user_id == User.id)
        .filter(User.is_active.is_(True))
    )

    if department_id:
        query = query.filter(Faculty.department_id == department_id)

    all_faculties = query.all()
    available_faculties = [f for f in all_faculties if f.id not in busy_faculty_ids]

    formatted: List[Dict[str, Any]] = []
    for f in available_faculties:
        dept = db.query(Department).filter(Department.id == f.department_id).first() if f.department_id else None
        formatted.append({
            "faculty_id": f.id,
            "name": f.user.name if f.user else "Faculty",
            "department": dept.name if dept else "N/A",
            "designation": f.designation or "Faculty",
            "specialization": f.specialization or "General",
        })

    return {
        "date": str(target_date),
        "day": day_full,
        "interval": f"{st.strftime('%H:%M')} - {et.strftime('%H:%M')}",
        "total_available": len(formatted),
        "total_evaluated": len(all_faculties),
        "available_faculty": formatted,
    }
