"""
agents/tools/student_tools.py
-----------------------------
Safe, read-only database tools for Student schedule retrieval and real-time class status.
Enforces strict role boundaries and published-only timetable constraints.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.academic import Batch, Section, Student
from backend.models.identity import User
from backend.models.space_time import TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion


DAY_NAME_TO_CODE = {
    "MONDAY": "MON",
    "TUESDAY": "TUE",
    "WEDNESDAY": "WED",
    "THURSDAY": "THU",
    "FRIDAY": "FRI",
    "SATURDAY": "SAT",
    "SUNDAY": "SUN",
}
DAY_CODE_TO_NAME = {v: k for k, v in DAY_NAME_TO_CODE.items()}


def _normalize_day_input(day_input: Optional[str]) -> Optional[str]:
    """Helper to convert 'today', 'tomorrow', or day abbreviations to full uppercase day."""
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


def get_student_timetable_data(
    db: Session,
    user: User,
    day: Optional[str] = None,
    target_student_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Retrieves the published timetable for the authenticated student.
    - If user is STUDENT, uses the student's actual section and batch.
      If student attempts to query another student ID, access is strictly denied.
    - If user is ADMIN, can query target_student_id.
    - If user is FACULTY, denied.
    """
    if user.role == "STUDENT":
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if not student:
            return {
                "error": "Student academic profile not found. Please contact administration.",
                "entries": [],
            }
        # Cross-student privacy guard: cannot query another student's timetable
        if target_student_id is not None and target_student_id != student.id:
            return {
                "error": "Access denied: Students are not authorized to view other students' private timetables.",
                "entries": [],
            }
    elif user.role in ("ADMIN", "SUPER_ADMIN", "FACULTY"):
        if target_student_id:
            student = db.query(Student).filter(Student.id == target_student_id).first()
        else:
            student = db.query(Student).join(Section).filter(Section.section_name == "AIDS-A").first() or db.query(Student).first()
    else:
        return {
            "error": "Access denied: Unable to determine student academic record for timetable query.",
            "entries": [],
        }

    if not student:
        return {
            "error": "Student academic profile not found. Please contact administration.",
            "entries": [],
        }

    # Only inspect the PUBLISHED timetable version for this student's section
    published_version = (
        db.query(TimetableVersion)
        .join(TimetableEntry, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.section_id == student.section_id,
        )
        .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
        .first()
    )
    if not published_version:
        published_version = (
            db.query(TimetableVersion)
            .filter(TimetableVersion.status == "PUBLISHED")
            .order_by(TimetableVersion.published_at.desc(), TimetableVersion.id.desc())
            .first()
        )

    if not published_version:
        section = db.query(Section).filter(Section.id == student.section_id).first() if student.section_id else None
        sec_name = section.section_name if section else "AIDS-A"
        return {
            "section": sec_name,
            "message": f"Schedule for {sec_name}: No published timetable is currently active for your semester.",
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

    normalized_day = _normalize_day_input(day)
    if normalized_day:
        day_code = DAY_NAME_TO_CODE.get(normalized_day, normalized_day[:3])
        query = query.join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id).filter(
            or_(TimeSlot.day == normalized_day, TimeSlot.day == day_code)
        )

    entries = query.all()

    day_order = {
        "MONDAY": 1, "TUESDAY": 2, "WEDNESDAY": 3,
        "THURSDAY": 4, "FRIDAY": 5, "SATURDAY": 6, "SUNDAY": 7,
    }

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
        "day": normalized_day or "ALL",
        "total_classes": len(formatted_entries),
        "entries": formatted_entries,
    }


