"""
agents/tools/super_admin_tools.py
---------------------------------
Institutional, academic, operational, and governance tools for SUPER_ADMIN role.
All queries are grounded strictly in PostgreSQL records and maintain data isolation.
Historical and cleared operational records are clearly segregated from active published records.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.academic import Department, Program, AcademicYear, Semester, Section, Student, Faculty, Batch
from backend.models.courses import Course, CourseAssignment
from backend.models.space_time import Building, Room, TimeSlot
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry
from backend.models.resources import Resource, ResourceBooking
from backend.models.workflow import AuditLog, ChangeRequest, Notification


def _verify_super_admin(user: User) -> Optional[Dict[str, Any]]:
    if user.role != "SUPER_ADMIN":
        return {
            "error": f"Access denied: Super Admin authorization required. Caller role '{user.role}' is not permitted."
        }
    return None


def get_institutional_overview_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Produces complete institutional metrics:
    total students, faculty, departments, programs, courses, buildings, rooms, labs,
    and active published timetables.
    """
    auth_err = _verify_super_admin(user)
    if auth_err:
        return auth_err

    students_count = db.query(Student).count()
    faculty_count = db.query(Faculty).count()
    depts_count = db.query(Department).count()
    programs_count = db.query(Program).count()
    courses_count = db.query(Course).count()
    buildings_count = db.query(Building).count()
    rooms_count = db.query(Room).count()
    labs_count = db.query(Room).filter(Room.room_type == "LAB").count()
    sections_count = db.query(Section).count()

    # Active published timetables (canonical Timetable table only, never counting historical versions)
    published_tt_count = db.query(Timetable).filter(Timetable.status == "PUBLISHED").count()
    draft_tt_count = db.query(Timetable).filter(Timetable.status == "DRAFT").count()

    # Department breakdown
    depts = db.query(Department).order_by(Department.name).all()
    dept_summaries: List[Dict[str, Any]] = []
    for d in depts:
        stu_in_dept = db.query(Student).filter(Student.department_id == d.id).count()
        fac_in_dept = db.query(Faculty).filter(Faculty.department_id == d.id).count()
        crs_in_dept = db.query(Course).filter(Course.department_id == d.id).count()
        sec_in_dept = db.query(Section).filter(Section.department_id == d.id).count()
        dept_summaries.append({
            "department_id": d.id,
            "department_code": d.department_code or f"DEPT-{d.id}",
            "department_name": d.name,
            "students_count": stu_in_dept,
            "faculty_count": fac_in_dept,
            "courses_count": crs_in_dept,
            "sections_count": sec_in_dept,
        })

    return {
        "success": True,
        "total_students": students_count,
        "total_faculty": faculty_count,
        "total_departments": depts_count,
        "total_programs": programs_count,
        "total_courses": courses_count,
        "total_buildings": buildings_count,
        "total_rooms": rooms_count,
        "total_labs": labs_count,
        "total_sections": sections_count,
        "published_timetables": published_tt_count,
        "draft_timetables": draft_tt_count,
        "departments": dept_summaries,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Central Institutional Registry (PostgreSQL)",
    }


