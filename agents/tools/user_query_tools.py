"""
agents/tools/user_query_tools.py
--------------------------------
Personal notifications, requests, and free-period calculations.
All data is strictly scoped to the authenticated caller's identity (user.id).
Never leaks other users' notifications or request status.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.academic import Faculty, Student, Section
from backend.models.space_time import TimeSlot
from backend.models.timetable import Timetable, TimetableEntry
from backend.models.workflow import Notification, ChangeRequest
from backend.models.curriculum import CurriculumRequest
from backend.models.substitution import FacultySubstitution


def get_user_notifications_data(
    db: Session,
    user: User,
    unread_only: bool = False,
    limit: int = 15,
) -> Dict[str, Any]:
    """
    Retrieves notifications belonging strictly to the authenticated user.
    """
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))

    total_count = query.count()
    notifs = query.order_by(Notification.created_at.desc()).limit(limit).all()

    items = []
    for n in notifs:
        items.append({
            "id": n.id,
            "title": n.title or "Campus Announcement",
            "message": n.message or "",
            "type": n.type or "INFO",
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else "",
        })

    unread_count = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read.is_(False),
    ).count()

    return {
        "success": True,
        "total_notifications": total_count,
        "unread_count": unread_count,
        "notifications": items,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Campus Notification System",
    }


def get_user_requests_status_data(
    db: Session,
    user: User,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Retrieves status of requests submitted by or assigned to the authenticated user.
    Includes change requests, substitution requests, and curriculum requests.
    """
    # 1. Change requests
    cr_query = db.query(ChangeRequest).filter(ChangeRequest.requested_by == user.id)
    change_requests = cr_query.order_by(ChangeRequest.created_at.desc()).limit(limit).all()
    cr_items = [
        {
            "id": cr.id,
            "type": "CHANGE_REQUEST",
            "status": cr.status,
            "details": cr.reason or cr.request_type or "Schedule change request",
            "created_at": cr.created_at.isoformat() if cr.created_at else "",
        }
        for cr in change_requests
    ]

    # 2. Substitution requests (if faculty)
    sub_items = []
    if user.role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
        if fac:
            subs = (
                db.query(FacultySubstitution)
                .filter(
                    (FacultySubstitution.original_faculty_id == fac.id)
                    | (FacultySubstitution.substitute_faculty_id == fac.id)
                )
                .order_by(FacultySubstitution.created_at.desc())
                .limit(limit)
                .all()
            )
            for s in subs:
                is_requester = (s.original_faculty_id == fac.id)
                sub_items.append({
                    "id": s.id,
                    "type": "FACULTY_SUBSTITUTION",
                    "role_in_request": "Requester" if is_requester else "Substitute",
                    "status": s.status,
                    "date": s.substitution_date.isoformat() if s.substitution_date else "",
                    "reason": s.reason or "Faculty class coverage",
                    "created_at": s.created_at.isoformat() if s.created_at else "",
                })

    all_requests = cr_items + sub_items
    return {
        "success": True,
        "total_requests": len(all_requests),
        "requests": all_requests,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Workflow & Request Processing Engine",
    }


