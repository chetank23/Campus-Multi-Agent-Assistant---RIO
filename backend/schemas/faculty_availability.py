from typing import Optional
from pydantic import BaseModel, ConfigDict

class FacultyAvailabilityBase(BaseModel):
    faculty_id: int
    slot_id: int
    availability: str
    preference: int = 0

class FacultyAvailabilityCreate(FacultyAvailabilityBase):
    pass

class FacultyAvailabilityUpdate(BaseModel):
    availability: Optional[str] = None
    preference: Optional[int] = None

class FacultyAvailabilityResponse(FacultyAvailabilityBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
