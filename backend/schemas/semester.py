from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import date

class SemesterBase(BaseModel):
    academic_year_id: int
    semester_number: int
    start_date: date
    end_date: date

class SemesterCreate(SemesterBase):
    pass

class SemesterUpdate(BaseModel):
    academic_year_id: Optional[int] = None
    semester_number: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class SemesterResponse(SemesterBase):
    id: int

    model_config = ConfigDict(from_attributes=True)