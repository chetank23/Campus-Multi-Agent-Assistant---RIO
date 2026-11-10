"""
agents/tools/admin_tools.py
---------------------------
Administrative query capabilities for ADMIN and SUPER_ADMIN roles.
Enforces institutional or department-scoped data access.
Answers queries directly from PostgreSQL database models:
Student, Faculty, Course, Room, Building, Section, Timetable, etc.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.academic import Department, Program, AcademicYear, Semester, Section, Student, Faculty, Batch
from backend.models.courses import Course, CourseAssignment
from backend.models.space_time import Building, Room, TimeSlot, FacultyAvailability
from backend.models.timetable import Timetable, TimetableEntry
from backend.models.resources import Resource, ResourceBooking


def _verify_admin_access(user: User) -> Optional[Dict[str, Any]]:
    if user.role not in ("ADMIN", "SUPER_ADMIN"):
        return {
            "error": f"Access denied: Administrative privileges required. Caller role '{user.role}' is not authorized."
        }
    return None


def search_student_directory_data(
    db: Session,
    user: User,
    search_query: Optional[str] = None,
    section_name: Optional[str] = None,
    batch_name: Optional[str] = None,
    semester_number: Optional[int] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Finds students matching USN (student_id), name, section, batch, or semester.
    Admin scoped to authorized department if user has department_id set.
    """
    auth_err = _verify_admin_access(user)
    if auth_err:
        return auth_err

    query = db.query(Student).join(User, Student.user_id == User.id)

    # Department scope enforcement if non-superadmin
    if user.role == "ADMIN" and user.department_id:
        query = query.filter(Student.department_id == user.department_id)

    if search_query:
        sq = search_query.strip()
        query = query.filter(
            or_(
                Student.student_id.ilike(f"%{sq}%"),
                User.name.ilike(f"%{sq}%"),
                User.email.ilike(f"%{sq}%"),
            )
        )

    if section_name:
        query = query.join(Section, Student.section_id == Section.id).filter(
            Section.section_name.ilike(section_name.strip())
        )

    if batch_name:
        query = query.join(Batch, Student.batch_id == Batch.id).filter(
            Batch.batch_name.ilike(batch_name.strip())
        )

    if semester_number:
        query = query.join(Semester, Student.semester_id == Semester.id).filter(
            Semester.semester_number == semester_number
        )

    total_count = query.count()
    students = query.order_by(Student.student_id.asc()).limit(limit).all()

    student_records = []
    for s in students:
        sec = s.section
        dept = s.department
        u = s.user
        ct = sec.class_teacher if sec else None
        student_records.append({
            "id": s.id,
            "usn": s.student_id or "N/A",
            "name": u.name if u else "Student",
            "email": u.email if u else "N/A",
            "department": dept.name if dept else "N/A",
            "section": sec.section_name if sec else "N/A",
            "semester": s.semester.semester_number if s.semester else None,
            "class_teacher": ct.user.name if (ct and ct.user) else "Unassigned",
        })

    return {
        "success": True,
        "total_count": total_count,
        "returned_count": len(student_records),
        "students": student_records,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Student Academic Master Registry",
    }


