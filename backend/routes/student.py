import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from backend.database import get_db
from backend.models.academic import Student, Faculty
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry
from backend.models.space_time import Room, TimeSlot
from backend.schemas.student import StudentCreate, StudentUpdate, StudentResponse, StudentCourseResponse
from backend.schemas.timetable import StudentTimetableResponse, PersonalTimetableEntry
from backend.services.substitution_service import day_matches_date, get_active_substitutions_for_date
from backend.dependencies import get_current_user, require_role, require_department_scope

router = APIRouter(prefix="/students", tags=["Students"])
student_router = APIRouter(prefix="/student", tags=["Student"])

DAY_ORDER = {
    "MON": 1, "MONDAY": 1,
    "TUE": 2, "TUESDAY": 2,
    "WED": 3, "WEDNESDAY": 3,
    "THU": 4, "THURSDAY": 4,
    "FRI": 5, "FRIDAY": 5,
    "SAT": 6, "SATURDAY": 6,
    "SUN": 7, "SUNDAY": 7,
}


@router.get("/", response_model=List[StudentResponse])
def get_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(Student).all()
    elif current_user.role == "FACULTY":
        # Faculty can see students of their department via section? Actually student has department_id directly.
        return db.query(Student).filter(Student.department_id == current_user.department_id).all()
    else:  # STUDENT
        # Students can only see their own profile
        return db.query(Student).filter(Student.user_id == current_user.id).all()


