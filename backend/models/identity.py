"""
backend/models/identity.py
--------------------------
Users table.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.utils.datetime_utils import utc_now
from .base import Base

if TYPE_CHECKING:
    from .academic import Department, Faculty, Student
    from .workflow import AuditLog, ChangeRequest, Notification
    from .resources import ResourceBooking
    from .timetable import TimetableVersion


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        String(30),
        CheckConstraint(
            "role IN ('STUDENT','FACULTY','ADMIN','SUPER_ADMIN')",
            name="ck_users_role",
        ),
        nullable=False,
    )
    # Forward reference — departments table is defined in academic.py
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_users_department_id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )

    # Relationships (back-populated from other models)
    department: Mapped[Optional["Department"]] = relationship(
        "Department", foreign_keys=[department_id], back_populates="members"
    )
    faculty_profile: Mapped[Optional["Faculty"]] = relationship(
        "Faculty", back_populates="user", uselist=False
    )
    student_profile: Mapped[Optional["Student"]] = relationship(
        "Student", back_populates="user", uselist=False
    )
    change_requests: Mapped[list["ChangeRequest"]] = relationship(
        "ChangeRequest", foreign_keys="ChangeRequest.requested_by", back_populates="requester"
    )
    reviewed_requests: Mapped[list["ChangeRequest"]] = relationship(
        "ChangeRequest", foreign_keys="ChangeRequest.reviewed_by", back_populates="reviewer"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="user"
    )
    resource_bookings_requested: Mapped[list["ResourceBooking"]] = relationship(
        "ResourceBooking", foreign_keys="ResourceBooking.requested_by", back_populates="requester"
    )
    resource_bookings_approved: Mapped[list["ResourceBooking"]] = relationship(
        "ResourceBooking", foreign_keys="ResourceBooking.approved_by", back_populates="approver"
    )
    timetable_versions_created: Mapped[list["TimetableVersion"]] = relationship(
        "TimetableVersion", foreign_keys="TimetableVersion.created_by", back_populates="creator"
    )
    timetable_versions_approved: Mapped[list["TimetableVersion"]] = relationship(
        "TimetableVersion", foreign_keys="TimetableVersion.approved_by", back_populates="approver"
    )
