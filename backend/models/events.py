"""
backend/models/events.py
------------------------
Campus Events, Club & Activity Coordination Domain Models:
1. CoordinatorCapability: Fine-grained, scoped capabilities for event/club coordination.
2. Club: Student & faculty activity clubs and organizations.
3. CampusEvent: Unified event model covering institutional events and club activities.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
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
    from .space_time import Building, Room
    from .academic import Department, Program, Batch


class CoordinatorCapability(Base):
    __tablename__ = "coordinator_capabilities"
    __table_args__ = (
        Index("ix_coord_cap_user_active", "user_id", "capability", "is_active"),
        Index("ix_coord_cap_scope", "capability", "scope_type", "scope_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_coord_cap_user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'EVENT_COORDINATOR', 'CLUB_COORDINATOR', 'EVENT_DIRECT_PUBLISH'
    scope_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="GLOBAL"
    )  # 'GLOBAL', 'CLUB', 'DEPARTMENT', 'EVENT'
    scope_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="TRUE", nullable=False
    )
    starts_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    assigned_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_coord_cap_assigned_by", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_coord_cap_revoked_by", ondelete="SET NULL"),
        nullable=True,
    )
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    assigner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_by])
    revoker: Mapped[Optional["User"]] = relationship("User", foreign_keys=[revoked_by])


class Club(Base):
    __tablename__ = "clubs"
    __table_args__ = (
        Index("ix_clubs_status", "status"),
        Index("ix_clubs_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'TECHNICAL', 'CULTURAL', 'SPORTS', 'LITERARY', 'COMMUNITY'
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", server_default="'ACTIVE'", nullable=False
    )  # 'ACTIVE', 'INACTIVE'
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_clubs_created_by", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])
    activities: Mapped[List["CampusEvent"]] = relationship(
        "CampusEvent", back_populates="club", cascade="all, delete-orphan"
    )


class CampusEvent(Base):
    __tablename__ = "campus_events"
    __table_args__ = (
        Index("ix_campus_events_status_time", "status", "start_time", "end_time"),
        Index("ix_campus_events_club_id", "club_id"),
        Index("ix_campus_events_category", "category"),
        Index("ix_campus_events_target", "target_audience", "target_department_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'SEMINAR', 'WORKSHOP', 'GUEST_LECTURE', 'TECH_TALK', 'COMPETITION', 'HACKATHON', 'CULTURAL', 'SPORTS', 'INSTITUTIONAL', 'CLUB_ACTIVITY', 'OTHER'
    club_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("clubs.id", name="fk_campus_events_club_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organizer_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    coordinator_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_campus_events_coordinator_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Kolkata", server_default="'Asia/Kolkata'", nullable=False
    )

    building_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("buildings.id", name="fk_campus_events_building_id", ondelete="SET NULL"),
        nullable=True,
    )
    room_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("rooms.id", name="fk_campus_events_room_id", ondelete="SET NULL"),
        nullable=True,
    )
    venue_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    is_online: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="FALSE", nullable=False
    )
    online_link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    target_audience: Mapped[str] = mapped_column(
        String(30), default="ALL", server_default="'ALL'", nullable=False
    )  # 'ALL', 'STUDENT', 'FACULTY', 'DEPARTMENT_ONLY', 'MEMBERS_ONLY'
    target_department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_campus_events_target_dept_id", ondelete="SET NULL"),
        nullable=True,
    )
    target_program_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("programs.id", name="fk_campus_events_target_prog_id", ondelete="SET NULL"),
        nullable=True,
    )
    target_batch_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("batches.id", name="fk_campus_events_target_batch_id", ondelete="SET NULL"),
        nullable=True,
    )
    target_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="TRUE", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="DRAFT", server_default="'DRAFT'", nullable=False
    )  # 'DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PUBLISHED', 'ONGOING', 'COMPLETED', 'REJECTED', 'CANCELLED', 'ARCHIVED'

    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_campus_events_approved_by", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_campus_events_created_by", ondelete="CASCADE"),
        nullable=False,
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_campus_events_updated_by", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    club: Mapped[Optional["Club"]] = relationship("Club", back_populates="activities")
    coordinator: Mapped["User"] = relationship("User", foreign_keys=[coordinator_id])
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    updater: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by])
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])
    building: Mapped[Optional["Building"]] = relationship("Building", foreign_keys=[building_id])
    room: Mapped[Optional["Room"]] = relationship("Room", foreign_keys=[room_id])
    department: Mapped[Optional["Department"]] = relationship("Department", foreign_keys=[target_department_id])
    program: Mapped[Optional["Program"]] = relationship("Program", foreign_keys=[target_program_id])
    batch: Mapped[Optional["Batch"]] = relationship("Batch", foreign_keys=[target_batch_id])

