"""
backend/schemas/placements.py
-----------------------------
Pydantic v2 schemas for CDC Placement Management:
- Placement drive CRUD & lifecycle requests/responses
- Placement selection schedules
- Deterministic student eligibility result
- Student academic records (CGPA, grading scale, backlogs)
- Dashboard analytics
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# 1. Selection Schedule Schemas
# ---------------------------------------------------------------------------

class PlacementScheduleCreate(BaseModel):
    round_type: str = Field(
        ...,
        description="PRE_PLACEMENT_TALK, ONLINE_ASSESSMENT, CODING_TEST, APTITUDE_TEST, TECHNICAL_INTERVIEW, HR_INTERVIEW, GROUP_DISCUSSION, FINAL_ROUND",
    )
    round_order: int = Field(1, ge=1)
    title: str = Field(..., min_length=2, max_length=150)
    start_time: datetime.datetime
    end_time: datetime.datetime
    venue_name: Optional[str] = Field(None, max_length=150)
    room_id: Optional[int] = None
    is_online: bool = False
    meeting_link: Optional[str] = Field(None, max_length=255)
    instructions: Optional[str] = None


class PlacementScheduleResponse(BaseModel):
    id: int
    round_type: str
    round_order: int
    title: str
    start_time: str
    end_time: str
    venue_name: Optional[str] = None
    room_id: Optional[int] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    is_online: bool
    meeting_link: Optional[str] = None
    instructions: Optional[str] = None


# ---------------------------------------------------------------------------
# 2. Student Eligibility Schemas
# ---------------------------------------------------------------------------

class StudentEligibilityResult(BaseModel):
    status: Literal["ELIGIBLE", "NOT_ELIGIBLE", "CANNOT_DETERMINE"]
    is_eligible: bool
    reasons: List[str] = []
    criteria_breakdown: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# 3. Placement Drive Request Schemas
# ---------------------------------------------------------------------------

class PlacementDriveCreateRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=150)
    company_description: Optional[str] = None
    company_website: Optional[str] = Field(default=None, max_length=255)
    company_logo_url: Optional[str] = Field(default=None, max_length=255)

    title: str = Field(..., min_length=3, max_length=200)
    job_role: str = Field(..., min_length=2, max_length=150)
    job_description: Optional[str] = None
    job_type: Literal["FULL_TIME", "INTERNSHIP", "INTERN_PLUS_FULL_TIME"] = "FULL_TIME"
    work_location: Optional[str] = Field(default=None, max_length=150)
    compensation_details: Optional[str] = Field(default=None, max_length=200)
    tier: Optional[str] = Field(default=None, max_length=50)

    # Structured Eligibility Rules
    eligible_department_ids: Optional[List[int]] = None
    eligible_program_ids: Optional[List[int]] = None
    eligible_batch_ids: Optional[List[int]] = None
    graduation_year: Optional[int] = Field(default=None, ge=2020, le=2035)
    min_cgpa: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    grading_scale: float = Field(default=10.0, ge=4.0, le=10.0)
    min_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    max_active_backlogs: Optional[int] = Field(default=None, ge=0)
    max_total_backlogs: Optional[int] = Field(default=None, ge=0)
    allowed_genders: Literal["ALL", "MALE_ONLY", "FEMALE_ONLY"] = "ALL"
    additional_criteria: Optional[str] = None

    application_deadline: datetime.datetime
    application_link: Optional[str] = Field(default=None, max_length=500)
    application_instructions: Optional[str] = None
    contact_email: Optional[str] = Field(default=None, max_length=150)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    required_documents: Optional[str] = None

    schedules: List[PlacementScheduleCreate] = []


class PlacementDriveUpdateRequest(BaseModel):
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    company_description: Optional[str] = None
    company_website: Optional[str] = Field(default=None, max_length=255)
    company_logo_url: Optional[str] = Field(default=None, max_length=255)

    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    job_role: Optional[str] = Field(default=None, min_length=2, max_length=150)
    job_description: Optional[str] = None
    job_type: Optional[Literal["FULL_TIME", "INTERNSHIP", "INTERN_PLUS_FULL_TIME"]] = None
    work_location: Optional[str] = Field(default=None, max_length=150)
    compensation_details: Optional[str] = Field(default=None, max_length=200)
    tier: Optional[str] = Field(default=None, max_length=50)

    eligible_department_ids: Optional[List[int]] = None
    eligible_program_ids: Optional[List[int]] = None
    eligible_batch_ids: Optional[List[int]] = None
    graduation_year: Optional[int] = Field(default=None, ge=2020, le=2035)
    min_cgpa: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    grading_scale: Optional[float] = Field(default=None, ge=4.0, le=10.0)
    min_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    max_active_backlogs: Optional[int] = Field(default=None, ge=0)
    max_total_backlogs: Optional[int] = Field(default=None, ge=0)
    allowed_genders: Optional[Literal["ALL", "MALE_ONLY", "FEMALE_ONLY"]] = None
    additional_criteria: Optional[str] = None

    application_deadline: Optional[datetime.datetime] = None
    application_link: Optional[str] = Field(default=None, max_length=500)
    application_instructions: Optional[str] = None
    contact_email: Optional[str] = Field(default=None, max_length=150)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    required_documents: Optional[str] = None

    schedules: Optional[List[PlacementScheduleCreate]] = None
    version: Optional[int] = None


class PlacementDriveActionReason(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class PlacementDriveValidationResponse(BaseModel):
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    eligible_students_count: int = 0
    likely_duplicates: List[str] = []


# ---------------------------------------------------------------------------
# 4. Placement Drive Response Schemas
# ---------------------------------------------------------------------------

class PlacementDriveResponse(BaseModel):
    id: int
    company_name: str
    company_description: Optional[str] = None
    company_website: Optional[str] = None
    company_logo_url: Optional[str] = None

    title: str
    job_role: str
    job_description: Optional[str] = None
    job_type: str
    work_location: Optional[str] = None
    compensation_details: Optional[str] = None
    tier: Optional[str] = None

    eligible_department_ids: Optional[List[int]] = None
    eligible_department_names: List[str] = []
    eligible_program_ids: Optional[List[int]] = None
    eligible_program_names: List[str] = []
    eligible_batch_ids: Optional[List[int]] = None
    graduation_year: Optional[int] = None
    min_cgpa: Optional[float] = None
    grading_scale: float
    min_percentage: Optional[float] = None
    max_active_backlogs: Optional[int] = None
    max_total_backlogs: Optional[int] = None
    allowed_genders: str
    additional_criteria: Optional[str] = None

    application_deadline: str
    is_deadline_passed: bool
    application_link: Optional[str] = None
    application_instructions: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    required_documents: Optional[str] = None

    status: str  # DRAFT, PUBLISHED, CLOSED, POSTPONED, CANCELLED, ARCHIVED
    postpone_reason: Optional[str] = None
    cancellation_reason: Optional[str] = None
    published_at: Optional[str] = None
    closed_at: Optional[str] = None

    coordinator_id: int
    coordinator_name: str
    coordinator_email: str
    version: int
    created_at: str
    updated_at: str

    schedules: List[PlacementScheduleResponse] = []
    eligibility: Optional[StudentEligibilityResult] = None


# ---------------------------------------------------------------------------
# 5. Student Academic Records Schemas
# ---------------------------------------------------------------------------

class StudentAcademicRecordUpsert(BaseModel):
    student_id: int
    cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    grading_scale: float = Field(10.0, ge=4.0, le=10.0)
    percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    active_backlogs: Optional[int] = Field(0, ge=0)
    total_backlogs: Optional[int] = Field(0, ge=0)
    graduation_year: Optional[int] = Field(None, ge=2020, le=2035)
    tenth_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    twelfth_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    is_verified: bool = True


class StudentAcademicRecordResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    student_usn: str
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    cgpa: Optional[float] = None
    grading_scale: float
    percentage: Optional[float] = None
    active_backlogs: Optional[int] = None
    total_backlogs: Optional[int] = None
    graduation_year: Optional[int] = None
    tenth_percentage: Optional[float] = None
    twelfth_percentage: Optional[float] = None
    is_verified: bool
    verified_by_name: Optional[str] = None
    updated_at: str


# ---------------------------------------------------------------------------
# 6. Dashboard Analytics Schemas
# ---------------------------------------------------------------------------

class CdcDashboardStats(BaseModel):
    total_drives: int
    published_drives: int
    draft_drives: int
    closed_drives: int
    postponed_drives: int
    cancelled_drives: int
    upcoming_deadlines_count: int
    recent_drives: List[PlacementDriveResponse] = []
