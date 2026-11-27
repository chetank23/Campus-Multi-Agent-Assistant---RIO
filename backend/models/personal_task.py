"""
backend/models/personal_task.py
-------------------------------
Personal To-Do List / Notepad model for authenticated Students and Faculty.
Strictly scoped by user_id ownership.
"""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class PersonalTask(Base):
    __tablename__ = "personal_tasks"

    __table_args__ = (
        Index("ix_personal_tasks_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_personal_tasks_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    priority: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_personal_tasks_priority"),
        default="MEDIUM",
        server_default="'MEDIUM'",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(15),
        CheckConstraint("status IN ('PENDING', 'COMPLETED')", name="ck_personal_tasks_status"),
        default="PENDING",
        server_default="'PENDING'",
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=_utc_now, onupdate=_utc_now, server_default=func.now(), nullable=False
    )

    owner = relationship("User", foreign_keys=[user_id])
