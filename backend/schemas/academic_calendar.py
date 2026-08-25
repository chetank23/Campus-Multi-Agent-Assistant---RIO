from typing import Optional
from pydantic import BaseModel, ConfigDict
import datetime

class AcademicCalendarBase(BaseModel):
    academic_year_id: int
    date: datetime.date
    event_type: str
    description: Optional[str] = None

class AcademicCalendarCreate(AcademicCalendarBase):
    pass

class AcademicCalendarUpdate(BaseModel):
    date: Optional[datetime.date] = None
    event_type: Optional[str] = None
    description: Optional[str] = None

class AcademicCalendarResponse(AcademicCalendarBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
