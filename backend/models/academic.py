"""
backend/models/academic.py
--------------------------
Academic structure domain:
  Department, Program, AcademicYear, Semester, Section, Batch, Student, Faculty
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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .identity import User
    from .courses import Course, CourseAssignment, ElectiveGroup
    from .space_time import FacultyAvailability, Room
    from .timetable import TimetableEntry, TimetableVersion


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)

    # Relationships
    members: Mapped[list["User"]] = relationship(
        "User", foreign_keys="User.department_id", back_populates="department"
    )
    programs: Mapped[list["Program"]] = relationship("Program", back_populates="department")
    sections: Mapped[list["Section"]] = relationship("Section", back_populates="department")
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="department")
    faculty_members: Mapped[list["Faculty"]] = relationship(
        "Faculty", back_populates="department"
    )
    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="department")
    elective_groups: Mapped[list["ElectiveGroup"]] = relationship(
        "ElectiveGroup", back_populates="department"
    )
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="department"
    )



class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("departments.id", name="fk_programs_department_id"), nullable=True
    )
    program_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    degree: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="programs"
    )
    sections: Mapped[list["Section"]] = relationship("Section", back_populates="program")
    students: Mapped[list["Student"]] = relationship("Student", back_populates="program")
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="program"
    )


class AcademicYear(Base):
    __tablename__ = "academic_years"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)

    semesters: Mapped[list["Semester"]] = relationship(
        "Semester", back_populates="academic_year"
    )
    timetable_versions: Mapped[list["TimetableVersion"]] = relationship(
        "TimetableVersion", back_populates="academic_year"
    )


class Semester(Base):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    academic_year_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("academic_years.id", name="fk_semesters_academic_year_id"),
        nullable=True,
    )
    semester_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)

    academic_year: Mapped[Optional["AcademicYear"]] = relationship(
        "AcademicYear", back_populates="semesters"
    )
    sections: Mapped[list["Section"]] = relationship("Section", back_populates="semester")
    students: Mapped[list["Student"]] = relationship("Student", back_populates="semester")
    elective_groups: Mapped[list["ElectiveGroup"]] = relationship(
        "ElectiveGroup", back_populates="semester"
    )
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="semester"
    )


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_sections_department_id"),
        nullable=True,
    )
    program_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_sections_program_id"), nullable=True
    )
    semester_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("semesters.id", name="fk_sections_semester_id"), nullable=True
    )
    section_name: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    student_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    class_teacher_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("faculty.id", name="fk_sections_class_teacher_id"), nullable=True
    )

    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="sections"
    )
    program: Mapped[Optional["Program"]] = relationship("Program", back_populates="sections")
    semester: Mapped[Optional["Semester"]] = relationship("Semester", back_populates="sections")
    class_teacher: Mapped[Optional["Faculty"]] = relationship(
        "Faculty", foreign_keys=[class_teacher_id], back_populates="sections_as_class_teacher"
    )
    batches: Mapped[list["Batch"]] = relationship("Batch", back_populates="section")
    students: Mapped[list["Student"]] = relationship("Student", back_populates="section")
    course_assignments: Mapped[list["CourseAssignment"]] = relationship(
        "CourseAssignment", back_populates="section"
    )
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="section"
    )


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sections.id", name="fk_batches_section_id"), nullable=True
    )
    batch_name: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    student_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    section: Mapped[Optional["Section"]] = relationship("Section", back_populates="batches")
    students: Mapped[list["Student"]] = relationship("Student", back_populates="batch")
    course_assignments: Mapped[list["CourseAssignment"]] = relationship(
        "CourseAssignment", back_populates="batch"
    )
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="batch"
    )


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_students_user_id"), nullable=True
    )
    student_id: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_students_department_id"),
        nullable=True,
    )
    program_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("programs.id", name="fk_students_program_id"), nullable=True
    )
    semester_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("semesters.id", name="fk_students_semester_id"), nullable=True
    )
    section_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sections.id", name="fk_students_section_id"), nullable=True
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("batches.id", name="fk_students_batch_id"), nullable=True
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="student_profile")
    department: Mapped[Optional["Department"]] = relationship(
        "Department", foreign_keys=[department_id]
    )
    program: Mapped[Optional["Program"]] = relationship(
        "Program", back_populates="students"
    )
    semester: Mapped[Optional["Semester"]] = relationship(
        "Semester", back_populates="students"
    )
    section: Mapped[Optional["Section"]] = relationship("Section", back_populates="students")
    batch: Mapped[Optional["Batch"]] = relationship("Batch", back_populates="students")


class Faculty(Base):
    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_faculty_user_id"), nullable=True
    )
    faculty_id: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("departments.id", name="fk_faculty_department_id"),
        nullable=True,
    )
    designation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    specialization: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    areas_of_interest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_weekly_load: Mapped[int] = mapped_column(Integer, default=16, server_default="16")


    user: Mapped[Optional["User"]] = relationship("User", back_populates="faculty_profile")
    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="faculty_members"
    )
    sections_as_class_teacher: Mapped[list["Section"]] = relationship(
        "Section", foreign_keys="Section.class_teacher_id", back_populates="class_teacher"
    )
    availability: Mapped[list["FacultyAvailability"]] = relationship(
        "FacultyAvailability", back_populates="faculty"
    )
    course_assignments: Mapped[list["CourseAssignment"]] = relationship(
        "CourseAssignment", back_populates="faculty"
    )
    timetable_entries: Mapped[list["TimetableEntry"]] = relationship(
        "TimetableEntry", back_populates="faculty"
    )
