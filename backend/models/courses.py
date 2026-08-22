"""
backend/models/courses.py
-------------------------
Courses domain:
  Course, CourseAssignment, ElectiveGroup, ElectiveGroupCourse
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .academic import Department, Faculty, Section, Batch, Semester
    from .timetable import Timetable


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    course_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_courses_department_id"),
        nullable=True,
    )
    course_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        CheckConstraint(
            "course_type IN ('THEORY','LAB','TUTORIAL','PROJECT','ELECTIVE')",
            name="ck_courses_course_type",
        ),
        nullable=True,
    )
    credits: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lecture_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tutorial_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    practical_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requires_lab: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="FALSE"
    )

    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="courses"
    )
    course_assignments: Mapped[list["CourseAssignment"]] = relationship(
        "CourseAssignment", back_populates="course"
    )
    elective_group_courses: Mapped[list["ElectiveGroupCourse"]] = relationship(
        "ElectiveGroupCourse", back_populates="course"
    )
    timetable_entries: Mapped[list["Timetable"]] = relationship(
        "Timetable", back_populates="course"
    )


class CourseAssignment(Base):
    __tablename__ = "course_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("courses.id", name="fk_ca_course_id"), nullable=True
    )
    faculty_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("faculty.id", name="fk_ca_faculty_id"), nullable=True
    )
    section_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sections.id", name="fk_ca_section_id"), nullable=True
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("batches.id", name="fk_ca_batch_id"), nullable=True
    )

    course: Mapped[Optional["Course"]] = relationship(
        "Course", back_populates="course_assignments"
    )
    faculty: Mapped[Optional["Faculty"]] = relationship(
        "Faculty", back_populates="course_assignments"
    )
    section: Mapped[Optional["Section"]] = relationship(
        "Section", back_populates="course_assignments"
    )
    batch: Mapped[Optional["Batch"]] = relationship(
        "Batch", back_populates="course_assignments"
    )


class ElectiveGroup(Base):
    __tablename__ = "elective_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    semester_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("semesters.id", name="fk_eg_semester_id"), nullable=True
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_eg_department_id"), nullable=True
    )

    semester: Mapped[Optional["Semester"]] = relationship(
        "Semester", back_populates="elective_groups"
    )
    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="elective_groups"
    )
    elective_group_courses: Mapped[list["ElectiveGroupCourse"]] = relationship(
        "ElectiveGroupCourse", back_populates="group"
    )


class ElectiveGroupCourse(Base):
    __tablename__ = "elective_group_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("elective_groups.id", name="fk_egc_group_id"),
        nullable=True,
    )
    course_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("courses.id", name="fk_egc_course_id"), nullable=True
    )

    group: Mapped[Optional["ElectiveGroup"]] = relationship(
        "ElectiveGroup", back_populates="elective_group_courses"
    )
    course: Mapped[Optional["Course"]] = relationship(
        "Course", back_populates="elective_group_courses"
    )
