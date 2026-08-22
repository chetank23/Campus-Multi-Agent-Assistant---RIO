"""
backend/models/resources.py
----------------------------
Resources domain:
  Resource, ResourceBooking
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .identity import User


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(30),
        CheckConstraint(
            "resource_type IN ('LAB','SEMINAR_HALL','PROJECTOR','AUDITORIUM','EQUIPMENT')",
            name="ck_resources_resource_type",
        ),
        nullable=True,
    )
    location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", server_default="'ACTIVE'"
    )

    bookings: Mapped[list["ResourceBooking"]] = relationship(
        "ResourceBooking", back_populates="resource"
    )


class ResourceBooking(Base):
    __tablename__ = "resource_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("resources.id", name="fk_rb_resource_id"),
        nullable=True,
    )
    requested_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_rb_requested_by"), nullable=True
    )
    date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    start_time: Mapped[Optional[datetime.time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[datetime.time]] = mapped_column(Time, nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CANCELLED')",
            name="ck_rb_status",
        ),
        nullable=True,
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_rb_approved_by"), nullable=True
    )

    resource: Mapped[Optional["Resource"]] = relationship(
        "Resource", back_populates="bookings"
    )
    requester: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[requested_by],
        back_populates="resource_bookings_requested",
    )
    approver: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[approved_by],
        back_populates="resource_bookings_approved",
    )
