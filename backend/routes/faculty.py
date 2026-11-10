import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from backend.database import get_db
from backend.models.academic import Faculty
from backend.models.identity import User
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry
from backend.models.space_time import Room, TimeSlot
from backend.schemas.faculty import FacultyCreate, FacultyUpdate, FacultyResponse
from backend.schemas.timetable import FacultyTimetableResponse, PersonalTimetableEntry, DepartmentTimetableResponse
from backend.models.substitution import FacultySubstitution
from backend.services.substitution_service import day_matches_date, get_active_substitutions_for_date
from backend.dependencies import get_current_user, require_role

router = APIRouter(prefix="/faculty", tags=["Faculty"])

DAY_ORDER = {
    "MON": 1, "MONDAY": 1,
    "TUE": 2, "TUESDAY": 2,
    "WED": 3, "WEDNESDAY": 3,
    "THU": 4, "THURSDAY": 4,
    "FRI": 5, "FRIDAY": 5,
    "SAT": 6, "SATURDAY": 6,
    "SUN": 7, "SUNDAY": 7,
}


def _to_response(fac: Faculty) -> FacultyResponse:
    """Convert a Faculty ORM object to FacultyResponse, populating the joined User name."""
    resp = FacultyResponse.model_validate(fac)
    if fac.user:
        resp.name = fac.user.name
    return resp


@router.get("", response_model=List[FacultyResponse], include_in_schema=False)
@router.get("/", response_model=List[FacultyResponse])
def get_faculty_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Faculty).options(joinedload(Faculty.user))
    if current_user.role == "ADMIN":
        rows = q.all()
    elif current_user.role == "FACULTY":
        rows = q.filter(Faculty.department_id == current_user.department_id).all()
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return [_to_response(f) for f in rows]


