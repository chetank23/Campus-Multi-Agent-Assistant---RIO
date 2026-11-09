"""
backend/models/system_setting.py
--------------------------------
Database-backed mutable application configuration for RIO-MJP:
- General settings (Institution metadata, Timezone, Notification defaults)
- Timetable settings (Default working days, period timings, generation constraints)
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional, Any, Dict

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.utils.datetime_utils import utc_now
from .base import Base

if TYPE_CHECKING:
    from .identity import User


class SystemSetting(Base):
    __tablename__ = "system_settings"
    __table_args__ = (
        Index("ix_system_settings_category", "category"),
    )

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # GENERAL, TIMETABLE, NOTIFICATIONS, SYSTEM
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_ss_updated_by_id"), nullable=True
    )

    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])

