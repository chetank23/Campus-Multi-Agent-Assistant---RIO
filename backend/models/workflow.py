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
    Index,
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
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    __table_args__ = (
        Index("ix_notifications_user_id_is_read", "user_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_notif_user_id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
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


class AgentProposal(Base):
    __tablename__ = "agent_proposals"
    __table_args__ = (
        Index("ix_agent_proposals_proposal_id", "proposal_id", unique=True),
        Index("ix_agent_proposals_lookup", "user_id", "proposal_type", "consumed", "superseded"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    proposal_type: Mapped[str] = mapped_column(String(50))  # 'SCHEDULING', 'RESOURCE_BOOKING', 'OPERATION'
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_ap_user_id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    parent_proposal_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="FALSE")
    superseded_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="FALSE")
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        Index("ix_notification_outbox_status", "status"),
        Index("ix_notification_outbox_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id", name="fk_no_notification_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_no_user_id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), default="SSE", server_default="'SSE'")
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", server_default="'PENDING'"
    )  # 'PENDING', 'SENT', 'FAILED', 'DEAD_LETTER'
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_retries: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    last_attempt_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    notification: Mapped["Notification"] = relationship("Notification")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

