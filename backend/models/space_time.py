"""
backend/models/space_time.py
-----------------------------
Space & Time domain:
  Building, Room, Lab, TimeSlot, FacultyAvailability, AcademicCalendar
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
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
    from .academic import Department, Faculty, AcademicYear
    from .timetable import TimetableEntry


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    number_of_floors: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="building")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    building_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("buildings.id", name="fk_rooms_building_id"), nullable=True
    )
    room_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    floor_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    room_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        CheckConstraint(
            "room_type IN ('CLASSROOM','LAB','SEMINAR_HALL','AUDITORIUM','MEETING_ROOM')",
            name="ck_rooms_room_type",
        ),
        nullable=True,
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_rooms_department_id"),
        nullable=True,
    )
    has_projector: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="FALSE"
    )
    has_smart_board: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="FALSE"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="ACTIVE", server_default="'ACTIVE'"
    )

    building: Mapped[Optional["Building"]] = relationship(
        "Building", back_populates="rooms"
    )
    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="rooms"
    )
    lab: Mapped[Optional["Lab"]] = relationship(
        "Lab", back_populates="room", uselist=False
    )
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="room"
    )


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("rooms.id", name="fk_labs_room_id"), nullable=True
    )
    lab_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_labs_department_id"),
        nullable=True,
    )
    computer_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    equipment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    software: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    room: Mapped[Optional["Room"]] = relationship("Room", back_populates="lab")
    department: Mapped[Optional["Department"]] = relationship(
        "Department", foreign_keys=[department_id]
    )


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    start_time: Mapped[Optional[datetime.time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[datetime.time]] = mapped_column(Time, nullable=True)
    slot_type: Mapped[Optional[str]] = mapped_column(
        String(10),
        CheckConstraint(
            "slot_type IN ('CLASS','BREAK','LUNCH')",
            name="ck_time_slots_slot_type",
        ),
        nullable=True,
    )

    faculty_availability: Mapped[list["FacultyAvailability"]] = relationship(
        "FacultyAvailability", back_populates="slot"
    )
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="slot"
    )


class FacultyAvailability(Base):
    __tablename__ = "faculty_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    faculty_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("faculty.id", name="fk_fa_faculty_id"), nullable=True
    )
    slot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("time_slots.id", name="fk_fa_slot_id"), nullable=True
    )
    availability: Mapped[Optional[str]] = mapped_column(
        String(15),
        CheckConstraint(
            "availability IN ('AVAILABLE','UNAVAILABLE','PREFERRED')",
            name="ck_fa_availability",
        ),
        nullable=True,
    )
    preference: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    faculty: Mapped[Optional["Faculty"]] = relationship(
        "Faculty", back_populates="availability"
    )
    slot: Mapped[Optional["TimeSlot"]] = relationship(
        "TimeSlot", back_populates="faculty_availability"
    )


class AcademicCalendar(Base):
    __tablename__ = "academic_calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    academic_year_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("academic_years.id", name="fk_ac_academic_year_id"),
        nullable=True,
    )
    date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    event_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        CheckConstraint(
            "event_type IN ('HOLIDAY','WORKING_DAY','EXAM','EVENT','VACATION')",
            name="ck_ac_event_type",
        ),
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    academic_year: Mapped[Optional["AcademicYear"]] = relationship(
        "AcademicYear", foreign_keys=[academic_year_id]
    )