@router.get("/my-timetable", response_model=FacultyTimetableResponse)
def get_faculty_my_timetable(
    academic_year_id: Optional[int] = None,
    date: Optional[datetime.date] = None,
    response: Response = Response(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("FACULTY")),
):
    """
    Returns the published timetable entries assigned to the authenticated faculty member.
    Unpublished drafts, other faculty members' schedules, and non-faculty users are strictly excluded.
    """
    if response:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    fac = (
        db.query(Faculty)
        .options(joinedload(Faculty.department), joinedload(Faculty.user))
        .filter(Faculty.user_id == current_user.id)
        .first()
    )
    if not fac:
        return FacultyTimetableResponse(
            faculty_name=current_user.name,
            total_teaching_hours=0,
            entries=[],
        )

    query = (
        db.query(TimetableEntry)
        .outerjoin(Timetable, TimetableEntry.timetable_id == Timetable.id)
        .outerjoin(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            ((Timetable.id != None) & (Timetable.status == "PUBLISHED")) |  # noqa: E711
            ((TimetableEntry.timetable_id == None) & (TimetableVersion.id != None) & (TimetableVersion.status == "PUBLISHED")),  # noqa: E711
            TimetableEntry.faculty_id == fac.id,
            TimetableEntry.status != "CANCELLED",
        )
    )
    if academic_year_id:
        query = query.filter(
            (Timetable.academic_year_id == academic_year_id) |
            (TimetableVersion.academic_year_id == academic_year_id)
        )

    raw_entries = (
        query.options(
            joinedload(TimetableEntry.course),
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

    # If date is specified, filter and overlay date-specific substitutions
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
                faculty_name=current_user.name,
                faculty_designation=fac.designation,
                room_number=e.room.room_number if e.room else None,
                building_name=e.room.building.name if (e.room and e.room.building) else None,
                day=e.slot.day if e.slot else None,
                start_time=e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else None,
                end_time=e.slot.end_time.strftime("%H:%M") if (e.slot and e.slot.end_time) else None,
                slot_type=slot_type,
                status=e.status,
                is_substituted=is_sub,
                substitute_faculty_id=sub.substitute_faculty_id if sub else None,
                substitute_faculty_name=sub_name,
                substitution_id=sub.id if sub else None,
                substitution_status=sub.status if sub else None,
            )
        )

    # If date is specified, also append classes this faculty is covering as substitute
    if date:
        covering_subs = (
            db.query(FacultySubstitution)
            .options(
                joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
                joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
                joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
                joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
                joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
                joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
                joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
            )
            .filter(
                FacultySubstitution.substitution_date == date,
                FacultySubstitution.substitute_faculty_id == fac.id,
                FacultySubstitution.status == "APPROVED",
            )
            .all()
        )
        for cs in covering_subs:
            ce = cs.timetable_entry
            if not ce:
                continue
            orig_fac_name = cs.original_faculty.user.name if (cs.original_faculty and cs.original_faculty.user) else "Regular Faculty"
            result_entries.append(
                PersonalTimetableEntry(
                    id=ce.id,
                    version_id=ce.version_id,
                    version_number=ce.version.version_number if ce.version else None,
                    academic_year_name=ce.version.academic_year.name if (ce.version and ce.version.academic_year) else None,
                    semester_number=ce.semester_id,
                    department_name=ce.department.name if ce.department else None,
                    program_name=ce.program.program_name if ce.program else None,
                    section_name=ce.section.section_name if ce.section else None,
                    batch_name=ce.batch.batch_name if ce.batch else None,
                    course_code=ce.course.course_code if ce.course else None,
                    course_name=ce.course.course_name if ce.course else None,
                    course_type=ce.course.course_type if ce.course else None,
                    faculty_name=current_user.name,
                    faculty_designation=fac.designation,
                    room_number=ce.room.room_number if ce.room else None,
                    building_name=ce.room.building.name if (ce.room and ce.room.building) else None,
                    day=ce.slot.day if ce.slot else None,
                    start_time=ce.slot.start_time.strftime("%H:%M") if (ce.slot and ce.slot.start_time) else None,
                    end_time=ce.slot.end_time.strftime("%H:%M") if (ce.slot and ce.slot.end_time) else None,
                    slot_type=ce.slot.slot_type if ce.slot else None,
                    status=ce.status,
                    is_substituted=True,
                    original_faculty_name=orig_fac_name,
                    substitute_faculty_id=fac.id,
                    substitute_faculty_name=current_user.name,
                    substitution_id=cs.id,
                    substitution_status=cs.status,
                )
            )
        result_entries.sort(key=lambda x: x.start_time or "00:00")

    ct_sections = [s.section_name for s in fac.sections_as_class_teacher if s.section_name]
    first_tt = sorted_entries[0].timetable if (sorted_entries and sorted_entries[0].timetable) else None
    effective_working_days = first_tt.working_days if (first_tt and getattr(first_tt, "working_days", None)) else "MON_SAT"

    return FacultyTimetableResponse(
        faculty_id=fac.id,
        faculty_code=fac.faculty_id,
        faculty_name=current_user.name,
        designation=fac.designation,
        department_name=fac.department.name if fac.department else None,
        total_teaching_hours=total_hours,
        working_days=effective_working_days,
        sections_as_class_teacher=ct_sections,
        entries=result_entries,
    )


