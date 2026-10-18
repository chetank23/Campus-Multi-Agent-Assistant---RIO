"""
agents/tools/student_tools.py
-----------------------------
Safe, read-only database tools for Student schedule retrieval and real-time class status.
Enforces strict role boundaries and published-only timetable constraints.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.academic import Batch, Section, Student
from backend.models.courses import Course
from backend.models.identity import User
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion


def get_student_timetable_data(
    db: Session,
    user: User,
    day: Optional[str] = None,
    target_student_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Retrieves the published timetable for the authenticated student.
    - If user is STUDENT, uses the student's actual section and batch.
    - If user is ADMIN, can optionally query target_student_id.
    - If user is FACULTY, denied.
    """
    if user.role == "STUDENT":
        student = db.query(Student).filter(Student.user_id == user.id).first()
    elif user.role == "ADMIN" and target_student_id:
        student = db.query(Student).filter(Student.id == target_student_id).first()
    elif user.role == "ADMIN":
        # Admin querying general student timetable must specify or get first active student
        student = db.query(Student).first()
    else:
        return {
            "error": "Only students or administrators can query student timetables.",
            "entries": [],
        }

    if not student:
        return {
            "error": "Student academic profile not found. Please contact administration.",
            "entries": [],
        }

    # Only inspect the PUBLISHED timetable version
    published_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
        .first()
    )

    if not published_version:
        return {
            "message": "No published timetable is currently active for your semester.",
            "entries": [],
        }

    query = (
        db.query(TimetableEntry)
        .filter(
            TimetableEntry.version_id == published_version.id,
            TimetableEntry.section_id == student.section_id,
        )
    )

    # Filter by student's batch or general section classes
    if student.batch_id:
        query = query.filter(
            (TimetableEntry.batch_id.is_(None)) | (TimetableEntry.batch_id == student.batch_id)
        )
    else:
        query = query.filter(TimetableEntry.batch_id.is_(None))

    if day:
        normalized_day = day.strip().upper()
        query = query.join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id).filter(
            TimeSlot.day == normalized_day
        )

    entries = query.all()

    # Sort entries by day and start_time
    day_order = {"MONDAY": 1, "TUESDAY": 2, "WEDNESDAY": 3, "THURSDAY": 4, "FRIDAY": 5, "SATURDAY": 6, "SUNDAY": 7}
    
    formatted_entries: List[Dict[str, Any]] = []
    for e in entries:
        slot = e.slot
        course = e.course
        room = e.room
        fac = e.faculty
        fac_user = fac.user if fac else None

        formatted_entries.append({
            "day": slot.day if slot else "N/A",
            "start_time": slot.start_time.strftime("%H:%M") if (slot and slot.start_time) else "",
            "end_time": slot.end_time.strftime("%H:%M") if (slot and slot.end_time) else "",
            "course_code": course.course_code if course else "N/A",
            "course_title": course.course_name if course else "N/A",
            "room": room.room_number if room else "N/A",
            "faculty_name": fac_user.name if fac_user else "N/A",
            "status": e.status or "ACTIVE",
        })

    formatted_entries.sort(
        key=lambda x: (
            day_order.get(x["day"], 99),
            x["start_time"],
        )
    )

    section = db.query(Section).filter(Section.id == student.section_id).first() if student.section_id else None
    batch = db.query(Batch).filter(Batch.id == student.batch_id).first() if student.batch_id else None

    return {
        "student_name": student.user.name if (student and student.user) else "Student",
        "student_id": student.student_id if student else "N/A",
        "section": section.section_name if section else "N/A",
        "batch": batch.batch_name if batch else "All",
        "total_classes": len(formatted_entries),
        "entries": formatted_entries,
    }


def get_class_status_data(
    db: Session,
    user: User,
    ref_time: Optional[datetime.time] = None,
    ref_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Evaluates real-time class status (PROJECT_SPECIFICATION.md §8.4a)
    Strictly derived from current time and published timetable entries:
    - CANCELLED if entry.status == 'CANCELLED'
    - RESCHEDULED if entry.status == 'RESCHEDULED'
    - UPCOMING if now < start_time
    - ONGOING if start_time <= now < end_time
    - COMPLETED if now >= end_time
    """
    now_date = ref_date or datetime.date.today()
    now_time = ref_time or datetime.datetime.now().time()
    today_day = now_date.strftime("%A").upper()

    # 1. Fetch relevant timetable entries for today
    if user.role == "STUDENT":
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if not student:
            return {"error": "Student profile not found", "classes": []}

        published_version = (
            db.query(TimetableVersion)
            .filter(TimetableVersion.status == "PUBLISHED")
            .order_by(TimetableVersion.published_at.desc())
            .first()
        )
        if not published_version:
            return {"message": "No published timetable active", "classes": []}

        query = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableEntry.version_id == published_version.id,
                TimetableEntry.section_id == student.section_id,
                TimeSlot.day == today_day,
            )
        )
        if student.batch_id:
            query = query.filter((TimetableEntry.batch_id.is_(None)) | (TimetableEntry.batch_id == student.batch_id))
        else:
            query = query.filter(TimetableEntry.batch_id.is_(None))

    elif user.role == "FACULTY":
        from backend.models.academic import Faculty
        faculty = db.query(Faculty).filter(Faculty.user_id == user.id).first()
        if not faculty:
            return {"error": "Faculty profile not found", "classes": []}

        published_version = (
            db.query(TimetableVersion)
            .filter(TimetableVersion.status == "PUBLISHED")
            .order_by(TimetableVersion.published_at.desc())
            .first()
        )
        if not published_version:
            return {"message": "No published timetable active", "classes": []}

        query = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableEntry.version_id == published_version.id,
                TimetableEntry.faculty_id == faculty.id,
                TimeSlot.day == today_day,
            )
        )
    else:
        # Admin: get upcoming/ongoing classes across the university
        published_version = (
            db.query(TimetableVersion)
            .filter(TimetableVersion.status == "PUBLISHED")
            .order_by(TimetableVersion.published_at.desc())
            .first()
        )
        if not published_version:
            return {"message": "No published timetable active", "classes": []}

        query = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableEntry.version_id == published_version.id,
                TimeSlot.day == today_day,
            )
        )

    entries = query.all()
    results: List[Dict[str, Any]] = []

    for e in entries:
        slot = e.slot
        if not slot or not slot.start_time or not slot.end_time:
            continue

        # Deterministic status derivation (§8.4a)
        if e.status == "CANCELLED":
            calculated_status = "CANCELLED"
        elif e.status == "RESCHEDULED":
            calculated_status = "RESCHEDULED"
        elif now_time < slot.start_time:
            calculated_status = "UPCOMING"
        elif slot.start_time <= now_time < slot.end_time:
            calculated_status = "ONGOING"
        else:
            calculated_status = "COMPLETED"

        course = e.course
        room = e.room
        fac = e.faculty
        fac_user = fac.user if fac else None

        results.append({
            "course_code": course.course_code if course else "N/A",
            "course_title": course.course_name if course else "N/A",
            "room": room.room_number if room else "N/A",
            "faculty": fac_user.name if fac_user else "N/A",
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "class_status": calculated_status,
        })

    results.sort(key=lambda x: x["start_time"])

    # Highlight current and next classes
    ongoing = next((c for c in results if c["class_status"] == "ONGOING"), None)
    next_up = next((c for c in results if c["class_status"] == "UPCOMING"), None)

    return {
        "date": str(now_date),
        "day": today_day,
        "current_time": now_time.strftime("%H:%M"),
        "ongoing_class": ongoing,
        "next_class": next_up,
        "classes": results,
    }
