"""
backend/models/workflow.py
--------------------------
Workflow, Notifications & Audit domain:
  ChangeRequest, Notification, AuditLog
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.utils.datetime_utils import utc_now
from .base import Base

if TYPE_CHECKING:
    from .identity import User


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requested_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cr_requested_by"), nullable=True
    )
    request_type: Mapped[Optional[str]] = mapped_column(
        String(30),
        CheckConstraint(
            "request_type IN ('TIMETABLE_CHANGE','RESOURCE_REQUEST',"
            "'FACULTY_AVAILABILITY_CHANGE','ROOM_CHANGE')",
            name="ck_cr_request_type",
        ),
        nullable=True,
    )
    related_entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", server_default="'PENDING'"
    )
    reviewed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_cr_reviewed_by"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )

    requester: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[requested_by], back_populates="change_requests"
    )
    reviewer: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[reviewed_by], back_populates="reviewed_requests"
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_notif_user_id"), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="FALSE"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_al_user_id"), nullable=True
    )
    action: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # JSONB for flexible old/new value capture — PostgreSQL-native
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
