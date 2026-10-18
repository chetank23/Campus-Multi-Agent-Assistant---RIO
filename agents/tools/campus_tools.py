"""
agents/tools/campus_tools.py
----------------------------
Safe, read-only tools for Course, Room/Lab, and Academic Calendar lookups.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.academic import Department
from backend.models.courses import Course
from backend.models.space_time import AcademicCalendar, Building, Room


def get_course_details_data(
    db: Session,
    query_str: str,
) -> Dict[str, Any]:
    """
    Looks up course information by course code or title.
    """
    pattern = f"%{query_str.strip()}%"
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
        results.append({
            "code": c.course_code or "N/A",
            "title": c.course_name or "N/A",
            "credits": c.credits,
            "department": dept.name if dept else "N/A",
            "is_elective": (c.course_type == "ELECTIVE"),
        })

    return {
        "count": len(results),
        "results": results,
    }


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
        # Default to today onwards
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

    IMPORTANT DISTINCTION:
    - This tool reports the *total inventory* of registered, active rooms
      (status == 'ACTIVE') — not whether any specific room is free right now.
    - Real-time availability (is Room X unoccupied at this moment?) requires
      checking timetable slots for the current date and time.  That data is
      not available through this tool.

    Use this when the user asks "how many classrooms are there?" or "how many
    labs does the campus have?"  Do NOT use this to answer "which rooms are
    free right now?" — that needs a different, time-aware query.
    """
    base_query = db.query(Room).filter(Room.status == "ACTIVE")

    # Optionally filter by room type
    if room_type:
        room_type_upper = room_type.strip().upper()
        base_query = base_query.filter(Room.room_type == room_type_upper)

    # Aggregate counts by room_type
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
            "This count reflects rooms registered as ACTIVE in the campus facilities register. "
            "To determine which rooms are free at a specific time, please specify a date and time "
            "or check the timetable for scheduling conflicts."
        ),
    }
