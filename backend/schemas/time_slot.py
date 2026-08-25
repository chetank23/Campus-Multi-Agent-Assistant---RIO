from typing import Optional
from pydantic import BaseModel, ConfigDict
import datetime

class TimeSlotBase(BaseModel):
    day: str
    start_time: datetime.time
    end_time: datetime.time
    slot_type: str

class TimeSlotCreate(TimeSlotBase):
    pass

class TimeSlotUpdate(BaseModel):
    day: Optional[str] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    slot_type: Optional[str] = None

class TimeSlotResponse(TimeSlotBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
