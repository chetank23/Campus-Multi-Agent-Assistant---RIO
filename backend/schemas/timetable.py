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
    timetable_entries: List[TimetableEntryResponse] = []
