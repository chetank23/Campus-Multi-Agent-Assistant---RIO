from typing import Optional
from pydantic import BaseModel, ConfigDict

class LabBase(BaseModel):
    room_id: int
    lab_name: str
    department_id: int
    computer_count: Optional[int] = None
    equipment: Optional[str] = None
    software: Optional[str] = None

class LabCreate(LabBase):
    pass

class LabUpdate(BaseModel):
    room_id: Optional[int] = None
    lab_name: Optional[str] = None
    department_id: Optional[int] = None
    computer_count: Optional[int] = None
    equipment: Optional[str] = None
    software: Optional[str] = None

class LabResponse(LabBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
