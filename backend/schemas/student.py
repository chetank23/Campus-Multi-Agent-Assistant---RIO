from typing import Optional
from pydantic import BaseModel, ConfigDict

class StudentBase(BaseModel):
    user_id: int
    student_id: str
    department_id: int
    program_id: int
    semester_id: int
    section_id: int
    batch_id: int

class StudentCreate(StudentBase):
    pass

class StudentUpdate(BaseModel):
    user_id: Optional[int] = None
    student_id: Optional[str] = None
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    semester_id: Optional[int] = None
    section_id: Optional[int] = None
    batch_id: Optional[int] = None

class StudentResponse(StudentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class StudentCourseResponse(BaseModel):
    id: int
    course_code: str
    course_name: str
    course_type: str
    credits: int
    faculty_name: Optional[str] = None
    faculty_designation: Optional[str] = None
    section_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
