"""
agents/tools/scheduling_tools.py
--------------------------------
Read-only and diagnostic tools for the Scheduling Agent:
- resolve_academic_scope: Entity matcher and resolver against PostgreSQL
- analyze_scheduling_readiness: Pre-flight validator for required solver data
- explain_solver_diagnostics: Human-readable diagnostic breakdown for infeasible runs
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.identity import User
from backend.models.academic import Department, Program, Semester, Section, AcademicYear, Batch
from backend.models.courses import Course, CourseAssignment
from backend.models.space_time import Room, TimeSlot, FacultyAvailability
from backend.models.timetable import TimetableVersion
from backend.models.workflow import AuditLog
from backend.schemas.timetable_generation import GenerationScope
from backend.services.timetable_input_loader import validate_and_load_input
from backend.services.notification_service import notify_timetable_published


def resolve_academic_scope_data(
    db: Session,
    query_text: str,
    department_id: Optional[int] = None,
    program_id: Optional[int] = None,
    semester_id: Optional[int] = None,
    academic_year_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Resolves natural-language text into a typed GenerationScope.
    Matches department name/code, program name, semester number, and academic year.
    Returns:
    - resolved: bool
    - scope: dict (GenerationScope dict) or None
    - display: dict of human readable names
    - missing_parameters: list of missing fields
    - ambiguities: list of questions to ask
    """
    text = query_text.lower()

    # 1. Academic Year
    if not academic_year_id:
        # Default to the most active/latest academic year
        ay = db.query(AcademicYear).order_by(AcademicYear.id.desc()).first()
        if ay:
            academic_year_id = ay.id

    ay_obj = db.query(AcademicYear).filter(AcademicYear.id == academic_year_id).first() if academic_year_id else None

    # 2. Department
    dept_obj = None
    if department_id:
        dept_obj = db.query(Department).filter(Department.id == department_id).first()
    else:
        # Search in DB
        all_depts = db.query(Department).all()
        for d in all_depts:
            code_pattern = r"\b" + re.escape(d.department_code.lower()) + r"\b"
            name_pattern = r"\b" + re.escape(d.name.lower()) + r"\b"
            if re.search(code_pattern, text) or re.search(name_pattern, text):
                dept_obj = d
                break
            # Common synonyms
            if "computer science" in text or "cse" in text or "cs" in text:
                if d.department_code.upper() in ["CS", "CSE"]:
                    dept_obj = d
                    break
            elif "mechanical" in text or "mech" in text:
                if d.department_code.upper() in ["ME", "MECH"]:
                    dept_obj = d
                    break
            elif "electrical" in text or "eee" in text or "ee" in text:
                if d.department_code.upper() in ["EE", "EEE"]:
                    dept_obj = d
                    break

    # 3. Program
    prog_obj = None
    if program_id:
        prog_obj = db.query(Program).filter(Program.id == program_id).first()
    elif dept_obj:
        dept_progs = db.query(Program).filter(Program.department_id == dept_obj.id).all()
        if len(dept_progs) == 1:
            prog_obj = dept_progs[0]
        elif len(dept_progs) > 1:
            # Check for B.Tech vs M.Tech
            for p in dept_progs:
                p_name = p.program_name.lower() if p.program_name else ""
                if ("b.tech" in text or "btech" in text) and "b.tech" in p_name:
                    prog_obj = p
                    break
            if not prog_obj:
                # Default to primary program if unambiguous
                prog_obj = dept_progs[0]

    # 4. Semester
    sem_obj = None
    if semester_id:
        sem_obj = db.query(Semester).filter(Semester.id == semester_id).first()
    else:
        # Try to extract semester number from query: "semester 5", "sem 5", "5th semester", "semester 1", "sem 1"
        sem_match = re.search(r"\b(?:semester|sem)\s*(\d+)\b", text)
        if not sem_match:
            sem_match = re.search(r"\b(\d+)(?:st|nd|rd|th)\s*(?:semester|sem)\b", text)
        
        target_num = int(sem_match.group(1)) if sem_match else None
        
        if target_num is not None:
            # Look up semester with this number
            sem_query = db.query(Semester).filter(Semester.semester_number == target_num)
            sem_in_ay = None
            if academic_year_id:
                sem_in_ay = sem_query.filter(Semester.academic_year_id == academic_year_id).first()
                sem_obj = sem_in_ay or sem_query.first()
            else:
                sem_obj = sem_query.first()
            if sem_obj and (not ay_obj or (sem_in_ay is None and sem_obj.academic_year_id)):
                ay_obj = db.query(AcademicYear).filter(AcademicYear.id == sem_obj.academic_year_id).first()
        else:
            # If no number specified, check if "current semester" is requested
            if "current" in text or "active" in text:
                # Get the first active semester in the academic year
                sem_obj = db.query(Semester).filter(Semester.academic_year_id == academic_year_id).first()

    # Assess completeness
    missing = []
    if not ay_obj:
        missing.append("Academic Year")
    if not dept_obj:
        missing.append("Department")
    if not prog_obj:
        missing.append("Program")
    if not sem_obj:
        missing.append("Semester")

    if missing or ay_obj is None or dept_obj is None or prog_obj is None or sem_obj is None:
        # Construct helpful clarification message
        clarifications = []
        if "Department" in missing:
            clarifications.append("Which department should this timetable be generated for? (e.g. Computer Science, Mechanical, Electrical)")
        if "Semester" in missing:
            clarifications.append("Which semester number would you like to schedule? (e.g. Semester 1, Semester 5)")

        return {
            "resolved": False,
            "scope": None,
            "display": {},
            "missing_parameters": missing,
            "clarification_prompt": " ".join(clarifications),
        }

    valid_ay: AcademicYear = ay_obj
    valid_dept: Department = dept_obj
    valid_prog: Program = prog_obj
    valid_sem: Semester = sem_obj

    # Verify sections exist for this exact scope
    sections = db.query(Section).filter(
        Section.department_id == valid_dept.id,
        Section.program_id == valid_prog.id,
        Section.semester_id == valid_sem.id,
    ).all()

    scope_dict = {
        "academic_year_id": valid_ay.id,
        "department_id": valid_dept.id,
        "program_id": valid_prog.id,
        "semester_id": valid_sem.id,
        "section_ids": [s.id for s in sections] if sections else None,
    }

    sec_names = [s.section_name for s in sections if s.section_name]
    display_dict = {
        "academic_year": valid_ay.name,
        "department": f"{valid_dept.name} ({valid_dept.department_code})",
        "program": valid_prog.program_name,
        "semester": f"Semester {valid_sem.semester_number}",
        "sections_count": str(len(sections)),
        "section_names": ", ".join(sec_names) if sec_names else "None",
    }

    return {
        "resolved": True,
        "scope": scope_dict,
        "display": display_dict,
        "missing_parameters": [],
        "clarification_prompt": None,
    }


