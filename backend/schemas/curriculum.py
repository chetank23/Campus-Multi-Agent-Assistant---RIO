"""
backend/schemas/curriculum.py
-----------------------------
Pydantic v2 schemas for Central Academic Curriculum Registry,
Super Admin governance, AI extraction studio, and operational allocation.
"""

from __future__ import annotations

import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Regulation Schemas
# ---------------------------------------------------------------------------

class RegulationBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=30)
    name: str = Field(..., min_length=2, max_length=150)
    department_id: Optional[int] = None
    effective_year: int = Field(..., ge=2000, le=2100)
    is_active: bool = True
    description: Optional[str] = None


class RegulationCreate(RegulationBase):
    pass


class RegulationUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=30)
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    department_id: Optional[int] = None
    effective_year: Optional[int] = Field(None, ge=2000, le=2100)
    is_active: Optional[bool] = None
    description: Optional[str] = None


class RegulationResponse(RegulationBase):
    id: int
    department_name: Optional[str] = None
    cohorts_count: int = 0
    curriculum_versions_count: int = 0
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 2. Admission Cohort Schemas
# ---------------------------------------------------------------------------

class AdmissionCohortBase(BaseModel):
    cohort_name: str = Field(..., min_length=4, max_length=50)  # e.g. "2023-2027"
    start_year: int = Field(..., ge=2000, le=2100)
    end_year: int = Field(..., ge=2000, le=2100)
    program_id: int
    regulation_id: int
    is_active: bool = True


class AdmissionCohortCreate(AdmissionCohortBase):
    pass


class AdmissionCohortUpdate(BaseModel):
    cohort_name: Optional[str] = Field(None, min_length=4, max_length=50)
    start_year: Optional[int] = Field(None, ge=2000, le=2100)
    end_year: Optional[int] = Field(None, ge=2000, le=2100)
    program_id: Optional[int] = None
    regulation_id: Optional[int] = None
    is_active: Optional[bool] = None


class AdmissionCohortResponse(AdmissionCohortBase):
    id: int
    program_name: Optional[str] = None
    regulation_code: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 3. Curriculum Subject Mapping Schemas
# ---------------------------------------------------------------------------

class CurriculumSubjectMappingBase(BaseModel):
    curriculum_semester_id: int
    course_id: Optional[int] = None
    subject_code: str = Field(..., min_length=2, max_length=30)
    subject_name: str = Field(..., min_length=2, max_length=150)
    subject_type: str = Field(default="THEORY")
    is_mandatory: bool = True
    elective_group_name: Optional[str] = None
    credits: float = Field(default=3.0, ge=0.0, le=30.0)
    lecture_hours: int = Field(default=3, ge=0, le=40)
    tutorial_hours: int = Field(default=0, ge=0, le=40)
    practical_hours: int = Field(default=0, ge=0, le=40)
    contact_hours: int = Field(default=3, ge=0, le=50)
    practical_consecutive_periods: int = Field(default=2, ge=1, le=6)
    requires_lab: bool = False
    course_description: Optional[str] = None
    prerequisites: Optional[str] = None
    co_requisites: Optional[str] = None
    source_pdf_id: Optional[int] = None
    source_page: Optional[int] = None
    source_text: Optional[str] = None
    verification_status: str = "VERIFIED"


class CurriculumSubjectMappingCreate(BaseModel):
    curriculum_semester_id: int
    course_id: Optional[int] = None
    subject_code: str = Field(..., min_length=2, max_length=30)
    subject_name: str = Field(..., min_length=2, max_length=150)
    subject_type: str = "THEORY"
    is_mandatory: bool = True
    elective_group_name: Optional[str] = None
    credits: float = 3.0
    lecture_hours: int = 3
    tutorial_hours: int = 0
    practical_hours: int = 0
    contact_hours: int = 3
    practical_consecutive_periods: int = 2
    requires_lab: bool = False
    course_description: Optional[str] = None
    prerequisites: Optional[str] = None
    co_requisites: Optional[str] = None
    source_pdf_id: Optional[int] = None
    source_page: Optional[int] = None
    source_text: Optional[str] = None
    verification_status: str = "VERIFIED"


