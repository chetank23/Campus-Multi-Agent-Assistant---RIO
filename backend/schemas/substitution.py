"""
backend/schemas/substitution.py
-------------------------------
Pydantic schemas for Faculty Substitution:
- Class occurrence inspection
- Unavailability request creation
- Transparent deterministic candidate recommendations
- Review actions (Approval / Rejection with optimistic concurrency)
- Multi-party substitution responses (with role-based privacy barriers)
"""

from __future__ import annotations

import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ClassOccurrenceResponse(BaseModel):
    timetable_entry_id: int
    date: datetime.date
    day: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    course_id: Optional[int] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    batch_id: Optional[int] = None
    batch_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    has_active_request: bool = False
    active_substitution_id: Optional[int] = None
    active_substitution_status: Optional[str] = None
    substitute_faculty_id: Optional[int] = None
    substitute_faculty_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SubstitutionRequestCreate(BaseModel):
    timetable_entry_id: int
    substitution_date: datetime.date
    reason: str = Field(..., min_length=3, max_length=1000)


class CandidateEligibilityReason(BaseModel):
    factor: str
    status: str  # "PASS", "FAIL", "UNKNOWN"
    detail: str


class SubstituteCandidateRecommendation(BaseModel):
    faculty_id: int
    faculty_code: Optional[str] = None
    faculty_name: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    designation: Optional[str] = None
    qualification_tier: str  # "DIRECT_ASSIGNMENT", "DEPARTMENT_MATCH", "GENERAL"
    current_weekly_load: int
    max_weekly_load: int
    load_percentage: float
    score: float
    is_eligible: bool
    ineligibility_reasons: List[str] = []
    eligibility_breakdown: List[CandidateEligibilityReason] = []


class CandidateRecommendationResponse(BaseModel):
    substitution_id: int
    timetable_entry_id: int
    substitution_date: datetime.date
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    slot_day: Optional[str] = None
    slot_time: Optional[str] = None
    original_faculty_id: int
    original_faculty_name: str
    evaluation_status: str = Field(default="ELIGIBLE", pattern="^(ELIGIBLE|NO_ELIGIBLE_CANDIDATE|CANNOT_DETERMINE)$")
    cannot_determine: bool = False
    cannot_determine_reason: Optional[str] = None
    candidates: List[SubstituteCandidateRecommendation] = []


class SubstitutionReviewActionRequest(BaseModel):
    action: str = Field(..., pattern="^(APPROVE|REJECT)$")
    substitute_faculty_id: Optional[int] = None
    rejection_reason: Optional[str] = Field(default=None, max_length=1000)
    version: int = Field(default=1, ge=1)


class FacultySubstitutionResponse(BaseModel):
    id: int
    timetable_entry_id: int
    substitution_date: datetime.date
    original_faculty_id: int
    original_faculty_name: str
    substitute_faculty_id: Optional[int] = None
    substitute_faculty_name: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    slot_day: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    section_name: Optional[str] = None
    batch_name: Optional[str] = None
    department_name: Optional[str] = None
    status: str
    reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_by_id: int
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime.datetime] = None
    version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class StudentDateClassView(BaseModel):
    timetable_entry_id: int
    date: datetime.date
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_substituted: bool = False
    faculty_name: str
    original_faculty_name: Optional[str] = None
    slot_type: Optional[str] = None
    status: str

    model_config = ConfigDict(from_attributes=True)