def analyze_scheduling_readiness_data(db: Session, scope_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs pre-flight data readiness analysis for the provided GenerationScope.
    Returns:
    - status: READY | READY_WITH_WARNINGS | BLOCKED
    - findings: list of diagnostic findings
    - summary_metrics: counts of loaded entities
    - can_proceed: bool
    """
    try:
        scope = GenerationScope(**scope_dict)
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "can_proceed": False,
            "findings": [f"Invalid scope parameters: {str(exc)}"],
            "summary_metrics": {},
        }

    findings: List[str] = []
    status_str = "READY"

    # 1. Verify sections
    sections = db.query(Section).filter(
        Section.department_id == scope.department_id,
        Section.program_id == scope.program_id,
        Section.semester_id == scope.semester_id,
    ).all()
    section_ids = [s.id for s in sections]
    if not sections:
        findings.append("❌ BLOCKED: No academic sections found for this Department, Program, and Semester.")
        return {
            "status": "BLOCKED",
            "can_proceed": False,
            "findings": findings,
            "summary_metrics": {"sections": 0},
        }

    batches = db.query(Batch).filter(Batch.section_id.in_(section_ids)).all()
    batch_ids = [b.id for b in batches]

    # 2. Verify course assignments
    assignments = db.query(CourseAssignment).filter(
        (CourseAssignment.section_id.in_(section_ids)) | (CourseAssignment.batch_id.in_(batch_ids))
    ).all()
    if not assignments:
        findings.append("❌ BLOCKED: No course assignments configured for sections in this scope.")
        return {
            "status": "BLOCKED",
            "can_proceed": False,
            "findings": findings,
            "summary_metrics": {"sections": len(sections), "assignments": 0},
        }

    course_ids = list(set(a.course_id for a in assignments if a.course_id))
    faculty_ids = list(set(a.faculty_id for a in assignments if a.faculty_id))
    courses = db.query(Course).filter(Course.id.in_(course_ids)).all()

    # 3. Check time slots
    slots = db.query(TimeSlot).all()
    if not slots:
        findings.append("❌ BLOCKED: No time slots defined in the campus space/time register.")
        return {
            "status": "BLOCKED",
            "can_proceed": False,
            "findings": findings,
            "summary_metrics": {"sections": len(sections), "slots": 0},
        }

    # 4. Check rooms and capacities
    rooms = db.query(Room).filter(Room.status == "ACTIVE").all()
    if not rooms:
        findings.append("❌ BLOCKED: No active rooms available for scheduling.")
        return {
            "status": "BLOCKED",
            "can_proceed": False,
            "findings": findings,
            "summary_metrics": {"sections": len(sections), "rooms": 0},
        }

    # 5. Check faculty availability
    availabilities = db.query(FacultyAvailability).filter(FacultyAvailability.faculty_id.in_(faculty_ids)).all()
    if not availabilities:
        findings.append("⚠️ WARNING: No explicit faculty availability preferences registered. Solver will assume standard open availability.")
        status_str = "READY_WITH_WARNINGS"

    # 6. Check lab requirements
    lab_courses = [c for c in courses if c.requires_lab or c.course_type == "LAB"]
    lab_rooms = [r for r in rooms if r.room_type == "LAB"]
    if lab_courses and not lab_rooms:
        findings.append("❌ BLOCKED: Courses require laboratory sessions, but no active LAB rooms are registered.")
        return {
            "status": "BLOCKED",
            "can_proceed": False,
            "findings": findings,
            "summary_metrics": {"sections": len(sections), "lab_rooms": 0},
        }

    findings.append(f"✅ Verified {len(sections)} sections and {len(batches)} batches.")
    findings.append(f"✅ Verified {len(courses)} active courses with {len(assignments)} teaching allocations across {len(faculty_ids)} faculty.")
    findings.append(f"✅ Verified {len(rooms)} active campus rooms ({len(lab_rooms)} labs) and {len(slots)} weekly time slots.")

    return {
        "status": status_str,
        "can_proceed": True,
        "findings": findings,
        "summary_metrics": {
            "sections": len(sections),
            "batches": len(batches),
            "courses": len(courses),
            "assignments": len(assignments),
            "faculty": len(faculty_ids),
            "rooms": len(rooms),
            "slots": len(slots),
        },
    }


def execute_finalize_timetable_data(
    db: Session,
    version_id: int,
    user: User,
) -> Dict[str, Any]:
    """
    Executes authoritative timetable version finalization.
    Enforces ADMIN role check, version status validation (must be VALIDATED),
    audit logging, and persistence verification.
    """
    if user.role != "ADMIN":
        return {
            "success": False,
            "error": "Access denied: Only university Administrators possess the authority to finalize timetable versions.",
        }

    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        return {
            "success": False,
            "error": f"Timetable version #{version_id} was not found.",
        }

    if version.status == "FINALIZED":
        return {
            "success": True,
            "version_id": version.id,
            "version_number": version.version_number,
            "status": "FINALIZED",
            "message": f"Timetable version #{version.id} (v{version.version_number}) is already finalized.",
        }

    if version.status != "VALIDATED":
        return {
            "success": False,
            "error": (
                f"Cannot finalize timetable version #{version_id} because its current status is '{version.status}'. "
                f"Timetables must pass constraint validation (status VALIDATED) before they can be finalized."
            ),
        }

    old_status = version.status
    version.status = "FINALIZED"

    audit = AuditLog(
        user_id=user.id,
        action="TIMETABLE_FINALIZED",
        entity_type="TimetableVersion",
        entity_id=version.id,
        old_value={"status": old_status},
        new_value={"status": "FINALIZED"},
    )
    db.add(audit)
    db.commit()

    # Persistence verification
    refetched = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not refetched or refetched.status != "FINALIZED":
        return {
            "success": False,
            "error": "Persistence verification failed: Timetable version status was not confirmed as FINALIZED in the database.",
        }

    return {
        "success": True,
        "version_id": refetched.id,
        "version_number": refetched.version_number,
        "status": refetched.status,
    }


def execute_publish_timetable_data(
    db: Session,
    version_id: int,
    user: User,
) -> Dict[str, Any]:
    """
    Executes authoritative timetable version publication.
    Enforces ADMIN role check, version status validation (must be FINALIZED),
    audit logging, and persistence verification.
    """
    if user.role != "ADMIN":
        return {
            "success": False,
            "error": "Access denied: Only university Administrators possess the authority to publish timetable versions.",
        }

    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        return {
            "success": False,
            "error": f"Timetable version #{version_id} was not found.",
        }

    if version.status == "PUBLISHED":
        return {
            "success": True,
            "version_id": version.id,
            "version_number": version.version_number,
            "status": "PUBLISHED",
            "published_at": str(version.published_at),
            "message": f"Timetable version #{version.id} (v{version.version_number}) is already published and active campus-wide.",
        }

    if version.status != "FINALIZED":
        return {
            "success": False,
            "error": (
                f"Cannot publish timetable version #{version_id} because its current status is '{version.status}'. "
                f"Versions must be finalized (status FINALIZED) by an Administrator before campus publication."
            ),
        }

    old_status = version.status
    now = datetime.datetime.now(datetime.UTC)
    version.status = "PUBLISHED"
    version.published_at = now

    audit = AuditLog(
        user_id=user.id,
        action="TIMETABLE_PUBLISHED",
        entity_type="TimetableVersion",
        entity_id=version.id,
        old_value={"status": old_status},
        new_value={"status": "PUBLISHED", "published_at": now.isoformat()},
    )
    db.add(audit)
    db.commit()

    # Persistence verification
    refetched = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not refetched or refetched.status != "PUBLISHED" or not refetched.published_at:
        return {
            "success": False,
            "error": "Persistence verification failed: Timetable version status was not confirmed as PUBLISHED in the database.",
        }

    # Trigger authoritative publication notifications
    notify_timetable_published(db=db, version_id=refetched.id)

    return {
        "success": True,
        "version_id": refetched.id,
        "version_number": refetched.version_number,
        "status": refetched.status,
        "published_at": str(refetched.published_at),
    }
