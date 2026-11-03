"""
backend/models/substitution.py
------------------------------
Faculty Substitution Domain Models:
  FacultySubstitution

Tracks single-date temporary faculty substitution requests, candidate ranking,
approval workflows, and multi-party notifications while strictly preserving
the canonical recurring master timetable intact.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.utils.datetime_utils import utc_now
from .base import Base

if TYPE_CHECKING:
    from .identity import User
    from .academic import Faculty
    from .timetable import TimetableEntry


class FacultySubstitution(Base):
    __tablename__ = "faculty_substitutions"
    __table_args__ = (
        Index("ix_sub_entry_date", "timetable_entry_id", "substitution_date"),
        Index("ix_sub_date_status", "substitution_date", "status"),
        Index("ix_sub_substitute_date_status", "substitute_faculty_id", "substitution_date", "status"),
        Index("ix_sub_original_date", "original_faculty_id", "substitution_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timetable_entry_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("timetable_entries.id", name="fk_sub_timetable_entry_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    substitution_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, index=True
    )
    original_faculty_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("faculty.id", name="fk_sub_original_faculty_id"),
        nullable=False,
        index=True,
    )
    substitute_faculty_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("faculty.id", name="fk_sub_substitute_faculty_id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('REQUESTED','PROPOSED','APPROVED','REJECTED','CANCELLED')",
            name="ck_sub_status",
        ),
        default="REQUESTED",
        server_default="'REQUESTED'",
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_sub_created_by_id"),
        nullable=False,
    )
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_sub_reviewed_by_id"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, server_default=func.now(), nullable=False
    )

    # Relationships
    timetable_entry: Mapped["TimetableEntry"] = relationship("TimetableEntry")
    original_faculty: Mapped["Faculty"] = relationship(
        "Faculty", foreign_keys=[original_faculty_id]
    )
    substitute_faculty: Mapped[Optional["Faculty"]] = relationship(
        "Faculty", foreign_keys=[substitute_faculty_id]
    )
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by_id])

