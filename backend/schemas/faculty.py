from typing import Optional
from pydantic import BaseModel, ConfigDict

class FacultyBase(BaseModel):
    user_id: Optional[int] = None
    faculty_id: Optional[str] = None
    department_id: Optional[int] = None
    designation: Optional[str] = None
    max_weekly_load: Optional[int] = 16

class FacultyCreate(FacultyBase):
    user_id: int
    faculty_id: str
    department_id: int
    designation: str

class FacultyUpdate(FacultyBase):
    pass

class FacultyResponse(FacultyBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