@router.get("/department-timetable", response_model=DepartmentTimetableResponse)
def get_faculty_department_timetable(
    academic_year_id: Optional[int] = None,
    section_id: Optional[int] = None,
    semester_id: Optional[int] = None,
    day: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("FACULTY")),
):
    """
    Returns published timetable entries for the authenticated faculty member's department.
    Strictly isolated: faculty cannot see entries of other departments.
    """
    fac = (
        db.query(Faculty)
        .options(joinedload(Faculty.department))
        .filter(Faculty.user_id == current_user.id)
        .first()
    )
    if not fac or not fac.department_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faculty is not assigned to a department.",
        )

    dept = fac.department
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faculty department record not found.",
        )
    query = (
        db.query(TimetableEntry)
        .outerjoin(Timetable, TimetableEntry.timetable_id == Timetable.id)
        .outerjoin(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            ((Timetable.id != None) & (Timetable.status == "PUBLISHED")) |  # noqa: E711
            ((TimetableVersion.id != None) & (TimetableVersion.status == "PUBLISHED")),  # noqa: E711
            TimetableEntry.department_id == fac.department_id,
            TimetableEntry.status != "CANCELLED",
        )
    )
    if academic_year_id:
        query = query.filter(
            (Timetable.academic_year_id == academic_year_id) |
            (TimetableVersion.academic_year_id == academic_year_id)
        )
    if section_id:
        query = query.filter(TimetableEntry.section_id == section_id)
    if semester_id:
        query = query.filter(TimetableEntry.semester_id == semester_id)
    if day:
        query = query.join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id).filter(TimeSlot.day.ilike(day.strip()))

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
    result_entries = []
    for e in sorted_entries:
        fac_name = e.faculty.user.name if (e.faculty and e.faculty.user) else None
        fac_desig = e.faculty.designation if e.faculty else None
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
                department_name=dept.name,
                program_name=e.program.program_name if e.program else None,
                section_name=e.section.section_name if e.section else None,
                batch_name=e.batch.batch_name if e.batch else None,
                course_code=e.course.course_code if e.course else None,
                course_name=e.course.course_name if e.course else None,
                course_type=e.course.course_type if e.course else None,
                faculty_name=fac_name,
                faculty_designation=fac_desig,
                room_number=e.room.room_number if e.room else None,
                building_name=e.room.building.name if (e.room and e.room.building) else None,
                day=e.slot.day if e.slot else None,
                start_time=e.slot.start_time.strftime("%H:%M") if (e.slot and e.slot.start_time) else None,
                end_time=e.slot.end_time.strftime("%H:%M") if (e.slot and e.slot.end_time) else None,
                slot_type=e.slot.slot_type if e.slot else None,
                status=e.status,
            )
        )

    return DepartmentTimetableResponse(
        department_id=dept.id,
        department_name=dept.name,
        department_code=dept.department_code,
        total_entries=len(result_entries),
        entries=result_entries,
    )


@router.get("/live-status")
def get_faculty_live_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("FACULTY")),
):
    """
    Evaluates real-time teaching status (ongoing, upcoming, completed) for authenticated faculty.
    """
    from agents.tools.student_tools import get_class_status_data
    return get_class_status_data(db=db, user=current_user)


@router.get("/{faculty_id}", response_model=FacultyResponse)
def get_faculty(
    faculty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fac = db.query(Faculty).options(joinedload(Faculty.user)).filter(Faculty.id == faculty_id).first()
    if not fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    if current_user.role == "ADMIN":
        return _to_response(fac)
    elif current_user.role == "FACULTY":
        if fac.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return _to_response(fac)
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.post("/", response_model=FacultyResponse)
def create_faculty(
    faculty: FacultyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_fac = Faculty(**faculty.model_dump())
    db.add(db_fac)
    db.commit()
    db.refresh(db_fac)
    # Re-fetch with joined user for the response
    refetched = db.query(Faculty).options(joinedload(Faculty.user)).filter(Faculty.id == db_fac.id).first()
    if not refetched:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created faculty")
    return _to_response(refetched)

@router.put("/{faculty_id}", response_model=FacultyResponse)
def update_faculty(
    faculty_id: int,
    faculty: FacultyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_fac = db.query(Faculty).filter(Faculty.id == faculty_id).first()
    if not db_fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    for key, value in faculty.model_dump(exclude_unset=True).items():
        setattr(db_fac, key, value)
    db.commit()
    refetched = db.query(Faculty).options(joinedload(Faculty.user)).filter(Faculty.id == faculty_id).first()
    if not refetched:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return _to_response(refetched)

@router.delete("/{faculty_id}")
def delete_faculty(
    faculty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_fac = db.query(Faculty).filter(Faculty.id == faculty_id).first()
    if not db_fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    db.delete(db_fac)
    db.commit()
    return {"ok": True}
