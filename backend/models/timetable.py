"""
backend/models/timetable.py
---------------------------
Timetable domain:
  TimetableVersion, Timetable

The composite indexes on (faculty_id, slot_id), (room_id, slot_id),
(section_id, slot_id) are defined here via __table_args__ so that Alembic
autogenerate picks them up in the initial migration.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .identity import User
    from .academic import (
        AcademicYear,
        Department,
        Program,
        Semester,
        Section,
        Batch,
        Faculty,
    )
    from .courses import Course
    from .space_time import Room, TimeSlot


class TimetableVersion(Base):
    __tablename__ = "timetable_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    academic_year_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("academic_years.id", name="fk_tv_academic_year_id"),
        nullable=True,
    )
    version_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('DRAFT','GENERATED','HOD_REVIEW','HOD_APPROVED',"
            "'COORDINATOR_REVIEW','ADMIN_REVIEW','APPROVED','PUBLISHED',"
            "'REJECTED','ARCHIVED')",
            name="ck_tv_status",
        ),
        nullable=True,
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_tv_created_by"), nullable=True
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_tv_approved_by"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, server_default=func.now()
    )
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    academic_year: Mapped[Optional["AcademicYear"]] = relationship(
        "AcademicYear", back_populates="timetable_versions"
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by], back_populates="timetable_versions_created"
    )
    approver: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[approved_by], back_populates="timetable_versions_approved"
    )
    timetable_entries: Mapped[list["Timetable"]] = relationship(
        "Timetable", back_populates="version"
    )


class Timetable(Base):
    __tablename__ = "timetable"

    # Composite indexes — the exact lookups the validator and solver hit hardest (§5.2)
    __table_args__ = (
        Index("ix_timetable_faculty_slot", "faculty_id", "slot_id"),
        Index("ix_timetable_room_slot", "room_id", "slot_id"),
        Index("ix_timetable_section_slot", "section_id", "slot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("timetable_version.id", name="fk_tt_version_id"),
        nullable=True,
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_tt_department_id"),
        nullable=True,
    )
    program_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_tt_program_id"), nullable=True
    )
    semester_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("semesters.id", name="fk_tt_semester_id"), nullable=True
    )
    section_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sections.id", name="fk_tt_section_id"), nullable=True
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("batches.id", name="fk_tt_batch_id"), nullable=True
    )
    course_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("courses.id", name="fk_tt_course_id"), nullable=True
    )
    faculty_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("faculty.id", name="fk_tt_faculty_id"), nullable=True
    )
    room_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("rooms.id", name="fk_tt_room_id"), nullable=True
    )
    slot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("time_slots.id", name="fk_tt_slot_id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", server_default="'DRAFT'"
    )

    version: Mapped[Optional["TimetableVersion"]] = relationship(
        "TimetableVersion", back_populates="timetable_entries"
    )
    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="timetable_entries"
    )
    program: Mapped[Optional["Program"]] = relationship(
        "Program", back_populates="timetable_entries"
    )
    semester: Mapped[Optional["Semester"]] = relationship(
        "Semester", back_populates="timetable_entries"
    )
    section: Mapped[Optional["Section"]] = relationship(
        "Section", back_populates="timetable_entries"
    )
    batch: Mapped[Optional["Batch"]] = relationship(
        "Batch", back_populates="timetable_entries"
    )
    course: Mapped[Optional["Course"]] = relationship(
        "Course", back_populates="timetable_entries"
    )
    faculty: Mapped[Optional["Faculty"]] = relationship(
        "Faculty", back_populates="timetable_entries"
    )
    room: Mapped[Optional["Room"]] = relationship("Room", back_populates="timetable_entries")
    slot: Mapped[Optional["TimeSlot"]] = relationship(
        "TimeSlot", back_populates="timetable_entries"
    )