def search_faculty_directory_data(
    db: Session,
    user: User,
    search_query: Optional[str] = None,
    department_name: Optional[str] = None,
    section_name: Optional[str] = None,
    has_availability: Optional[bool] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Searches faculty records by name, employee ID, specialization, or department.
    Lists assigned courses and availability count.
    """
    auth_err = _verify_admin_access(user)
    if auth_err:
        return auth_err

    query = db.query(Faculty).join(User, Faculty.user_id == User.id)

    if user.role == "ADMIN" and user.department_id:
        query = query.filter(Faculty.department_id == user.department_id)

    if section_name:
        query = query.join(CourseAssignment, CourseAssignment.faculty_id == Faculty.id).join(Section, CourseAssignment.section_id == Section.id).filter(
            Section.section_name.ilike(f"%{section_name.strip()}%")
        )

    if search_query:
        sq = search_query.strip().replace("Dr.", "").replace("Prof.", "").strip()
        query = query.filter(
            or_(
                User.name.ilike(f"%{sq}%"),
                Faculty.faculty_id.ilike(f"%{sq}%"),
                Faculty.specialization.ilike(f"%{sq}%"),
                Faculty.areas_of_interest.ilike(f"%{sq}%"),
            )
        )

    if department_name:
        query = query.join(Department, Faculty.department_id == Department.id).filter(
            or_(
                Department.name.ilike(f"%{department_name}%"),
                Department.department_code.ilike(f"%{department_name}%"),
            )
        )

    total_count = query.count()
    faculty_list = query.order_by(User.name.asc()).limit(limit).all()

    results = []
    for f in faculty_list:
        u = f.user
        dept = f.department
        assignments = db.query(CourseAssignment).filter(CourseAssignment.faculty_id == f.id).all()
        courses_assigned = [
            f"{a.course.course_code} - {a.course.course_name} ({a.section.section_name if a.section else 'All'})"
            for a in assignments if a.course
        ]
        avail_count = db.query(FacultyAvailability).filter(
            FacultyAvailability.faculty_id == f.id,
            FacultyAvailability.availability == "AVAILABLE",
        ).count()

        results.append({
            "faculty_id": f.faculty_id or f"FAC-{f.id}",
            "name": u.name if u else "Faculty Member",
            "email": u.email if u else "N/A",
            "designation": f.designation or "Faculty",
            "department": dept.name if dept else "Academic Department",
            "specialization": f.specialization or "General",
            "contact_number": f.contact_number or "N/A",
            "assigned_courses": courses_assigned,
            "availability_slots_configured": avail_count,
        })

    return {
        "success": True,
        "total_count": total_count,
        "returned_count": len(results),
        "faculty": results,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Campus Faculty Directory",
    }


def search_course_directory_data(
    db: Session,
    user: User,
    department_name: Optional[str] = None,
    semester_number: Optional[int] = None,
    course_query: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Lists courses, credit breakdown, syllabus requirements, and instructor assignments.
    """
    auth_err = _verify_admin_access(user)
    if auth_err:
        return auth_err

    query = db.query(Course)

    if user.role == "ADMIN" and user.department_id:
        query = query.filter(Course.department_id == user.department_id)

    if department_name:
        query = query.join(Department, Course.department_id == Department.id).filter(
            or_(
                Department.name.ilike(f"%{department_name}%"),
                Department.department_code.ilike(f"%{department_name}%"),
            )
        )

    if course_query:
        cq = course_query.strip()
        query = query.filter(
            or_(
                Course.course_code.ilike(f"%{cq}%"),
                Course.course_name.ilike(f"%{cq}%"),
            )
        )

    total_count = query.count()
    courses = query.order_by(Course.course_code.asc()).limit(limit).all()

    results = []
    for c in courses:
        dept = c.department
        assignments = db.query(CourseAssignment).filter(CourseAssignment.course_id == c.id).all()
        instructors = [
            f"{a.faculty.user.name if (a.faculty and a.faculty.user) else 'Faculty'} ({a.section.section_name if a.section else 'Section'})"
            for a in assignments
        ]
        results.append({
            "course_id": c.id,
            "course_code": c.course_code or "N/A",
            "course_name": c.course_name or "Course",
            "course_type": c.course_type or "THEORY",
            "credits": c.credits or 0,
            "lecture_hours": c.lecture_hours or 0,
            "department": dept.name if dept else "N/A",
            "assigned_instructors": instructors,
        })

    return {
        "success": True,
        "total_count": total_count,
        "returned_count": len(results),
        "courses": results,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "University Academic Course Catalog",
    }


def get_infrastructure_inventory_data(
    db: Session,
    user: User,
    building_name_or_code: Optional[str] = None,
    room_type: Optional[str] = None,
    floor_number: Optional[int] = None,
    limit: int = 60,
) -> Dict[str, Any]:
    """
    Returns campus infrastructure: buildings, floors, rooms, labs, capacities.
    """
    auth_err = _verify_admin_access(user)
    if auth_err:
        return auth_err

    bldg_query = db.query(Building)
    if building_name_or_code:
        bqc = building_name_or_code.strip()
        bldg_query = bldg_query.filter(
            or_(
                Building.name.ilike(f"%{bqc}%"),
                Building.code.ilike(f"%{bqc}%"),
            )
        )
    buildings = bldg_query.order_by(Building.name).all()

    room_query = db.query(Room).join(Building, Room.building_id == Building.id)
    if building_name_or_code:
        bqc = building_name_or_code.strip()
        room_query = room_query.filter(
            or_(
                Building.name.ilike(f"%{bqc}%"),
                Building.code.ilike(f"%{bqc}%"),
            )
        )

    if room_type:
        room_query = room_query.filter(Room.room_type == room_type.upper().strip())

    if floor_number is not None:
        room_query = room_query.filter(Room.floor_number == floor_number)

    total_rooms = room_query.count()
    rooms = room_query.order_by(Room.floor_number.asc(), Room.room_number.asc()).limit(limit).all()

    rooms_list = [
        {
            "room_id": r.id,
            "room_number": r.room_number,
            "building_code": r.building.code if r.building else "N/A",
            "building_name": r.building.name if r.building else "N/A",
            "floor_number": r.floor_number,
            "room_type": r.room_type or "CLASSROOM",
            "capacity": r.capacity or 0,
        }
        for r in rooms
    ]

    return {
        "success": True,
        "total_buildings": len(buildings),
        "buildings": [{"code": b.code, "name": b.name, "floors": b.number_of_floors} for b in buildings],
        "total_rooms": total_rooms,
        "returned_rooms_count": len(rooms_list),
        "rooms": rooms_list,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Campus Physical Infrastructure Registry",
    }


def get_section_timetable_data(
    db: Session,
    user: User,
    section_name: Optional[str] = None,
    day: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves the published timetable for a requested section.
    Distinguishes active published timetable from unfinalized drafts.
    """
    auth_err = _verify_admin_access(user)
    if auth_err:
        return auth_err

    sec_name = (section_name or "AIDS-A").strip()
    sec = db.query(Section).filter(Section.section_name.ilike(sec_name)).first()
    if not sec:
        # Fallback to first section
        sec = db.query(Section).first()
        if not sec:
            return {"error": f"Section '{sec_name}' could not be found."}

    tt = (
        db.query(Timetable)
        .filter(Timetable.section_id == sec.id, Timetable.status == "PUBLISHED")
        .first()
    )
    if not tt:
        return {
            "success": True,
            "section": sec.section_name,
            "status": "UNPUBLISHED",
            "message": f"Schedule for {sec.section_name}: No published timetable is currently active for this section.",
            "entries": [],
        }

    q = (
        db.query(TimetableEntry)
        .filter(TimetableEntry.timetable_id == tt.id)
        .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
    )

    if day:
        day_clean = day.upper().strip()
        day_map = {
            "MONDAY": "MON", "TUESDAY": "TUE", "WEDNESDAY": "WED",
            "THURSDAY": "THU", "FRIDAY": "FRI", "SATURDAY": "SAT",
        }
        day_token = day_map.get(day_clean, day_clean)
        q = q.filter(TimeSlot.day == day_token)

    entries = q.order_by(TimeSlot.day, TimeSlot.start_time).all()

    entry_records = []
    for e in entries:
        slot = e.slot
        crs = e.course
        fac = e.faculty
        rm = e.room
        entry_records.append({
            "day": slot.day if slot else "N/A",
            "start_time": slot.start_time.strftime("%H:%M") if (slot and slot.start_time) else "",
            "end_time": slot.end_time.strftime("%H:%M") if (slot and slot.end_time) else "",
            "course_code": crs.course_code if crs else "N/A",
            "course_title": crs.course_name if crs else "Class",
            "faculty_name": fac.user.name if (fac and fac.user) else "Instructor",
            "room": rm.room_number if rm else "TBD",
            "building": rm.building.name if (rm and rm.building) else "Campus Block",
        })

    return {
        "success": True,
        "section": sec.section_name,
        "department": sec.department.name if sec.department else "Academic Department",
        "semester": sec.semester.semester_number if sec.semester else 7,
        "total_scheduled_classes": len(entry_records),
        "entries": entry_records,
        "status": "PUBLISHED",
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Official Published Section Timetable",
    }