def _get_student_my_timetable_handler(
    academic_year_id: Optional[int] = None,
    date: Optional[datetime.date] = None,
    response: Optional[Response] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("STUDENT")),
) -> StudentTimetableResponse:
    """
    Returns the published timetable entries applicable to the authenticated student's section/batch.
    Arbitrary student IDs or section IDs cannot be passed to circumvent ownership.
    """
    if response:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    stu = (
        db.query(Student)
        .options(
            joinedload(Student.department),
            joinedload(Student.program),
            joinedload(Student.section),
            joinedload(Student.batch),
            joinedload(Student.user),
        )
        .filter(Student.user_id == current_user.id)
        .first()
    )
    if not stu or stu.section_id is None:
        return StudentTimetableResponse(
            student_name=current_user.name,
            total_class_hours=0,
            entries=[],
        )

    # Prefer canonical timetable if one is published for this student's section
    canonical_tt_query = (
        db.query(Timetable)
        .filter(
            Timetable.section_id == stu.section_id,
            Timetable.status == "PUBLISHED",
        )
    )
    if academic_year_id:
        canonical_tt_query = canonical_tt_query.filter(Timetable.academic_year_id == academic_year_id)
    canonical_tt = canonical_tt_query.order_by(Timetable.id.desc()).first()

    if canonical_tt:
        query = (
            db.query(TimetableEntry)
            .filter(
                TimetableEntry.timetable_id == canonical_tt.id,
                TimetableEntry.section_id == stu.section_id,
                TimetableEntry.status != "CANCELLED",
            )
        )
    else:
        query = (
            db.query(TimetableEntry)
            .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
            .filter(
                TimetableVersion.status == "PUBLISHED",
                TimetableEntry.section_id == stu.section_id,
                TimetableEntry.status != "CANCELLED",
            )
        )
        if academic_year_id:
            query = query.filter(TimetableVersion.academic_year_id == academic_year_id)
    if stu.batch_id is not None:
        # Include section-wide entries and student's batch entries
        query = query.filter(
            (TimetableEntry.batch_id == None) | (TimetableEntry.batch_id == stu.batch_id)  # noqa: E711
        )
    else:
        # Only section-wide entries
        query = query.filter(TimetableEntry.batch_id == None)  # noqa: E711

    raw_entries = (
        query.options(
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.faculty).joinedload(Faculty.user),
            joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableEntry.slot),
            joinedload(TimetableEntry.section),
            joinedload(TimetableEntry.batch),
            joinedload(TimetableEntry.department),
            joinedload(TimetableEntry.program),
            joinedload(TimetableEntry.timetable).joinedload(Timetable.academic_year),
            joinedload(TimetableEntry.version).joinedload(TimetableVersion.academic_year),
        )
        .all()
    )

    def sort_key(e: TimetableEntry):
        day_val = e.slot.day.upper() if (e.slot and e.slot.day) else ""
        day_rank = DAY_ORDER.get(day_val, 99)
        time_str = e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else "99:99"
        return (day_rank, time_str)

    sorted_entries = sorted(raw_entries, key=sort_key)

    sub_map = get_active_substitutions_for_date(db, date) if date else {}

    filtered_entries = [e for e in sorted_entries if not date or day_matches_date(e.slot.day if e.slot else None, date)]

    result_entries = []
    total_hours = 0
    for e in filtered_entries:
        slot_type = e.slot.slot_type if e.slot else None
        if slot_type == "CLASS" or slot_type is None:
            total_hours += 1

        sub = sub_map.get(e.id)
        is_sub = sub is not None
        orig_fac_name = e.faculty.user.name if (e.faculty and e.faculty.user) else None
        eff_fac_name = sub.substitute_faculty.user.name if (sub and sub.substitute_faculty and sub.substitute_faculty.user) else orig_fac_name
        sub_name = sub.substitute_faculty.user.name if (sub and sub.substitute_faculty and sub.substitute_faculty.user) else None

        entry_ay = None
        if e.timetable and e.timetable.academic_year:
            entry_ay = e.timetable.academic_year.name
        elif e.version and e.version.academic_year:
            entry_ay = e.version.academic_year.name

        result_entries.append(
            PersonalTimetableEntry(
                id=e.id,
                version_id=e.version_id or (e.timetable_id if e.timetable_id else None),
                version_number=e.version.version_number if e.version else "CANONICAL",
                academic_year_name=entry_ay,
                semester_number=e.semester_id,
                department_name=e.department.name if e.department else None,
                program_name=e.program.program_name if e.program else None,
                section_name=e.section.section_name if e.section else None,
                batch_name=e.batch.batch_name if e.batch else None,
                course_code=e.course.course_code if e.course else None,
                course_name=e.course.course_name if e.course else None,
                course_type=e.course.course_type if e.course else None,
                faculty_name=eff_fac_name,
                faculty_designation=e.faculty.designation if e.faculty else None,
                room_number=e.room.room_number if e.room else None,
                building_name=e.room.building.name if (e.room and e.room.building) else None,
                day=e.slot.day if e.slot else None,
                start_time=e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else None,
                end_time=e.slot.end_time.strftime("%H:%M") if (e.slot and e.slot.end_time) else None,
                slot_type=slot_type,
                status=e.status,
                is_substituted=is_sub,
                original_faculty_name=orig_fac_name if is_sub else None,
                substitute_faculty_id=sub.substitute_faculty_id if sub else None,
                substitute_faculty_name=sub_name,
                substitution_id=sub.id if sub else None,
                substitution_status=sub.status if sub else None,
            )
        )

    ct = stu.section.class_teacher if (stu.section and stu.section.class_teacher) else None
    ct_name = ct.user.name if (ct and ct.user) else None
    ct_desig = ct.designation if ct else None
    ct_contact = ct.contact_number if ct else None
    first_tt = sorted_entries[0].timetable if (sorted_entries and sorted_entries[0].timetable) else None
    first_ver = sorted_entries[0].version if (sorted_entries and sorted_entries[0].version) else None
    if stu.semester and stu.semester.academic_year:
        ay_name = stu.semester.academic_year.name
    elif first_tt and first_tt.academic_year:
        ay_name = first_tt.academic_year.name
    elif first_ver and first_ver.academic_year:
        ay_name = first_ver.academic_year.name
    else:
        ay_name = None
    adm_batch = stu.batch.batch_name if stu.batch else "2023"
    effective_working_days = first_tt.working_days if (first_tt and getattr(first_tt, "working_days", None)) else "MON_SAT"

    return StudentTimetableResponse(
        student_id=stu.id,
        student_code=stu.student_id,
        student_name=current_user.name,
        department_name=stu.department.name if stu.department else None,
        program_name=stu.program.program_name if stu.program else None,
        semester_number=stu.semester_id,
        section_name=stu.section.section_name if stu.section else None,
        batch_name=stu.batch.batch_name if stu.batch else None,
        academic_year_name=ay_name,
        admission_batch=adm_batch,
        class_teacher_name=ct_name,
        class_teacher_designation=ct_desig,
        class_teacher_contact=ct_contact,
        total_class_hours=total_hours,
        working_days=effective_working_days,
        entries=result_entries,
    )


