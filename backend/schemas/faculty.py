from typing import Optional
from pydantic import BaseModel, ConfigDict

class FacultyBase(BaseModel):
    user_id: int
    faculty_id: str
    department_id: int
    designation: str
    contact_number: Optional[str] = None
    max_weekly_load: Optional[int] = 16

class FacultyCreate(FacultyBase):
    pass

class FacultyUpdate(BaseModel):
    user_id: Optional[int] = None
    faculty_id: Optional[str] = None
    department_id: Optional[int] = None
    designation: Optional[str] = None
    contact_number: Optional[str] = None
    max_weekly_load: Optional[int] = None

class FacultyResponse(FacultyBase):
    id: int
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
