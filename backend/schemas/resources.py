"""
backend/schemas/resources.py
----------------------------
Pydantic schemas for the Resource Allocation Engine:
  - Resource definition & management
  - Resource booking requests, approvals, and cancellations
  - Availability queries and alternative resource suggestions
"""

from __future__ import annotations

import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

ResourceType = Literal["LAB", "SEMINAR_HALL", "PROJECTOR", "AUDITORIUM", "EQUIPMENT"]
ResourceStatus = Literal["ACTIVE", "INACTIVE", "MAINTENANCE"]
BookingStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]


# ── Resource Schemas ──────────────────────────────────────────────────────────

class ResourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Resource name or identifier")
    resource_type: ResourceType = Field(..., description="Type/category of resource")
    location: Optional[str] = Field(None, max_length=150, description="Physical room or building location")
    capacity: Optional[int] = Field(None, ge=0, description="Seating or equipment capacity")
    status: ResourceStatus = Field(default="ACTIVE", description="Operating status")


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    resource_type: Optional[ResourceType] = None
    location: Optional[str] = Field(None, max_length=150)
    capacity: Optional[int] = Field(None, ge=0)
    status: Optional[ResourceStatus] = None


class ResourceResponse(ResourceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ── Booking Schemas ───────────────────────────────────────────────────────────

class ResourceBookingBase(BaseModel):
    resource_id: int = Field(..., description="ID of the resource to book")
    date: datetime.date = Field(..., description="Date of the booking")
    start_time: datetime.time = Field(..., description="Start time (HH:MM:SS)")
    end_time: datetime.time = Field(..., description="End time (HH:MM:SS)")
    purpose: Optional[str] = Field(None, max_length=500, description="Booking reason or purpose")

    @model_validator(mode="after")
    def validate_interval(self) -> "ResourceBookingBase":
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be strictly after start_time")
        if self.date < datetime.date.today():
            raise ValueError("Booking date cannot be in the past")
        return self


class ResourceBookingCreate(ResourceBookingBase):
    pass


class ResourceBookingResponse(BaseModel):
    id: int
    resource_id: int
    requested_by: Optional[int] = None
    date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    purpose: Optional[str] = None
    status: BookingStatus
    approved_by: Optional[int] = None

    # Enriched presentation fields
    resource_name: Optional[str] = None
    resource_type: Optional[str] = None
    resource_location: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    approver_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BookingStatusAction(BaseModel):
    reason: Optional[str] = Field(None, max_length=500, description="Optional reason for rejection or cancellation")


# ── Availability & Alternative Schemas ────────────────────────────────────────

class AlternativeResource(BaseModel):
    id: int
    name: str
    resource_type: str
    location: Optional[str] = None
    capacity: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class AlternativeTime(BaseModel):
    resource_id: int
    resource_name: str
    date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    duration_minutes: int

    model_config = ConfigDict(from_attributes=True)


class ConflictDetail(BaseModel):
    conflict_type: Literal["EXISTING_BOOKING", "PUBLISHED_TIMETABLE", "RESOURCE_INACTIVE", "ACTIVE_BOOKING_LOCK"]
    description: str
    conflicting_id: Optional[int] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None


class AvailabilityResponse(BaseModel):
    resource_id: int
    date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    available: bool
    conflicts: List[ConflictDetail] = Field(default_factory=list)
    alternatives: List[AlternativeResource] = Field(default_factory=list)
    alternative_times: List[AlternativeTime] = Field(default_factory=list)