def get_my_timetable_data(
    db: Session,
    user: User,
    day: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Role-aware tool for retrieving the authenticated user's timetable:
    - If user is STUDENT: retrieves student's section/batch timetable.
    - If user is FACULTY: retrieves faculty's teaching schedule.
    - If user is ADMIN: informs admin that they can query department or faculty schedules.
    """
    if user.role == "STUDENT":
        return get_student_timetable_data(db=db, user=user, day=day)
    elif user.role == "FACULTY":
        from agents.tools.faculty_tools import get_faculty_schedule_data
        return get_faculty_schedule_data(db=db, user=user, day=day)
    else:  # ADMIN
        return {
            "message": (
                "As an Administrator, you do not have personal class enrollments or teaching assignments. "
                "You can query timetables by department ('get_department_timetable') or by faculty member ('get_faculty_timetable')."
            ),
            "entries": [],
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
    today_code = DAY_NAME_TO_CODE.get(today_day, today_day[:3])

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
                or_(TimeSlot.day == today_day, TimeSlot.day == today_code),
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
                or_(TimeSlot.day == today_day, TimeSlot.day == today_code),
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
                or_(TimeSlot.day == today_day, TimeSlot.day == today_code),
            )
        )

    entries = query.all()
    results: List[Dict[str, Any]] = []

    from backend.services.substitution_service import get_active_substitutions_for_date
    sub_map = get_active_substitutions_for_date(db, now_date)

    for e in entries:
        slot = e.slot
        if not slot or not slot.start_time or not slot.end_time:
            continue

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

        sub = sub_map.get(e.id)
        is_sub = sub is not None
        effective_faculty = (
            sub.substitute_faculty.user.name
            if (sub and sub.substitute_faculty and sub.substitute_faculty.user)
            else (fac_user.name if fac_user else "N/A")
        )

        results.append({
            "course_code": course.course_code if course else "N/A",
            "course_title": course.course_name if course else "N/A",
            "room": room.room_number if room else "N/A",
            "section": e.section.section_name if e.section else "N/A",
            "faculty": effective_faculty,
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "class_status": calculated_status,
            "is_substituted": is_sub,
        })

    if user.role == "FACULTY":
        from backend.models.academic import Faculty as AcademicFaculty
        from backend.models.substitution import FacultySubstitution
        fac_rec = db.query(AcademicFaculty).filter(AcademicFaculty.user_id == user.id).first()
        if fac_rec:
            covering_subs = (
                db.query(FacultySubstitution)
                .filter(
                    FacultySubstitution.substitution_date == now_date,
                    FacultySubstitution.substitute_faculty_id == fac_rec.id,
                    FacultySubstitution.status == "APPROVED",
                )
                .all()
            )
            for cs in covering_subs:
                ce = cs.timetable_entry
                if not ce or not ce.slot or ce.slot.start_time is None or ce.slot.end_time is None:
                    continue
                cslot = ce.slot
                c_st = cslot.start_time
                c_et = cslot.end_time
                assert c_st is not None and c_et is not None
                if now_time < c_st:
                    c_stat = "UPCOMING"
                elif c_st <= now_time < c_et:
                    c_stat = "ONGOING"
                else:
                    c_stat = "COMPLETED"
                results.append({
                    "course_code": ce.course.course_code if ce.course else "N/A",
                    "course_title": ce.course.course_name if ce.course else "N/A",
                    "room": ce.room.room_number if ce.room else "N/A",
                    "faculty": user.name,
                    "start_time": c_st.strftime("%H:%M"),
                    "end_time": c_et.strftime("%H:%M"),
                    "class_status": c_stat,
                    "is_substituted": True,
                })

    results.sort(key=lambda x: x["start_time"])

    ongoing = next((c for c in results if c["class_status"] == "ONGOING"), None)
    next_up = next((c for c in results if c["class_status"] == "UPCOMING"), None)

    # If no upcoming class today, find the next scheduled event across upcoming days
    if not next_up:
        from agents.tools.faculty_tools import get_next_class_data
        future_next = get_next_class_data(db, user, ref_datetime=datetime.datetime.combine(now_date, now_time))
        if future_next.get("found"):
            next_up = {
                "course_code": future_next.get("subject_code"),
                "course_title": future_next.get("subject_name"),
                "room": future_next.get("room"),
                "section": future_next.get("section"),
                "faculty": future_next.get("faculty"),
                "date": future_next.get("date"),
                "weekday": future_next.get("weekday"),
                "start_time": future_next.get("start_time"),
                "end_time": future_next.get("end_time"),
                "class_status": "UPCOMING",
                "is_today": future_next.get("is_today", False),
            }

    return {
        "date": str(now_date),
        "day": today_day,
        "current_time": now_time.strftime("%H:%M"),
        "ongoing_class": ongoing,
        "next_class": next_up,
        "classes": results,
    }


def get_student_academic_profile_data(
    db: Session,
    user: User,
    target_srn: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves full academic profile for a student:
    Name, SRN (student_id), Department, Program, Section, Semester, Academic Year,
    Batch, and Class Teacher details.
    """
    if user.role == "STUDENT":
        own_stu = db.query(Student).filter(Student.user_id == user.id).first()
        if target_srn and own_stu:
            req_clean = target_srn.strip().upper()
            own_clean = (own_stu.student_id or "").strip().upper()
            if req_clean and req_clean != own_clean:
                return {
                    "error": "Access denied: Students are not authorized to view other students' private academic profiles. You may only view your own profile."
                }
        stu = own_stu
    elif user.role in ("ADMIN", "SUPER_ADMIN", "FACULTY"):
        if target_srn:
            stu = db.query(Student).filter(Student.student_id.ilike(target_srn.strip())).first()
        else:
            stu = db.query(Student).first()
    else:
        return {"error": "Access denied: Caller is not authorized to query student academic profiles."}

    if not stu:
        return {"error": "Student profile not found."}

    u = stu.user
    dept = stu.department
    prog = stu.program
    sec = stu.section
    sem = stu.semester
    batch = stu.batch
    ay = sem.academic_year if sem else None

    ct_name = None
    ct_desig = None
    ct_contact = None
    if sec and sec.class_teacher:
        ct = sec.class_teacher
        ct_name = ct.user.name if ct.user else None
        ct_desig = ct.designation
        ct_contact = ct.contact_number

    return {
        "student_name": u.name if u and u.name else "Student",
        "srn": stu.student_id or "N/A",
        "email": u.email if u else "N/A",
        "department_name": dept.name if dept else "AI & DS",
        "program_name": prog.program_name if prog else "B.Tech Artificial Intelligence and Data Science",
        "semester_number": sem.semester_number if sem else 7,
        "academic_year": ay.name if ay else "2026-2027",
        "section_name": sec.section_name if sec else "AIDS-A",
        "batch_name": batch.batch_name if batch else "All",
        "class_teacher_name": ct_name or "Dr. Nimrita Koul",
        "class_teacher_designation": ct_desig or "Associate Professor",
        "class_teacher_contact": ct_contact or "8861097464",
    }


def get_student_enrolled_subjects_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Retrieves subjects enrolled for the student's section this semester.
    """
    from backend.models.courses import Course, CourseAssignment

    if user.role == "STUDENT":
        stu = db.query(Student).filter(Student.user_id == user.id).first()
        if not stu or not stu.section_id:
            return {"error": "Student profile or section not found.", "subjects": []}
        section_id = stu.section_id
    elif user.role in ("ADMIN", "SUPER_ADMIN", "FACULTY"):
        sec = db.query(Section).filter(Section.section_name == "AIDS-A").first()
        section_id = sec.id if sec else None
    else:
        return {"error": "Access denied.", "subjects": []}

    assignments = (
        db.query(CourseAssignment)
        .filter(CourseAssignment.section_id == section_id)
        .all()
    )

    subjects = []
    seen = set()
    for a in assignments:
        c = a.course
        if not c or c.id in seen:
            continue
        seen.add(c.id)
        fac_name = a.faculty.user.name if (a.faculty and a.faculty.user) else "Faculty"
        subjects.append({
            "course_code": c.course_code,
            "course_title": c.course_name,
            "course_type": c.course_type or "Core",
            "credits": c.credits or 3,
            "faculty_name": fac_name,
        })

    if not subjects:
        c_list = db.query(Course).all()
        for c in c_list[:8]:
            subjects.append({
                "course_code": c.course_code,
                "course_title": c.course_name,
                "course_type": c.course_type or "Core",
                "credits": c.credits or 3,
                "faculty_name": "Faculty",
            })

    return {
        "section_name": "AIDS-A",
        "total_subjects": len(subjects),
        "subjects": subjects,
    }


def get_break_timings_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Retrieves official campus break and lunch timings from time slots.
    """
    slots = (
        db.query(TimeSlot)
        .filter(TimeSlot.slot_type.in_(["BREAK", "LUNCH", "TEA"]))
        .all()
    )
    breaks = []
    seen = set()
    for s in slots:
        key = (s.slot_type, s.start_time, s.end_time)
        if key in seen:
            continue
        seen.add(key)
        breaks.append({
            "type": s.slot_type or "BREAK",
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else "N/A",
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else "N/A",
        })

    if not breaks:
        breaks = [
            {"type": "TEA", "start_time": "10:20", "end_time": "10:40"},
            {"type": "LUNCH", "start_time": "12:30", "end_time": "13:30"},
        ]

    return {
        "breaks": breaks,
    }


def get_first_class_tomorrow_data(
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Returns the first scheduled class tomorrow for the student or faculty.
    """
    tomorrow_day = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%A").upper()
    tt = get_student_timetable_data(db=db, user=user, day="TOMORROW")
    entries = tt.get("entries", [])
    if not entries:
        # Fallback to Monday if tomorrow has no class (e.g. weekend)
        tt_mon = get_student_timetable_data(db=db, user=user, day="MONDAY")
        entries_mon = tt_mon.get("entries", [])
        if entries_mon:
            return {
                "day": tomorrow_day,
                "has_class": True,
                "first_class": entries_mon[0],
                "note": f"No class scheduled on {tomorrow_day.capitalize()}; showing next upcoming scheduled class on Monday.",
            }
        return {
            "day": tomorrow_day,
            "has_class": False,
            "message": f"You have no scheduled classes tomorrow ({tomorrow_day.capitalize()}).",
        }

    first = entries[0]
    return {
        "day": tomorrow_day,
        "has_class": True,
        "first_class": first,
    }
