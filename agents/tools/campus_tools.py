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

from backend.models.academic import Department, Faculty
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import AcademicCalendar, Building, Room, TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion
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
                TimetableEntry.status != "CANCELLED",
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


def get_published_timetable_status_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Retrieves the status of published timetable versions.
    - Admin: can see all versions, draft/published statuses, total entries.
    - Faculty/Student: only sees the active PUBLISHED timetable version. Draft versions remain confidential.
    """
    if user.role == "ADMIN":
        versions = db.query(TimetableVersion).order_by(TimetableVersion.id.desc()).all()
        version_list = []
        for v in versions:
            entries_count = db.query(TimetableEntry).filter(TimetableEntry.version_id == v.id).count()
            version_list.append({
                "version_id": v.id,
                "version_number": v.version_number,
                "status": v.status,
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
            "active_published_version": active_pub,
            "total_versions": len(version_list),
            "versions": version_list,
        }
    else:
        # Non-admin: strictly published version only
        pub_v = (
            db.query(TimetableVersion)
            .filter(TimetableVersion.status == "PUBLISHED")
            .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
            .first()
        )
        if not pub_v:
            return {
                "role": user.role,
                "has_published_timetable": False,
                "message": "No published timetable is currently active for this semester.",
            }

        entries_count = db.query(TimetableEntry).filter(TimetableEntry.version_id == pub_v.id).count()
        return {
            "role": user.role,
            "has_published_timetable": True,
            "version_number": pub_v.version_number,
            "academic_year": pub_v.academic_year.name if pub_v.academic_year else "N/A",
            "published_at": pub_v.published_at.strftime("%Y-%m-%d") if pub_v.published_at else None,
            "status": "PUBLISHED",
            "total_active_entries": entries_count,
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
    if user.role == "ADMIN":
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
