from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import date

class AcademicYearBase(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class AcademicYearCreate(AcademicYearBase):
    name: str
    start_date: date
    end_date: date

class AcademicYearUpdate(AcademicYearBase):
    pass

class AcademicYearResponse(AcademicYearBase):
    id: int

    model_config = ConfigDict(from_attributes=True)