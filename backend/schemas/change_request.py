from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


RequestType = Literal[
    "TIMETABLE_CHANGE",
    "RESOURCE_REQUEST",
    "FACULTY_AVAILABILITY_CHANGE",
    "ROOM_CHANGE",
]


class ChangeRequestCreate(BaseModel):
    request_type: RequestType
    related_entity_id: Optional[int] = Field(default=None, gt=0)
    reason: str = Field(min_length=5, max_length=4000)


class ChangeRequestReview(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    review_note: Optional[str] = Field(default=None, max_length=2000)


class ChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requested_by: Optional[int]
    request_type: Optional[str]
    related_entity_id: Optional[int]
    reason: Optional[str]
    status: str
    reviewed_by: Optional[int]
    created_at: datetime
    review_note: Optional[str] = None
