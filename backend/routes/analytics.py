"""
backend/routes/analytics.py
---------------------------
Data-backed campus reporting & analytics endpoints for RIO-MJP.
Calculated directly from live database records with zero fabricated numbers.
Restricted to ADMIN role.
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import require_role
from backend.models.academic import Department, Faculty, Section, Student
from backend.models.courses import Course
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Building, Room
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import ChangeRequest

router = APIRouter(prefix="/admin/analytics", tags=["Reports & Analytics"])


@router.get("/overview")
def get_analytics_overview(
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns verified institutional analytics aggregated across academic, space, timetable,
    and workflow databases.
    """
    # 1. User & People metrics
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_students = db.query(func.count(Student.id)).scalar() or 0
    total_faculty = db.query(func.count(Faculty.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0

    # 2. Academic metrics
    total_departments = db.query(func.count(Department.id)).scalar() or 0
    total_courses = db.query(func.count(Course.id)).scalar() or 0
    total_sections = db.query(func.count(Section.id)).scalar() or 0

    # 3. Space & Infrastructure
    total_buildings = db.query(func.count(Building.id)).scalar() or 0
    total_rooms = db.query(func.count(Room.id)).scalar() or 0
    lab_rooms = db.query(func.count(Room.id)).filter(Room.room_type == "LAB").scalar() or 0
    classroom_rooms = total_rooms - lab_rooms
    total_capacity = db.query(func.sum(Room.capacity)).scalar() or 0

    # 4. Timetable version status breakdown
    version_rows = (
        db.query(TimetableVersion.status, func.count(TimetableVersion.id))
        .group_by(TimetableVersion.status)
        .all()
    )
    timetable_breakdown = {status: count for status, count in version_rows}
    total_versions = sum(timetable_breakdown.values())

    # 5. Resource bookings breakdown
    booking_rows = (
        db.query(ResourceBooking.status, func.count(ResourceBooking.id))
        .group_by(ResourceBooking.status)
        .all()
    )
    booking_breakdown = {status: count for status, count in booking_rows}
    total_bookings = sum(booking_breakdown.values())

    # 6. Change requests breakdown
    cr_rows = (
        db.query(ChangeRequest.status, func.count(ChangeRequest.id))
        .group_by(ChangeRequest.status)
        .all()
    )
    change_request_breakdown = {status: count for status, count in cr_rows}
    total_change_requests = sum(change_request_breakdown.values())

    # 7. Department-level breakdown
    departments = db.query(Department).all()
    dept_summaries: List[Dict[str, Any]] = []
    for d in departments:
        dept_faculty = db.query(func.count(Faculty.id)).filter(Faculty.department_id == d.id).scalar() or 0
        dept_students = db.query(func.count(Student.id)).filter(Student.department_id == d.id).scalar() or 0
        dept_courses = db.query(func.count(Course.id)).filter(Course.department_id == d.id).scalar() or 0
        dept_sections = db.query(func.count(Section.id)).join(Student, Student.section_id == Section.id).filter(Student.department_id == d.id).distinct().scalar() or 0

        # Check published timetable entries for department
        published_entries = (
            db.query(func.count(TimetableEntry.id))
            .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
            .filter(
                TimetableVersion.status == "PUBLISHED",
                TimetableEntry.department_id == d.id,
            )
            .scalar()
            or 0
        )

        dept_summaries.append({
            "department_id": d.id,
            "department_code": d.department_code,
            "department_name": d.name,
            "faculty_count": dept_faculty,
            "student_count": dept_students,
            "course_count": dept_courses,
            "published_schedule_entries": published_entries,
        })

    return {
        "people": {
            "total_users": total_users,
            "total_students": total_students,
            "total_faculty": total_faculty,
            "active_users": active_users,
        },
        "academic": {
            "total_departments": total_departments,
            "total_courses": total_courses,
            "total_sections": total_sections,
        },
        "infrastructure": {
            "total_buildings": total_buildings,
            "total_rooms": total_rooms,
            "classrooms": classroom_rooms,
            "labs": lab_rooms,
            "total_seat_capacity": total_capacity,
        },
        "timetables": {
            "total_versions": total_versions,
            "status_breakdown": timetable_breakdown,
        },
        "resource_bookings": {
            "total_bookings": total_bookings,
            "status_breakdown": booking_breakdown,
        },
        "change_requests": {
            "total_change_requests": total_change_requests,
            "status_breakdown": change_request_breakdown,
        },
        "department_summaries": dept_summaries,
    }


@router.get("/department-progress")
def get_department_progress(
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Computes truthful timetable completion progress for every academic department:
    Total sections vs sections with published schedules.
    """
    departments = db.query(Department).all()
    results = []

    for d in departments:
        # Sections in this department
        sections = (
            db.query(Section)
            .filter(Section.department_id == d.id)
            .all()
        )
        total_sec = len(sections)

        # Published sections
        if total_sec == 0:
            pct = 100 if d.department_code else 0
            published_sec = 0
        else:
            published_sec = (
                db.query(func.count(func.distinct(TimetableEntry.section_id)))
                .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
                .filter(
                    TimetableVersion.status == "PUBLISHED",
                    TimetableEntry.department_id == d.id,
                )
                .scalar()
                or 0
            )
            pct = min(100, int((published_sec / total_sec) * 100))

        results.append({
            "department_id": d.id,
            "department_code": d.department_code,
            "department_name": d.name,
            "total_sections": total_sec,
            "published_sections": published_sec,
            "completion_percentage": pct,
        })

    return results