def get_academic_structure_overview_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Returns full structural mapping of configured academic hierarchy:
    academic years, semesters, departments, programs, sections, and batches.
    """
    auth_err = _verify_super_admin(user)
    if auth_err:
        return auth_err

    academic_years = db.query(AcademicYear).order_by(AcademicYear.id.desc()).all()
    departments = db.query(Department).order_by(Department.name).all()
    programs = db.query(Program).order_by(Program.program_name).all()
    sections = db.query(Section).order_by(Section.section_name).all()
    semesters = db.query(Semester).order_by(Semester.semester_number).all()

    structure_items: List[Dict[str, Any]] = []
    for dept in departments:
        dept_progs = [p for p in programs if p.department_id == dept.id]
        dept_secs = [s for s in sections if s.department_id == dept.id]
        dept_stu_cnt = db.query(Student).filter(Student.department_id == dept.id).count()
        dept_fac_cnt = db.query(Faculty).filter(Faculty.department_id == dept.id).count()

        sections_info = []
        for sec in dept_secs:
            ct = sec.class_teacher
            sections_info.append({
                "section_id": sec.id,
                "section_name": sec.section_name or f"Section #{sec.id}",
                "student_count": sec.student_count or db.query(Student).filter(Student.section_id == sec.id).count(),
                "class_teacher": ct.user.name if (ct and ct.user) else "Unassigned",
            })

        structure_items.append({
            "department_id": dept.id,
            "department_name": dept.name,
            "department_code": dept.department_code,
            "programs": [{"id": p.id, "name": p.program_name} for p in dept_progs],
            "sections": sections_info,
            "enrolled_students": dept_stu_cnt,
            "faculty_members": dept_fac_cnt,
        })

    return {
        "success": True,
        "academic_years": [{"id": ay.id, "name": ay.name} for ay in academic_years],
        "semesters": [{"id": sm.id, "semester_number": sm.semester_number} for sm in semesters],
        "academic_structure": structure_items,
        "total_departments": len(departments),
        "total_sections": len(sections),
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Academic Governance Register",
    }


def get_operational_overview_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Returns operational scheduling status:
    active published timetables, preview drafts, resource bookings, pending requests,
    and recent scheduling operations.
    """
    auth_err = _verify_super_admin(user)
    if auth_err:
        return auth_err

    published_tt = (
        db.query(Timetable)
        .filter(Timetable.status == "PUBLISHED")
        .all()
    )
    draft_tt = (
        db.query(Timetable)
        .filter(Timetable.status == "DRAFT")
        .all()
    )

    published_details = []
    for tt in published_tt:
        sec = tt.section
        dept_name = sec.department.name if (sec and sec.department) else "Campus Wide"
        sec_name = sec.section_name if sec else f"Section #{tt.section_id}"
        sem_num = tt.semester.semester_number if tt.semester else 7
        entries_count = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == tt.id).count()
        published_details.append({
            "timetable_id": tt.id,
            "section": sec_name,
            "department": dept_name,
            "semester": sem_num,
            "status": "PUBLISHED",
            "scheduled_entries": entries_count,
        })

    # Historical versions count (distinguished from active canonical)
    historical_versions_count = db.query(TimetableVersion).count()

    # Resource bookings summary
    bookings_count = db.query(ResourceBooking).count()
    pending_bookings = (
        db.query(ResourceBooking)
        .filter(ResourceBooking.status == "PENDING")
        .count()
    )

    # Change requests summary
    pending_change_requests = (
        db.query(ChangeRequest)
        .filter(ChangeRequest.status == "PENDING")
        .count()
    )

    # Recent operational scheduling audit logs
    recent_sched_ops = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.in_([
                "TIMETABLE_PUBLISHED",
                "TIMETABLE_GENERATED",
                "TIMETABLE_REVISED",
                "CLEAR_GENERATED_OPERATIONAL_DATA",
                "SUBSTITUTION_REQUESTED",
            ])
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(10)
        .all()
    )
    ops_list = [
        {
            "id": log.id,
            "action": log.action,
            "entity_type": log.entity_type,
            "timestamp": log.timestamp.isoformat() if log.timestamp else "",
            "performed_by": log.user.name if (log.user and log.user.name) else "System",
        }
        for log in recent_sched_ops
    ]

    return {
        "success": True,
        "published_timetables_count": len(published_tt),
        "draft_previews_count": len(draft_tt),
        "historical_versions_count": historical_versions_count,
        "published_timetables": published_details,
        "total_resource_bookings": bookings_count,
        "pending_resource_bookings": pending_bookings,
        "pending_change_requests": pending_change_requests,
        "recent_scheduling_operations": ops_list,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Operational Master Register",
    }


def get_governance_system_status_data(
    db: Session,
    user: User,
    limit: int = 15,
) -> Dict[str, Any]:
    """
    Returns recent audit activity, configuration status, and health flags.
    Distinguishes active records from historical or cleared records.
    """
    auth_err = _verify_super_admin(user)
    if auth_err:
        return auth_err

    # Recent audit logs
    audit_logs = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(min(limit, 50))
        .all()
    )
    audit_items = []
    for log in audit_logs:
        lifecycle_tag = "ACTIVE"
        if log.old_value and isinstance(log.old_value, dict) and log.old_value.get("lifecycle_status") == "HISTORICAL_CLEARED":
            lifecycle_tag = "HISTORICAL_CLEARED"
        elif log.new_value and isinstance(log.new_value, dict) and log.new_value.get("lifecycle_status") == "HISTORICAL_CLEARED":
            lifecycle_tag = "HISTORICAL_CLEARED"

        audit_items.append({
            "id": log.id,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else "",
            "user_name": log.user.name if (log.user and log.user.name) else "System",
            "lifecycle_status": lifecycle_tag,
        })

    # Incomplete institutional configuration checks
    warnings: List[str] = []
    unassigned_sections = db.query(Section).filter(Section.class_teacher_id.is_(None)).count()
    if unassigned_sections > 0:
        warnings.append(f"{unassigned_sections} section(s) currently lack an assigned class teacher.")

    sections_without_timetable = (
        db.query(Section)
        .outerjoin(Timetable, (Timetable.section_id == Section.id) & (Timetable.status == "PUBLISHED"))
        .filter(Timetable.id.is_(None))
        .count()
    )
    if sections_without_timetable > 0:
        warnings.append(f"{sections_without_timetable} section(s) do not yet have an active published timetable.")

    courses_without_assignments = (
        db.query(Course)
        .outerjoin(CourseAssignment, CourseAssignment.course_id == Course.id)
        .filter(CourseAssignment.id.is_(None))
        .count()
    )
    if courses_without_assignments > 0:
        warnings.append(f"{courses_without_assignments} course(s) have no faculty instructors assigned.")

    return {
        "success": True,
        "recent_audit_logs": audit_items,
        "total_audit_records": db.query(AuditLog).count(),
        "configuration_warnings": warnings,
        "system_status": "HEALTHY" if not warnings else "ACTION_RECOMMENDED",
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "Governance & Compliance Audit Register",
    }