class CurriculumSubjectMappingUpdate(BaseModel):
    course_id: Optional[int] = None
    subject_code: Optional[str] = Field(None, min_length=2, max_length=30)
    subject_name: Optional[str] = Field(None, min_length=2, max_length=150)
    subject_type: Optional[str] = None
    is_mandatory: Optional[bool] = None
    elective_group_name: Optional[str] = None
    credits: Optional[float] = None
    lecture_hours: Optional[int] = None
    tutorial_hours: Optional[int] = None
    practical_hours: Optional[int] = None
    contact_hours: Optional[int] = None
    practical_consecutive_periods: Optional[int] = None
    requires_lab: Optional[bool] = None
    course_description: Optional[str] = None
    prerequisites: Optional[str] = None
    co_requisites: Optional[str] = None
    source_page: Optional[int] = None
    source_text: Optional[str] = None
    verification_status: Optional[str] = None


class CurriculumSubjectMappingResponse(CurriculumSubjectMappingBase):
    id: int
    curriculum_version_id: int
    semester_number: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 4. Curriculum Semester Schemas
# ---------------------------------------------------------------------------

class CurriculumSemesterResponse(BaseModel):
    id: int
    curriculum_version_id: int
    semester_number: int
    total_credits: float = 0.0
    total_contact_hours: int = 0
    notes: Optional[str] = None
    subject_mappings: List[CurriculumSubjectMappingResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CurriculumSemesterCreate(BaseModel):
    semester_number: int = Field(..., ge=1, le=12)
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 5. Curriculum Version Schemas
# ---------------------------------------------------------------------------

class CurriculumVersionBase(BaseModel):
    department_id: int
    program_id: int
    regulation_id: int
    cohort_id: Optional[int] = None
    description: Optional[str] = None
    total_semesters: Optional[int] = Field(default=None, ge=1, le=16)


class CurriculumVersionCreate(CurriculumVersionBase):
    version_code: Optional[str] = None  # auto-generated if omitted (e.g. CURR-CSE-R2023-V1)


class CurriculumVersionUpdate(BaseModel):
    cohort_id: Optional[int] = None
    description: Optional[str] = None
    total_semesters: Optional[int] = Field(None, ge=1, le=16)


class CurriculumVersionStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(DRAFT|NEEDS_REVIEW|VALIDATED|APPROVED|PUBLISHED|SUPERSEDED|ARCHIVED)$")
    review_notes: Optional[str] = None


class CurriculumVersionResponse(BaseModel):
    id: int
    version_code: str
    department_id: int
    department_name: Optional[str] = None
    program_id: int
    program_name: Optional[str] = None
    regulation_id: int
    regulation_code: Optional[str] = None
    cohort_id: Optional[int] = None
    cohort_name: Optional[str] = None
    version_number: int
    status: str
    description: Optional[str] = None
    total_credits: float
    total_semesters: int
    source_document_id: Optional[int] = None
    source_document_title: Optional[str] = None
    created_by_id: int
    created_by_name: Optional[str] = None
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_by_name: Optional[str] = None
    published_by_id: Optional[int] = None
    published_by_name: Optional[str] = None
    published_at: Optional[datetime.datetime] = None
    superseded_by_id: Optional[int] = None
    previous_version_id: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    semesters: List[CurriculumSemesterResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CurriculumVersionSummary(BaseModel):
    id: int
    version_code: str
    department_name: str
    program_name: str
    regulation_code: str
    cohort_name: Optional[str] = None
    version_number: int
    status: str
    total_credits: float
    total_semesters: int
    published_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 6. Document & Extraction Schemas
# ---------------------------------------------------------------------------

class CurriculumDocumentResponse(BaseModel):
    id: int
    title: str
    file_name: str
    file_path: str
    file_hash: str
    file_size_bytes: int
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    regulation_id: Optional[int] = None
    cohort_id: Optional[int] = None
    curriculum_version_id: Optional[int] = None
    uploaded_by_id: int
    uploader_name: Optional[str] = None
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractedSubjectItem(BaseModel):
    semester: int
    code: str
    name: str
    type: str = "THEORY"
    credits: float = 3.0
    lecture: int = 3
    tutorial: int = 0
    practical: int = 0
    contact_hours: int = 3
    requires_lab: bool = False
    is_mandatory: bool = True
    elective_group: Optional[str] = None
    source_page: Optional[int] = None
    source_text: Optional[str] = None
    confidence_score: Optional[float] = None
    extraction_method: str = "DETERMINISTIC_PARSER"


class ExtractionReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(APPROVE|REJECT)$")
    feedback: Optional[str] = None
    target_version_id: Optional[int] = None  # target version to populate if approved
    edited_data: Optional[List[ExtractedSubjectItem]] = None


class CurriculumExtractionJobResponse(BaseModel):
    id: int
    document_id: int
    document_title: Optional[str] = None
    target_curriculum_version_id: Optional[int] = None
    status: str
    total_pages: int
    extracted_semesters_count: int
    extracted_subjects_count: int
    extracted_data: Optional[List[ExtractedSubjectItem]] = None
    error_message: Optional[str] = None
    extraction_mode: str = "DETERMINISTIC_PARSER_FALLBACK"
    ai_provider_status: str = "UNAVAILABLE"
    created_by_id: int
    creator_name: Optional[str] = None
    reviewed_by_id: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 7. Curriculum Release & Inbox Schemas
# ---------------------------------------------------------------------------

class CurriculumReleaseCreate(BaseModel):
    curriculum_version_id: Optional[int] = None
    department_ids: List[int] = []


CurriculumVersionPublishRequest = CurriculumReleaseCreate


class CurriculumReleaseAcknowledge(BaseModel):
    acknowledgement_notes: Optional[str] = None


class CurriculumReleaseResponse(BaseModel):
    id: int
    curriculum_version_id: int
    version_code: Optional[str] = None
    program_name: Optional[str] = None
    regulation_code: Optional[str] = None
    department_id: int
    department_name: Optional[str] = None
    released_at: datetime.datetime
    released_by_name: Optional[str] = None
    is_acknowledged: bool
    acknowledged_by_name: Optional[str] = None
    acknowledged_at: Optional[datetime.datetime] = None
    acknowledgement_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 8. Curriculum Request & Thread Schemas
# ---------------------------------------------------------------------------

class CurriculumRequestMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    attachments_json: Optional[str] = None


class CurriculumRequestMessageResponse(BaseModel):
    id: int
    request_id: int
    sender_id: int
    sender_name: str
    sender_role: str
    message: str
    attachments_json: Optional[str] = None
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class CurriculumRequestCreate(BaseModel):
    department_id: int
    program_id: Optional[int] = None
    curriculum_version_id: Optional[int] = None
    curriculum_semester_id: Optional[int] = None
    subject_mapping_id: Optional[int] = None
    request_type: str = Field(
        ...,
        pattern="^(MISSING_SUBJECT|INCORRECT_CODE|INCORRECT_NAME|WRONG_SEMESTER|INCORRECT_CREDITS|INCORRECT_HOURS|MISSING_LAB|MISSING_ELECTIVE|REVISED_SYLLABUS|OTHER)$"
    )
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5, max_length=5000)
    proposed_change_json: Optional[str] = None


class CurriculumRequestStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(OPEN|UNDER_REVIEW|NEEDS_INFORMATION|RESOLVED|REJECTED|WITHDRAWN)$")
    resolution_notes: Optional[str] = None
    resulting_curriculum_version_id: Optional[int] = None


class CurriculumRequestResponse(BaseModel):
    id: int
    request_number: str
    requesting_admin_id: int
    requesting_admin_name: Optional[str] = None
    department_id: int
    department_name: Optional[str] = None
    program_id: Optional[int] = None
    program_name: Optional[str] = None
    curriculum_version_id: Optional[int] = None
    curriculum_version_code: Optional[str] = None
    curriculum_semester_id: Optional[int] = None
    subject_mapping_id: Optional[int] = None
    subject_mapping_name: Optional[str] = None
    request_type: str
    title: str
    description: str
    proposed_change_json: Optional[str] = None
    status: str
    resolution_notes: Optional[str] = None
    resolved_by_id: Optional[int] = None
    resolved_by_name: Optional[str] = None
    resolved_at: Optional[datetime.datetime] = None
    resulting_curriculum_version_id: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    messages: List[CurriculumRequestMessageResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 9. Operational Section & Faculty Allocation Schemas
# ---------------------------------------------------------------------------

class SectionCourseOfferingCreate(BaseModel):
    curriculum_version_id: int
    curriculum_subject_mapping_id: int
    academic_year_id: int
    semester_id: int
    section_id: int
    batch_id: Optional[int] = None
    enrolled_student_count: int = Field(default=0, ge=0)


class FacultyCourseOfferingCreate(BaseModel):
    section_course_offering_id: int
    faculty_id: int
    assigned_role: str = "PRIMARY_LECTURER"
    assigned_hours: int = Field(default=3, ge=1, le=40)


class FacultyCourseOfferingResponse(BaseModel):
    id: int
    section_course_offering_id: int
    faculty_id: int
    faculty_name: Optional[str] = None
    faculty_code: Optional[str] = None
    assigned_role: str
    assigned_hours: int
    is_active: bool
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class SectionCourseOfferingResponse(BaseModel):
    id: int
    curriculum_version_id: int
    curriculum_subject_mapping_id: int
    subject_code: Optional[str] = None
    subject_name: Optional[str] = None
    subject_type: Optional[str] = None
    academic_year_id: int
    academic_year_name: Optional[str] = None
    semester_id: int
    semester_number: Optional[int] = None
    section_id: int
    section_name: Optional[str] = None
    batch_id: Optional[int] = None
    batch_name: Optional[str] = None
    enrolled_student_count: int
    is_active: bool
    faculty_allocations: List[FacultyCourseOfferingResponse] = []
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 10. Curriculum Readiness & Timetable Preflight Schemas
# ---------------------------------------------------------------------------

class SubjectReadinessItem(BaseModel):
    subject_code: str
    subject_name: str
    subject_type: str
    credits: float
    contact_hours: int
    requires_lab: bool
    sections_covered: int
    sections_total: int
    is_fully_allocated: bool
    allocated_faculty_names: List[str] = []
    missing_items: List[str] = []


class CurriculumReadinessResponse(BaseModel):
    curriculum_version_id: int
    version_code: str
    department_id: int
    department_name: str
    semester_number: int
    is_ready_for_scheduling: bool
    readiness_percentage: float
    total_subjects: int
    allocated_subjects: int
    unallocated_subjects: int
    missing_faculty_count: int
    subjects: List[SubjectReadinessItem] = []
    blocking_reasons: List[str] = []


# ---------------------------------------------------------------------------
# 11. Super Admin Dashboard Stats Schema
# ---------------------------------------------------------------------------

class SuperAdminDashboardStats(BaseModel):
    total_regulations: int = 0
    total_cohorts: int = 0
    total_curriculum_versions: int = 0
    draft_versions_count: int = 0
    needs_review_count: int = 0
    approved_versions_count: int = 0
    published_versions_count: int = 0
    open_requests_count: int = 0
    documents_count: int = 0
    extraction_jobs_count: int = 0
    active_releases_count: int = 0
    recent_activities: List[Dict[str, Any]] = []
