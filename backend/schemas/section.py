from typing import Optional
from pydantic import BaseModel, ConfigDict

class ClassTeacherSummary(BaseModel):
    id: int
    faculty_id: Optional[str] = None
    name: Optional[str] = None
    designation: Optional[str] = None
    contact_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class SectionBase(BaseModel):
    department_id: int
    program_id: int
    semester_id: int
    section_name: str
    student_count: int
    class_teacher_id: Optional[int] = None

class SectionCreate(SectionBase):
    pass

class SectionUpdate(BaseModel):
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    semester_id: Optional[int] = None
    section_name: Optional[str] = None
    student_count: Optional[int] = None
    class_teacher_id: Optional[int] = None

class SectionResponse(SectionBase):
    id: int
    class_teacher: Optional[ClassTeacherSummary] = None

    model_config = ConfigDict(from_attributes=True)