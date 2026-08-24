from typing import Optional
from pydantic import BaseModel, ConfigDict

class SectionBase(BaseModel):
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    semester_id: Optional[int] = None
    section_name: Optional[str] = None
    student_count: Optional[int] = None

class SectionCreate(SectionBase):
    department_id: int
    program_id: int
    semester_id: int
    section_name: str
    student_count: int

class SectionUpdate(SectionBase):
    pass

class SectionResponse(SectionBase):
    id: int

    model_config = ConfigDict(from_attributes=True)