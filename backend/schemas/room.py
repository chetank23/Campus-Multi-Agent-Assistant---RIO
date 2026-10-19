from typing import Optional, Literal
from datetime import date
from pydantic import BaseModel, ConfigDict, Field

RoomType = Literal["CLASSROOM", "LAB", "SEMINAR_HALL", "AUDITORIUM", "MEETING_ROOM"]

class RoomBase(BaseModel):
    building_id: int
    room_number: str
    capacity: int = Field(..., gt=0)
    room_type: RoomType
    floor_number: Optional[int] = None
    department_id: Optional[int] = None
    has_projector: bool = False
    has_smart_board: bool = False
    status: str = "ACTIVE"

class RoomCreate(RoomBase):
    pass

class RoomUpdate(BaseModel):
    building_id: Optional[int] = None
    room_number: Optional[str] = None
    floor_number: Optional[int] = None
    capacity: Optional[int] = Field(None, gt=0)
    room_type: Optional[RoomType] = None
    department_id: Optional[int] = None
    has_projector: Optional[bool] = None
    has_smart_board: Optional[bool] = None
    status: Optional[str] = None

class RoomResponse(RoomBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class RoomAvailabilityRequest(BaseModel):
    date: date
    slot_id: int
