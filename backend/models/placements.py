"""
backend/models/placements.py
----------------------------
SQLAlchemy ORM models for CDC Placement Management:
1. PlacementDrive — Company info, drive details, structured eligibility rules, deadlines, lifecycle.
2. PlacementSchedule — Multi-stage selection rounds (PPT, OA, Tech, HR), venues, timings.
3. StudentAcademicRecord — Authoritative student academic metrics (CGPA, grading scale, backlogs, graduation year).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .identity import User
    from .space_time import Room
    from .academic import Student, Department, Program, Batch


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class PlacementDrive(Base):
    __tablename__ = "placement_drives"
    __table_args__ = (
        Index("ix_placement_drives_status_deadline", "status", "application_deadline"),
        Index("ix_placement_drives_company", "company_name"),
        Index("ix_placement_drives_coordinator", "coordinator_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 1. Company Information
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    company_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_logo_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 2. Drive & Job Details
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    job_role: Mapped[str] = mapped_column(String(150), nullable=False)
    job_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_type: Mapped[str] = mapped_column(
        String(50), default="FULL_TIME", server_default="'FULL_TIME'", nullable=False
    )  # 'FULL_TIME', 'INTERNSHIP', 'INTERN_PLUS_FULL_TIME'
    work_location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    compensation_details: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 'TIER_1', 'DREAM', 'SUPER_DREAM', 'CORE'

    # 3. Structured Eligibility Engine Rules (JSON & Columns)
    eligible_department_ids: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True)
    eligible_program_ids: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True)
    eligible_batch_ids: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True)
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_cgpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grading_scale: Mapped[float] = mapped_column(Float, default=10.0, server_default="10.0", nullable=False)
    min_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_active_backlogs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_total_backlogs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allowed_genders: Mapped[str] = mapped_column(
        String(30), default="ALL", server_default="'ALL'", nullable=False
    )  # 'ALL', 'MALE_ONLY', 'FEMALE_ONLY'
    additional_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 4. Application & Contact
    application_deadline: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    application_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    application_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    required_documents: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 5. Lifecycle & Versioning
    status: Mapped[str] = mapped_column(
        String(30), default="DRAFT", server_default="'DRAFT'", nullable=False
    )  # 'DRAFT', 'PUBLISHED', 'CLOSED', 'POSTPONED', 'CANCELLED', 'ARCHIVED'
    postpone_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    coordinator_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_placement_drives_coordinator_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_placement_drives_created_by", ondelete="CASCADE"),
        nullable=False,
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_placement_drives_updated_by", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), onupdate=utc_now, nullable=False
    )

    # Relationships
    schedules: Mapped[List["PlacementSchedule"]] = relationship(
        "PlacementSchedule", back_populates="drive", cascade="all, delete-orphan", order_by="PlacementSchedule.round_order"
    )
    coordinator: Mapped["User"] = relationship("User", foreign_keys=[coordinator_id])
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    updater: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by])


class PlacementSchedule(Base):
    __tablename__ = "placement_schedules"
    __table_args__ = (
        Index("ix_placement_schedules_drive", "drive_id"),
        Index("ix_placement_schedules_time", "start_time", "end_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drive_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("placement_drives.id", name="fk_placement_schedules_drive_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'PRE_PLACEMENT_TALK', 'ONLINE_ASSESSMENT', 'CODING_TEST', 'APTITUDE_TEST', 'TECHNICAL_INTERVIEW', 'HR_INTERVIEW', 'GROUP_DISCUSSION', 'FINAL_ROUND'
    round_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    venue_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    room_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("rooms.id", name="fk_placement_schedules_room_id", ondelete="SET NULL"),
        nullable=True,
    )
    is_online: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="FALSE", nullable=False
    )
    meeting_link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), nullable=False
    )

    drive: Mapped["PlacementDrive"] = relationship("PlacementDrive", back_populates="schedules")
    room: Mapped[Optional["Room"]] = relationship("Room", foreign_keys=[room_id])


class StudentAcademicRecord(Base):
    __tablename__ = "student_academic_records"
    __table_args__ = (
        Index("ix_student_academic_records_student", "student_id", unique=True),
        Index("ix_student_academic_records_cgpa", "cgpa"),
        Index("ix_student_academic_records_grad_year", "graduation_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("students.id", name="fk_student_academic_records_student_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    cgpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grading_scale: Mapped[float] = mapped_column(Float, default=10.0, server_default="10.0", nullable=False)
    percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    active_backlogs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_backlogs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tenth_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    twelfth_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="TRUE", nullable=False
    )
    verified_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_student_acad_verified_by", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), onupdate=utc_now, nullable=False
    )

    student: Mapped["Student"] = relationship("Student", foreign_keys=[student_id])
    verifier: Mapped[Optional["User"]] = relationship("User", foreign_keys=[verified_by])