@router.get("/my-timetable", response_model=StudentTimetableResponse)
def get_student_my_timetable_plural(
    academic_year_id: Optional[int] = None,
    date: Optional[datetime.date] = None,
    response: Response = Response(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("STUDENT")),
):
    return _get_student_my_timetable_handler(academic_year_id, date, response, db, current_user)


@student_router.get("/my-timetable", response_model=StudentTimetableResponse)
def get_student_my_timetable_singular(
    academic_year_id: Optional[int] = None,
    date: Optional[datetime.date] = None,
    response: Response = Response(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("STUDENT")),
):
    return _get_student_my_timetable_handler(academic_year_id, date, response, db, current_user)


def _get_student_courses_handler(db: Session, current_user: User) -> List[StudentCourseResponse]:
    stu = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not stu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student profile not found")

    assignments = (
        db.query(CourseAssignment)
        .options(
            joinedload(CourseAssignment.course),
            joinedload(CourseAssignment.faculty).joinedload(Faculty.user),
            joinedload(CourseAssignment.section),
        )
        .filter(CourseAssignment.section_id == stu.section_id)
        .all()
    )
    results = []
    seen_courses = set()
    for ca in assignments:
        if not ca.course or ca.course.id in seen_courses:
            continue
        seen_courses.add(ca.course.id)
        fac_name = ca.faculty.user.name if (ca.faculty and ca.faculty.user) else None
        fac_desig = ca.faculty.designation if ca.faculty else None
        sec_name = ca.section.section_name if ca.section else None
        results.append(
            StudentCourseResponse(
                id=ca.course.id,
                course_code=ca.course.course_code or "",
                course_name=ca.course.course_name or "",
                course_type=ca.course.course_type or "THEORY",
                credits=ca.course.credits or 3,
                faculty_name=fac_name,
                faculty_designation=fac_desig,
                section_name=sec_name,
            )
        )
    return results


@router.get("/my-courses", response_model=List[StudentCourseResponse])
def get_student_courses_plural(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("STUDENT")),
):
    return _get_student_courses_handler(db, current_user)


@student_router.get("/courses", response_model=List[StudentCourseResponse])
def get_student_courses_singular(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("STUDENT")),
):
    return _get_student_courses_handler(db, current_user)


@router.get("/live-status")
@student_router.get("/live-status")
def get_student_live_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("STUDENT")),
):
    """
    Evaluates real-time class status (ongoing, upcoming, completed) for authenticated student.
    """
    from agents.tools.student_tools import get_class_status_data
    return get_class_status_data(db=db, user=current_user)



@router.get("/{student_id}", response_model=StudentResponse)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stu = db.query(Student).filter(Student.id == student_id).first()
    if not stu:
        raise HTTPException(status_code=404, detail="Student not found")
    if current_user.role == "ADMIN":
        return stu
    elif current_user.role == "FACULTY":
        if stu.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return stu
    else:  # STUDENT
        # Student can only view own record
        if stu.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return stu


@router.post("/", response_model=StudentResponse)
def create_student(
    student: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_stu = Student(**student.model_dump())
    db.add(db_stu)
    db.commit()
    db.refresh(db_stu)
    return db_stu


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    student: StudentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_stu = db.query(Student).filter(Student.id == student_id).first()
    if not db_stu:
        raise HTTPException(status_code=404, detail="Student not found")
    for key, value in student.model_dump(exclude_unset=True).items():
        setattr(db_stu, key, value)
    db.commit()
    db.refresh(db_stu)
    return db_stu


@router.delete("/{student_id}")
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_stu = db.query(Student).filter(Student.id == student_id).first()
    if not db_stu:
        raise HTTPException(status_code=404, detail="Student not found")
    db.delete(db_stu)
    db.commit()
    return {"ok": True}