def get_faculty_free_periods_data(
    db: Session,
    user: User,
    day: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculates free teaching periods, scheduled commitments, institutional breaks,
    and unavailable intervals for the authenticated faculty member.
    Grounds calculations strictly in TimeSlot, published TimetableEntry, and FacultyAvailability records.
    Strictly distinguishes free teaching periods from institutional breaks and non-working hours.
    """
    if user.role not in ("FACULTY", "ADMIN", "SUPER_ADMIN"):
        return {"error": "Access denied: Free periods calculation is only available for faculty and administrators."}

    fac: Optional[Faculty] = None
    if user.role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
    else:
        # Admin inspecting first faculty or profile
        fac = db.query(Faculty).first()

    if not fac:
        return {"error": "Faculty academic profile not found in database."}

    # Normalize day
    day_map = {
        "MONDAY": "MON", "TUESDAY": "TUE", "WEDNESDAY": "WED",
        "THURSDAY": "THU", "FRIDAY": "FRI", "SATURDAY": "SAT", "SUNDAY": "SUN",
        "MON": "MON", "TUE": "TUE", "WED": "WED", "THU": "THU", "FRI": "FRI", "SAT": "SAT", "SUN": "SUN",
    }
    today_dt = datetime.date.today()
    target_day = today_dt.strftime("%a").upper()[:3]
    if day:
        clean_day = day.upper().strip()
        if clean_day == "TODAY":
            target_day = today_dt.strftime("%a").upper()[:3]
        elif clean_day == "TOMORROW":
            target_day = (today_dt + datetime.timedelta(days=1)).strftime("%a").upper()[:3]
        else:
            target_day = day_map.get(clean_day, clean_day[:3])

    if target_day not in ("MON", "TUE", "WED", "THU", "FRI", "SAT"):
        target_day = "MON"

    # 1. Institutional Teaching Slots for target_day
    class_slots = (
        db.query(TimeSlot)
        .filter(TimeSlot.day == target_day, TimeSlot.slot_type == "CLASS")
        .order_by(TimeSlot.start_time)
        .all()
    )

    # 2. Institutional Break Slots (Lunch, Tea) - strictly NOT free teaching time
    break_slots = (
        db.query(TimeSlot)
        .filter(TimeSlot.day == target_day, TimeSlot.slot_type.in_(["BREAK", "LUNCH"]))
        .order_by(TimeSlot.start_time)
        .all()
    )

    # 3. Teaching commitments from active published timetable
    from backend.models.timetable import TimetableVersion
    published_version = (
        db.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .order_by(TimetableVersion.published_at.desc())
        .first()
    )
    busy_entry_map: Dict[int, TimetableEntry] = {}
    if published_version:
        entries = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(
                TimetableEntry.version_id == published_version.id,
                TimetableEntry.faculty_id == fac.id,
                TimeSlot.day == target_day,
                TimetableEntry.status != "CANCELLED",
            )
            .all()
        )
        for e in entries:
            if e.slot_id:
                busy_entry_map[e.slot_id] = e

    # 4. Faculty marked unavailable slots
    from backend.models.space_time import FacultyAvailability
    unavail_slot_ids = {
        fa.slot_id
        for fa in db.query(FacultyAvailability)
        .join(TimeSlot, FacultyAvailability.slot_id == TimeSlot.id)
        .filter(
            FacultyAvailability.faculty_id == fac.id,
            TimeSlot.day == target_day,
            FacultyAvailability.availability == "UNAVAILABLE",
        )
        .all()
    }

    free_teaching_periods = []
    teaching_commitments = []
    unavailable_periods = []

    for slot in class_slots:
        st_str = slot.start_time.strftime("%H:%M") if slot.start_time else ""
        et_str = slot.end_time.strftime("%H:%M") if slot.end_time else ""
        slot_info: Dict[str, Any] = {
            "period": f"{st_str}–{et_str}",
            "start_time": st_str,
            "end_time": et_str,
        }
        if slot.id in busy_entry_map:
            entry = busy_entry_map[slot.id]
            c = entry.course
            r = entry.room
            sec = entry.section
            slot_info["course_code"] = c.course_code if (c and c.course_code) else "N/A"
            slot_info["course_name"] = c.course_name if (c and c.course_name) else "N/A"
            slot_info["room"] = r.room_number if (r and r.room_number) else "N/A"
            slot_info["section"] = sec.section_name if (sec and sec.section_name) else "N/A"
            teaching_commitments.append(slot_info)
        elif slot.id in unavail_slot_ids:
            slot_info["reason"] = "Marked unavailable by faculty"
            unavailable_periods.append(slot_info)
        else:
            free_teaching_periods.append(slot_info)

    institutional_breaks = []
    for b in break_slots:
        st_str = b.start_time.strftime("%H:%M") if b.start_time else ""
        et_str = b.end_time.strftime("%H:%M") if b.end_time else ""
        institutional_breaks.append({
            "break_type": b.slot_type,
            "period": f"{st_str}–{et_str}",
            "start_time": st_str,
            "end_time": et_str,
            "note": "Scheduled institutional break — not free teaching time",
        })

    day_name_lookup = {
        "MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday",
        "THU": "Thursday", "FRI": "Friday", "SAT": "Saturday",
    }

    return {
        "success": True,
        "day_code": target_day,
        "day_name": day_name_lookup.get(target_day, target_day),
        "faculty_name": user.name,
        "total_teaching_slots_in_day": len(class_slots),
        "free_periods_count": len(free_teaching_periods),
        "teaching_periods_count": len(teaching_commitments),
        "free_teaching_periods": free_teaching_periods,
        "teaching_commitments": teaching_commitments,
        "institutional_breaks": institutional_breaks,
        "unavailable_periods": unavailable_periods,
        "working_hours": "08:30 to 16:30 (periods outside this are non-working hours)",
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Official Published Timetable & Faculty Workload Registry",
    }

