from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class TimetableEntryUpdate(BaseModel):
    room_id: Optional[int] = None
    slot_id: Optional[int] = None
    faculty_id: Optional[int] = None

class TimetableEntryResponse(BaseModel):
    id: int
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
