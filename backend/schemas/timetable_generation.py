from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import time, date

class GenerationScope(BaseModel):
    academic_year_id: int
    semester_id: int
    department_id: int
    program_id: int
    section_ids: Optional[List[int]] = None
    building_ids: Optional[List[int]] = None
    room_ids: Optional[List[int]] = None
    lab_ids: Optional[List[int]] = None
    time_slot_ids: Optional[List[int]] = None

# Internal structures for the optimizer
class OptSection(BaseModel):
    id: int
    department_id: int
    program_id: int
    semester_id: int
    student_count: int

class OptBatch(BaseModel):
    id: int
    section_id: int
    student_count: int

class OptCourse(BaseModel):
    id: int
    department_id: int
    course_type: str
    credits: int
    lecture_hours: int
    tutorial_hours: int
    practical_hours: int
    requires_lab: bool

class OptCourseAssignment(BaseModel):
    id: int
    course_id: int
    faculty_id: int
    section_id: Optional[int] = None
    batch_id: Optional[int] = None

class OptFaculty(BaseModel):
    id: int
    department_id: int
    max_weekly_load: int

class OptFacultyAvailability(BaseModel):
    id: int
    faculty_id: int
    slot_id: int
    availability: str
    preference: int

class OptTimeSlot(BaseModel):
    id: int
    day: str
    start_time: time
    end_time: time
    slot_type: str

class OptRoom(BaseModel):
    id: int
    building_id: int
    capacity: int
    room_type: str
    department_id: Optional[int] = None

class OptLab(BaseModel):
    id: int
    room_id: int
    department_id: int

class OptAcademicCalendar(BaseModel):
    id: int
    date: date
    event_type: str

class OptElectiveGroup(BaseModel):
    id: int
    semester_id: int
    department_id: int

class OptElectiveGroupCourse(BaseModel):
    id: int
    group_id: int
    course_id: int

class OptimizerInput(BaseModel):
    scope: GenerationScope
    sections: List[OptSection] = Field(default_factory=list)
    batches: List[OptBatch] = Field(default_factory=list)
    courses: List[OptCourse] = Field(default_factory=list)
    course_assignments: List[OptCourseAssignment] = Field(default_factory=list)
    faculty: List[OptFaculty] = Field(default_factory=list)
    faculty_availability: List[OptFacultyAvailability] = Field(default_factory=list)
    time_slots: List[OptTimeSlot] = Field(default_factory=list)
    rooms: List[OptRoom] = Field(default_factory=list)
    labs: List[OptLab] = Field(default_factory=list)
    academic_calendar: List[OptAcademicCalendar] = Field(default_factory=list)
    elective_groups: List[OptElectiveGroup] = Field(default_factory=list)
    elective_group_courses: List[OptElectiveGroupCourse] = Field(default_factory=list)

class TimetableEntryResult(BaseModel):
    course_assignment_id: int
    room_id: int
    slot_id: int
    hour_type: str

class GenerationSummary(BaseModel):
    status: str
    message: str
    loaded_sections: int
    loaded_courses: int
    loaded_faculty: int
    loaded_rooms: int
    loaded_time_slots: int
    solve_time_seconds: Optional[float] = None
    generated_entries: Optional[List[TimetableEntryResult]] = None
