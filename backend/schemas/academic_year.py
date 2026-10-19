from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import date

class AcademicYearBase(BaseModel):
    name: str
    start_date: date
    end_date: date

class AcademicYearCreate(AcademicYearBase):
    pass

class AcademicYearUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class AcademicYearResponse(AcademicYearBase):
    id: int

    model_config = ConfigDict(from_attributes=True)