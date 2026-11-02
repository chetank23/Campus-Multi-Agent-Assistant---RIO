"""
backend/schemas/events.py
-------------------------
Pydantic v2 schemas for:
1. Coordinator capabilities (assignment, revocation, listing)
2. Club management (creation, update, detail)
3. Campus Events & Club Activities (creation, update, approval, venue check, responses)
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# 1. Coordinator Capabilities Schemas
# ---------------------------------------------------------------------------

class CapabilityAssignRequest(BaseModel):
    user_id: int
    capability: Literal["EVENT_COORDINATOR", "CLUB_COORDINATOR", "EVENT_DIRECT_PUBLISH"]
    scope_type: Literal["GLOBAL", "CLUB", "DEPARTMENT", "EVENT"] = "GLOBAL"
    scope_id: Optional[int] = None
    starts_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None


class CapabilityRevokeRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)


class CapabilityResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_email: str
    user_role: str
    capability: str
    scope_type: str
    scope_id: Optional[int] = None
    scope_name: Optional[str] = None
    is_active: bool
    starts_at: Optional[str] = None
    expires_at: Optional[str] = None
    assigned_by: Optional[int] = None
    assigned_by_name: Optional[str] = None
    revocation_reason: Optional[str] = None
    created_at: str


# ---------------------------------------------------------------------------
# 2. Club Schemas
# ---------------------------------------------------------------------------

class ClubCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=30)
    category: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None


class ClubUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    category: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = None
    status: Optional[Literal["ACTIVE", "INACTIVE"]] = None


class ClubCoordinatorItem(BaseModel):
    capability_id: int
    user_id: int
    name: str
    email: str
    role: str
    is_active: bool
    has_direct_publish: bool = False
    assigned_at: str


class ClubResponse(BaseModel):
    id: int
    name: str
    code: str
    category: str
    description: Optional[str] = None
    status: str
    coordinators: List[ClubCoordinatorItem] = []
    activities_count: int = 0
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# 3. Campus Events & Activities Schemas
# ---------------------------------------------------------------------------

class EventCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    category: str = Field(
        ...,
        description="SEMINAR, WORKSHOP, GUEST_LECTURE, TECH_TALK, COMPETITION, HACKATHON, CULTURAL, SPORTS, INSTITUTIONAL, CLUB_ACTIVITY, OTHER",
    )
    club_id: Optional[int] = None
    organizer_name: Optional[str] = None
    start_time: datetime.datetime
    end_time: datetime.datetime
    timezone: str = "Asia/Kolkata"

    building_id: Optional[int] = None
    room_id: Optional[int] = None
    venue_name: Optional[str] = None

    is_online: bool = False
    online_link: Optional[str] = None

    target_audience: Literal["ALL", "STUDENT", "FACULTY", "DEPARTMENT_ONLY", "MEMBERS_ONLY"] = "ALL"
    target_department_id: Optional[int] = None
    target_program_id: Optional[int] = None
    target_batch_id: Optional[int] = None
    target_year: Optional[int] = None

    instructions: Optional[str] = None
    requires_approval: bool = True

    @model_validator(mode="after")
    def validate_times(self) -> "EventCreateRequest":
        if self.end_time <= self.start_time:
            raise ValueError("Event end_time must be strictly after start_time.")
        return self


class EventUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = None
    category: Optional[str] = None
    organizer_name: Optional[str] = None
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    building_id: Optional[int] = None
    room_id: Optional[int] = None
    venue_name: Optional[str] = None
    is_online: Optional[bool] = None
    online_link: Optional[str] = None
    target_audience: Optional[Literal["ALL", "STUDENT", "FACULTY", "DEPARTMENT_ONLY", "MEMBERS_ONLY"]] = None
    target_department_id: Optional[int] = None
    target_program_id: Optional[int] = None
    target_batch_id: Optional[int] = None
    target_year: Optional[int] = None
    instructions: Optional[str] = None
    requires_approval: Optional[bool] = None
    version: Optional[int] = None


class EventApprovalRequest(BaseModel):
    action: Literal["APPROVE", "REJECT"]
    reason: Optional[str] = None
    approval_notes: Optional[str] = None


class EventCancelRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)


class EventVenueConflictItem(BaseModel):
    conflict_type: str  # 'TIMETABLE_CLASS', 'RESOURCE_BOOKING', 'CAMPUS_EVENT'
    conflict_id: int
    title: str
    start_time: str
    end_time: str
    details: Optional[str] = None
    type: Optional[str] = None
    reason: Optional[str] = None


class EventVenueCheckRequest(BaseModel):
    room_id: int
    start_time: datetime.datetime
    end_time: datetime.datetime
    exclude_event_id: Optional[int] = None


class EventVenueCheckResponse(BaseModel):
    room_id: int
    room_number: str
    building_name: str
    is_available: bool
    conflicts: List[EventVenueConflictItem] = []


class EventResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    category: str
    club_id: Optional[int] = None
    club_name: Optional[str] = None
    organizer_name: Optional[str] = None
    coordinator_id: int
    coordinator_name: str
    coordinator_email: str
    start_time: str
    end_time: str
    timezone: str
    building_id: Optional[int] = None
    building_name: Optional[str] = None
    room_id: Optional[int] = None
    room_number: Optional[str] = None
    venue_name: Optional[str] = None
    is_online: bool
    online_link: Optional[str] = None
    target_audience: str
    target_department_id: Optional[int] = None
    target_department_name: Optional[str] = None
    target_program_id: Optional[int] = None
    target_batch_id: Optional[int] = None
    target_year: Optional[int] = None
    instructions: Optional[str] = None
    requires_approval: bool
    status: str
    live_status: str  # 'UPCOMING', 'ONGOING', 'COMPLETED', 'CANCELLED', 'DRAFT', 'PENDING'
    rejection_reason: Optional[str] = None
    cancellation_reason: Optional[str] = None
    approval_notes: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[str] = None
    published_at: Optional[str] = None
    created_by: int
    version: int
    created_at: str
    updated_at: str
