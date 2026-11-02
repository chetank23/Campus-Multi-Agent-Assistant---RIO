from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from backend.database import get_db
from backend.models.academic import Faculty
from backend.models.identity import User
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.space_time import Room, TimeSlot
from backend.schemas.faculty import FacultyCreate, FacultyUpdate, FacultyResponse
from backend.schemas.timetable import FacultyTimetableResponse, PersonalTimetableEntry, DepartmentTimetableResponse
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("FACULTY")),
):
    """
    Returns the published timetable entries assigned to the authenticated faculty member.
    Unpublished drafts, other faculty members' schedules, and non-faculty users are strictly excluded.
    """
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
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.faculty_id == fac.id,
            TimetableEntry.status != "CANCELLED",
        )
    )
    if academic_year_id:
        query = query.filter(TimetableVersion.academic_year_id == academic_year_id)

    raw_entries = (
        query.options(
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableEntry.slot),
            joinedload(TimetableEntry.section),
            joinedload(TimetableEntry.batch),
            joinedload(TimetableEntry.department),
            joinedload(TimetableEntry.program),
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
    total_hours = 0
    for e in sorted_entries:
        slot_type = e.slot.slot_type if e.slot else None
        if slot_type == "CLASS" or slot_type is None:
            total_hours += 1

        result_entries.append(
            PersonalTimetableEntry(
                id=e.id,
                version_id=e.version_id,
                version_number=e.version.version_number if e.version else None,
                academic_year_name=e.version.academic_year.name if (e.version and e.version.academic_year) else None,
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
            )
        )

    return FacultyTimetableResponse(
        faculty_id=fac.id,
        faculty_code=fac.faculty_id,
        faculty_name=current_user.name,
        designation=fac.designation,
        department_name=fac.department.name if fac.department else None,
        total_teaching_hours=total_hours,
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
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.department_id == fac.department_id,
            TimetableEntry.status != "CANCELLED",
        )
    )
    if academic_year_id:
        query = query.filter(TimetableVersion.academic_year_id == academic_year_id)
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
        result_entries.append(
            PersonalTimetableEntry(
                id=e.id,
                version_id=e.version_id,
                version_number=e.version.version_number if e.version else None,
                academic_year_name=e.version.academic_year.name if (e.version and e.version.academic_year) else None,
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
