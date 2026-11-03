"""
backend/models/curriculum.py
----------------------------
Central Academic Curriculum Registry domain:
  - Regulation: Academic schemes & regulations (R2023, R2025, etc.)
  - AdmissionCohort: Program admission cohorts (e.g. 2023-2027, 2025-2029)
  - CurriculumVersion: Versioned, governed institutional curricula (Draft -> Published)
  - CurriculumSemester: Ordinal semesters within a curriculum version (1..N)
  - CurriculumSubjectMapping: Version-pinned subject definition with credits & L/T/P hours
  - CurriculumDocument: Uploaded official syllabus PDFs with secure storage & hashing
  - CurriculumExtractionJob: AI document processing & structured extraction lifecycle
  - CurriculumRelease: Department inbox releases & administrative acknowledgements
  - CurriculumRequest: Admin -> Super Admin academic correction request tickets
  - CurriculumRequestMessage: Persistent communication threads for requests
  - SectionCourseOffering: Operational delivery mapping to actual sections and batches
  - FacultyCourseOffering: Faculty teaching allocations for section-course offerings
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.utils.datetime_utils import utc_now
from .base import Base

if TYPE_CHECKING:
    from .identity import User
    from .academic import Department, Program, AcademicYear, Semester, Section, Batch, Faculty, Student
    from .courses import Course
    from .timetable import TimetableVersion


# ---------------------------------------------------------------------------
# 1. Regulation / Academic Scheme
# ---------------------------------------------------------------------------

class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_regulations_department_id"), nullable=True
    )
    effective_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department")
    cohorts: Mapped[list["AdmissionCohort"]] = relationship(
        "AdmissionCohort", back_populates="regulation", cascade="all, delete-orphan"
    )
    curriculum_versions: Mapped[list["CurriculumVersion"]] = relationship(
        "CurriculumVersion", back_populates="regulation"
    )


# ---------------------------------------------------------------------------
# 2. Admission Cohort
# ---------------------------------------------------------------------------

class AdmissionCohort(Base):
    __tablename__ = "admission_cohorts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cohort_name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "2023-2027"
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)     # 2023
    end_year: Mapped[int] = mapped_column(Integer, nullable=False)       # 2027
    program_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_cohorts_program_id"), nullable=False, index=True
    )
    regulation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("regulations.id", name="fk_cohorts_regulation_id"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("program_id", "cohort_name", name="uq_program_cohort_name"),
    )

    # Relationships
    program: Mapped["Program"] = relationship("Program")
    regulation: Mapped["Regulation"] = relationship("Regulation", back_populates="cohorts")
    curriculum_versions: Mapped[list["CurriculumVersion"]] = relationship(
        "CurriculumVersion", back_populates="cohort"
    )


# ---------------------------------------------------------------------------
# 3. Curriculum Version
# ---------------------------------------------------------------------------

class CurriculumVersion(Base):
    __tablename__ = "curriculum_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_cv_department_id"), nullable=False, index=True
    )
    program_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_cv_program_id"), nullable=False, index=True
    )
    regulation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("regulations.id", name="fk_cv_regulation_id"), nullable=False, index=True
    )
    cohort_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("admission_cohorts.id", name="fk_cv_cohort_id"), nullable=True, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        CheckConstraint(
            "status IN ('DRAFT','NEEDS_REVIEW','VALIDATED','APPROVED','PUBLISHED','SUPERSEDED','ARCHIVED')",
            name="ck_curriculum_version_status",
        ),
        default="DRAFT",
        server_default="DRAFT",
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_credits: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    total_semesters: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    source_document_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_documents.id", name="fk_cv_document_id"), nullable=True
    )
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cv_created_by"), nullable=False
    )
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cv_reviewed_by"), nullable=True
    )
    approved_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cv_approved_by"), nullable=True
    )
    published_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cv_published_by"), nullable=True
    )
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", name="fk_cv_superseded_by"), nullable=True
    )
    previous_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", name="fk_cv_prev_version"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    # Relationships
    department: Mapped["Department"] = relationship("Department")
    program: Mapped["Program"] = relationship("Program")
    regulation: Mapped["Regulation"] = relationship("Regulation", back_populates="curriculum_versions")
    cohort: Mapped[Optional["AdmissionCohort"]] = relationship(
        "AdmissionCohort", back_populates="curriculum_versions"
    )
    document: Mapped[Optional["CurriculumDocument"]] = relationship(
        "CurriculumDocument", foreign_keys=[source_document_id]
    )
    semesters: Mapped[list["CurriculumSemester"]] = relationship(
        "CurriculumSemester", back_populates="curriculum_version", cascade="all, delete-orphan",
        order_by="CurriculumSemester.semester_number"
    )
    subject_mappings: Mapped[list["CurriculumSubjectMapping"]] = relationship(
        "CurriculumSubjectMapping", back_populates="curriculum_version", cascade="all, delete-orphan"
    )
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by_id])
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by_id])
    publisher: Mapped[Optional["User"]] = relationship("User", foreign_keys=[published_by_id])
    releases: Mapped[list["CurriculumRelease"]] = relationship(
        "CurriculumRelease", back_populates="curriculum_version", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# 4. Curriculum Semester
# ---------------------------------------------------------------------------

class CurriculumSemester(Base):
    __tablename__ = "curriculum_semesters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curriculum_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", ondelete="CASCADE", name="fk_cs_version_id"),
        nullable=False, index=True
    )
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..8+
    total_credits: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    total_contact_hours: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("curriculum_version_id", "semester_number", name="uq_curriculum_version_semester"),
    )

    curriculum_version: Mapped["CurriculumVersion"] = relationship(
        "CurriculumVersion", back_populates="semesters"
    )
    subject_mappings: Mapped[list["CurriculumSubjectMapping"]] = relationship(
        "CurriculumSubjectMapping", back_populates="curriculum_semester", cascade="all, delete-orphan",
        order_by="CurriculumSubjectMapping.subject_code"
    )


# ---------------------------------------------------------------------------
# 5. Curriculum Subject Mapping
# ---------------------------------------------------------------------------

class CurriculumSubjectMapping(Base):
    __tablename__ = "curriculum_subject_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curriculum_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", ondelete="CASCADE", name="fk_csm_version_id"),
        nullable=False, index=True
    )
    curriculum_semester_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_semesters.id", ondelete="CASCADE", name="fk_csm_semester_id"),
        nullable=False, index=True
    )
    course_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("courses.id", name="fk_csm_course_id"), nullable=True
    )
    subject_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(150), nullable=False)
    subject_type: Mapped[str] = mapped_column(
        String(30),
        CheckConstraint(
            "subject_type IN ('THEORY','PRACTICAL','INTEGRATED','TUTORIAL','PROJECT','INTERNSHIP','SEMINAR','MANDATORY_NON_CREDIT','PROFESSIONAL_ELECTIVE','OPEN_ELECTIVE')",
            name="ck_csm_subject_type",
        ),
        default="THEORY",
        server_default="THEORY",
        nullable=False,
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    elective_group_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    credits: Mapped[float] = mapped_column(Float, default=3.0, server_default="3.0", nullable=False)
    lecture_hours: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    tutorial_hours: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    practical_hours: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    contact_hours: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    practical_consecutive_periods: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    requires_lab: Mapped[bool] = mapped_column(Boolean, default=False, server_default="FALSE")
    course_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prerequisites: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    co_requisites: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_pdf_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_documents.id", name="fk_csm_source_pdf"), nullable=True
    )
    source_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(20), default="VERIFIED", server_default="VERIFIED", nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("curriculum_version_id", "subject_code", name="uq_csm_version_subject_code"),
    )

    # Relationships
    curriculum_version: Mapped["CurriculumVersion"] = relationship(
        "CurriculumVersion", back_populates="subject_mappings"
    )
    curriculum_semester: Mapped["CurriculumSemester"] = relationship(
        "CurriculumSemester", back_populates="subject_mappings"
    )
    course: Mapped[Optional["Course"]] = relationship("Course")
    source_document: Mapped[Optional["CurriculumDocument"]] = relationship("CurriculumDocument")
    section_offerings: Mapped[list["SectionCourseOffering"]] = relationship(
        "SectionCourseOffering", back_populates="subject_mapping", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# 6. Curriculum Document (PDF Storage)
# ---------------------------------------------------------------------------

class CurriculumDocument(Base):
    __tablename__ = "curriculum_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_cd_department_id"), nullable=True
    )
    program_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_cd_program_id"), nullable=True
    )
    regulation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("regulations.id", name="fk_cd_regulation_id"), nullable=True
    )
    cohort_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("admission_cohorts.id", name="fk_cd_cohort_id"), nullable=True
    )
    curriculum_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", name="fk_cd_curriculum_version_id", use_alter=True), nullable=True
    )
    uploaded_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cd_uploaded_by"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="UPLOADED", server_default="UPLOADED", nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by_id])
    extraction_jobs: Mapped[list["CurriculumExtractionJob"]] = relationship(
        "CurriculumExtractionJob", back_populates="document", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# 7. Curriculum Extraction Job
# ---------------------------------------------------------------------------

class CurriculumExtractionJob(Base):
    __tablename__ = "curriculum_extraction_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_documents.id", ondelete="CASCADE", name="fk_cej_document_id"),
        nullable=False, index=True
    )
    target_curriculum_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", name="fk_cej_version_id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30),
        CheckConstraint(
            "status IN ('QUEUED','PROCESSING','AWAITING_REVIEW','APPROVED','REJECTED','FAILED')",
            name="ck_cej_status",
        ),
        default="QUEUED",
        server_default="QUEUED",
        nullable=False,
    )
    total_pages: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    extracted_semesters_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    extracted_subjects_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    extracted_data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cej_created_by"), nullable=False
    )
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cej_reviewed_by"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    document: Mapped["CurriculumDocument"] = relationship(
        "CurriculumDocument", back_populates="extraction_jobs"
    )
    target_version: Mapped[Optional["CurriculumVersion"]] = relationship(
        "CurriculumVersion", foreign_keys=[target_curriculum_version_id]
    )
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by_id])


# ---------------------------------------------------------------------------
# 8. Curriculum Release (Inbox & Acknowledgement)
# ---------------------------------------------------------------------------

class CurriculumRelease(Base):
    __tablename__ = "curriculum_releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curriculum_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", ondelete="CASCADE", name="fk_cr_version_id"),
        nullable=False, index=True
    )
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_cr_department_id"), nullable=False, index=True
    )
    program_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_cr_program_id"), nullable=False
    )
    released_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    released_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cr_released_by"), nullable=False
    )
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="FALSE")
    acknowledged_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cr_acknowledged_by"), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgement_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    curriculum_version: Mapped["CurriculumVersion"] = relationship(
        "CurriculumVersion", back_populates="releases"
    )
    department: Mapped["Department"] = relationship("Department")
    program: Mapped["Program"] = relationship("Program")
    releaser: Mapped["User"] = relationship("User", foreign_keys=[released_by_id])
    acknowledger: Mapped[Optional["User"]] = relationship("User", foreign_keys=[acknowledged_by_id])


# ---------------------------------------------------------------------------
# 9. Curriculum Request (Admin -> Super Admin correction request)
# ---------------------------------------------------------------------------

class CurriculumRequest(Base):
    __tablename__ = "curriculum_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_number: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    requesting_admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_req_admin_id"), nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_req_department_id"), nullable=False, index=True
    )
    program_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_req_program_id"), nullable=True
    )
    curriculum_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", name="fk_req_version_id"), nullable=True
    )
    curriculum_semester_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_semesters.id", name="fk_req_semester_id"), nullable=True
    )
    subject_mapping_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_subject_mappings.id", name="fk_req_subject_mapping_id"), nullable=True
    )
    request_type: Mapped[str] = mapped_column(
        String(40),
        CheckConstraint(
            "request_type IN ('MISSING_SUBJECT','INCORRECT_CODE','INCORRECT_NAME','WRONG_SEMESTER','INCORRECT_CREDITS','INCORRECT_HOURS','MISSING_LAB','MISSING_ELECTIVE','REVISED_SYLLABUS','OTHER')",
            name="ck_req_type",
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_change_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        CheckConstraint(
            "status IN ('OPEN','UNDER_REVIEW','NEEDS_INFORMATION','RESOLVED','REJECTED','WITHDRAWN')",
            name="ck_curriculum_req_status",
        ),
        default="OPEN",
        server_default="OPEN",
        nullable=False,
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_req_resolved_by"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resulting_curriculum_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", name="fk_req_resulting_version_id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    requesting_admin: Mapped["User"] = relationship("User", foreign_keys=[requesting_admin_id])
    department: Mapped["Department"] = relationship("Department")
    program: Mapped[Optional["Program"]] = relationship("Program")
    curriculum_version: Mapped[Optional["CurriculumVersion"]] = relationship(
        "CurriculumVersion", foreign_keys=[curriculum_version_id]
    )
    messages: Mapped[list["CurriculumRequestMessage"]] = relationship(
        "CurriculumRequestMessage", back_populates="request", cascade="all, delete-orphan",
        order_by="CurriculumRequestMessage.created_at"
    )
    resolver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[resolved_by_id])
    resulting_version: Mapped[Optional["CurriculumVersion"]] = relationship(
        "CurriculumVersion", foreign_keys=[resulting_curriculum_version_id]
    )


# ---------------------------------------------------------------------------
# 10. Curriculum Request Message (Conversation Thread)
# ---------------------------------------------------------------------------

class CurriculumRequestMessage(Base):
    __tablename__ = "curriculum_request_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_requests.id", ondelete="CASCADE", name="fk_crm_request_id"),
        nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_crm_sender_id"), nullable=False
    )
    sender_role: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    attachments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    request: Mapped["CurriculumRequest"] = relationship("CurriculumRequest", back_populates="messages")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])


# ---------------------------------------------------------------------------
# 11. Section Course Offering (Operational Mapping)
# ---------------------------------------------------------------------------

class SectionCourseOffering(Base):
    __tablename__ = "section_course_offerings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    curriculum_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_versions.id", name="fk_sco_version_id"), nullable=False, index=True
    )
    curriculum_subject_mapping_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("curriculum_subject_mappings.id", name="fk_sco_csm_id"), nullable=False, index=True
    )
    academic_year_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("academic_years.id", name="fk_sco_academic_year_id"), nullable=False
    )
    semester_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("semesters.id", name="fk_sco_semester_id"), nullable=False
    )
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sections.id", name="fk_sco_section_id"), nullable=False, index=True
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("batches.id", name="fk_sco_batch_id"), nullable=True
    )
    enrolled_student_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    # Relationships
    curriculum_version: Mapped["CurriculumVersion"] = relationship("CurriculumVersion")
    subject_mapping: Mapped["CurriculumSubjectMapping"] = relationship(
        "CurriculumSubjectMapping", back_populates="section_offerings"
    )
    academic_year: Mapped["AcademicYear"] = relationship("AcademicYear")
    semester: Mapped["Semester"] = relationship("Semester")
    section: Mapped["Section"] = relationship("Section")
    batch: Mapped[Optional["Batch"]] = relationship("Batch")
    faculty_allocations: Mapped[list["FacultyCourseOffering"]] = relationship(
        "FacultyCourseOffering", back_populates="section_offering", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# 12. Faculty Course Offering (Faculty Allocation)
# ---------------------------------------------------------------------------

class FacultyCourseOffering(Base):
    __tablename__ = "faculty_course_offerings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_course_offering_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("section_course_offerings.id", ondelete="CASCADE", name="fk_fco_sco_id"),
        nullable=False, index=True
    )
    faculty_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("faculty.id", name="fk_fco_faculty_id"), nullable=False, index=True
    )
    assigned_role: Mapped[str] = mapped_column(
        String(30), default="PRIMARY_LECTURER", server_default="PRIMARY_LECTURER", nullable=False
    )
    assigned_hours: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    section_offering: Mapped["SectionCourseOffering"] = relationship(
        "SectionCourseOffering", back_populates="faculty_allocations"
    )
    faculty: Mapped["Faculty"] = relationship("Faculty")
