"""
backend/schemas/notification.py
-------------------------------
Pydantic v2 schemas for the Notification subsystem.
"""

from __future__ import annotations

import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    title: Optional[str] = None
    message: Optional[str] = None
    type: Optional[str] = None
    link: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    is_read: bool = False
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class NotificationMarkReadResponse(BaseModel):
    id: int
    is_read: bool


class NotificationMarkAllReadResponse(BaseModel):
    marked_count: int


class BroadcastAnnouncementRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    message: str = Field(..., min_length=1)
    target_role: Optional[Literal["ALL", "FACULTY", "STUDENT"]] = "ALL"
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    section_id: Optional[int] = None


class FacultyClassUpdateRequest(BaseModel):
    course_id: int
    section_id: int
    update_type: Literal["CANCELLATION", "RESCHEDULE", "ROOM_CHANGE", "ANNOUNCEMENT"]
    title: str = Field(..., min_length=1, max_length=150)
    message: str = Field(..., min_length=1)
