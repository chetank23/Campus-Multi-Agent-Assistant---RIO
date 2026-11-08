from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class TimetableEntryUpdate(BaseModel):
    room_id: Optional[int] = None
    slot_id: Optional[int] = None
    faculty_id: Optional[int] = None

class TimetableEntryResponse(BaseModel):
    id: int
    timetable_id: Optional[int] = None
    version_id: Optional[int] = None
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    semester_id: Optional[int] = None
    section_id: Optional[int] = None
    batch_id: Optional[int] = None
    course_id: Optional[int] = None
    faculty_id: Optional[int] = None
    room_id: Optional[int] = None
    slot_id: Optional[int] = None
    status: str

    model_config = ConfigDict(from_attributes=True)

class TimetableEntryDetailResponse(TimetableEntryResponse):
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    course_type: Optional[str] = None
    faculty_name: Optional[str] = None
    faculty_designation: Optional[str] = None
    faculty_contact: Optional[str] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    day: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    slot_type: Optional[str] = None
    section_name: Optional[str] = None

class TimetableVersionResponse(BaseModel):
    id: int
    academic_year_id: Optional[int] = None
    version_number: Optional[str] = None
    status: Optional[str] = None
    created_by: Optional[int] = None
    approved_by: Optional[int] = None
    created_at: datetime
    published_at: Optional[datetime] = None
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class TimetableVersionDetailResponse(TimetableVersionResponse):
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    academic_year_name: Optional[str] = None
    semester_number: Optional[int] = None
    section_name: Optional[str] = None
    class_teacher_name: Optional[str] = None
    class_teacher_designation: Optional[str] = None
    class_teacher_contact: Optional[str] = None
    timetable_entries: List[TimetableEntryDetailResponse] = []


class PersonalTimetableEntry(BaseModel):
    id: int
    version_id: Optional[int] = None
    version_number: Optional[str] = None
    academic_year_name: Optional[str] = None
    semester_number: Optional[int] = None
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    section_name: Optional[str] = None
    batch_name: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    course_type: Optional[str] = None
    faculty_name: Optional[str] = None
    faculty_designation: Optional[str] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    day: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    slot_type: Optional[str] = None
    status: str
    is_substituted: bool = False
    substitute_faculty_id: Optional[int] = None
    substitute_faculty_name: Optional[str] = None
    original_faculty_name: Optional[str] = None
    substitution_id: Optional[int] = None
    substitution_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FacultyTimetableResponse(BaseModel):
    faculty_id: Optional[int] = None
    faculty_code: Optional[str] = None
    faculty_name: Optional[str] = None
    designation: Optional[str] = None
    department_name: Optional[str] = None
    total_teaching_hours: int = 0
    working_days: Optional[str] = "MON_SAT"
    sections_as_class_teacher: List[str] = []
    entries: List[PersonalTimetableEntry] = []

    model_config = ConfigDict(from_attributes=True)


class StudentTimetableResponse(BaseModel):
    student_id: Optional[int] = None
    student_code: Optional[str] = None
    student_name: Optional[str] = None
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    semester_number: Optional[int] = None
    section_name: Optional[str] = None
    batch_name: Optional[str] = None
    academic_year_name: Optional[str] = None
    admission_batch: Optional[str] = None
    class_teacher_name: Optional[str] = None
    class_teacher_designation: Optional[str] = None
    class_teacher_contact: Optional[str] = None
    total_class_hours: int = 0
    working_days: Optional[str] = "MON_SAT"
    entries: List[PersonalTimetableEntry] = []

    model_config = ConfigDict(from_attributes=True)


class DepartmentTimetableResponse(BaseModel):
    department_id: int
    department_name: str
    department_code: str
    total_entries: int
    entries: List[PersonalTimetableEntry] = []

    model_config = ConfigDict(from_attributes=True)


# ── Canonical Timetable Schemas (Single Timetable per AY + Sem + Section) ──

class CanonicalTimetableResponse(BaseModel):
    id: int
    academic_year_id: int
    semester_id: int
    section_id: int
    academic_year_name: Optional[str] = None
    semester_number: Optional[int] = None
    section_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    status: str = "PUBLISHED"
    working_days: str = "MON_SAT"
    created_at: datetime
    published_at: Optional[datetime] = None
    class_teacher_name: Optional[str] = None
    class_teacher_designation: Optional[str] = None
    class_teacher_contact: Optional[str] = None
    entries: List[TimetableEntryDetailResponse] = []

    model_config = ConfigDict(from_attributes=True)


class TimetablePreviewEntry(BaseModel):
    section_id: int
    section_name: str
    course_assignment_id: int
    course_id: int
    course_code: str
    course_name: str
    course_type: str = "CORE"
    faculty_id: int
    faculty_name: str
    faculty_designation: Optional[str] = None
    faculty_contact: Optional[str] = None
    room_id: int
    room_number: str
    building_name: Optional[str] = None
    slot_id: int
    day: str
    start_time: str
    end_time: str
    slot_type: str = "CLASS"
    hour_type: str = "THEORY"


class TimetablePreviewResponse(BaseModel):
    academic_year_id: int
    semester_id: int
    department_id: int
    academic_year_name: str
    semester_number: int
    department_name: str
    status: str
    is_valid: bool
    can_publish: bool
    blocker_count: int = 0
    warning_count: int = 0
    violations: List[dict] = []
    sections: List[dict] = []
    entries: List[TimetablePreviewEntry] = []
    solve_time_seconds: float = 0.0
    score: Optional[dict] = None
    existing_published: bool = False
    working_days: str = "MON_SAT"


class PublishTimetableRequest(BaseModel):
    academic_year_id: int
    semester_id: int
    department_id: int
    working_days: Optional[str] = "MON_SAT"
    entries: List[TimetablePreviewEntry]


class PublishTimetableResponse(BaseModel):
    success: bool
    message: str
    published_timetables: List[CanonicalTimetableResponse] = []
    total_entries_published: int = 0
