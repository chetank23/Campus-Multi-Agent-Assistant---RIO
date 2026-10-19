import pytest
from datetime import time, date
from backend.schemas.timetable_generation import (
    OptimizerInput, GenerationScope, OptSection, OptCourse, OptCourseAssignment,
    OptFaculty, OptRoom, OptTimeSlot, OptAcademicCalendar,
    OptElectiveGroup, OptElectiveGroupCourse
)
from backend.optimizer.timetable_solver import TimetableSolver

def test_academic_calendar_does_not_disable_weekly_slots():
    # 1 TimeSlot (Monday)
    ts = OptTimeSlot(id=1, day="MON", start_time=time(9, 0), end_time=time(10, 0), slot_type="CLASS")
    
    # 1 Calendar record that falls on a Monday
    ac = OptAcademicCalendar(id=1, date=date(2026, 8, 31), event_type="HOLIDAY")
    
    c = OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=1, tutorial_hours=0, practical_hours=0, requires_lab=False)
    s = OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)
    f = OptFaculty(id=1, department_id=1, max_weekly_load=40)
    a = OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1, batch_id=None)
    r = OptRoom(id=1, building_id=1, capacity=50, room_type="CLASSROOM")
    scope = GenerationScope(academic_year_id=1, semester_id=1, department_id=1, program_id=1)
    
    opt_input = OptimizerInput(
        scope=scope,
        sections=[s],
        courses=[c],
        course_assignments=[a],
        faculty=[f],
        faculty_availability=[],
        rooms=[r],
        labs=[],
        time_slots=[ts],
        academic_calendar=[ac],
        elective_groups=[],
        elective_group_courses=[]
    )
    
    solver = TimetableSolver(opt_input, time_limit=10)
    result = solver.solve()
    
    assert result.feasible is True
    assert len(result.entries) == 1
    assert result.entries[0].slot_id == 1

def test_elective_group_constraint_prevents_overlap():
    c1 = OptCourse(id=1, department_id=1, course_type="ELECTIVE", credits=3, lecture_hours=1, tutorial_hours=0, practical_hours=0, requires_lab=False)
    c2 = OptCourse(id=2, department_id=1, course_type="ELECTIVE", credits=3, lecture_hours=1, tutorial_hours=0, practical_hours=0, requires_lab=False)
    
    eg = OptElectiveGroup(id=1, semester_id=1, department_id=1)
    egc1 = OptElectiveGroupCourse(id=1, group_id=1, course_id=1)
    egc2 = OptElectiveGroupCourse(id=2, group_id=1, course_id=2)
    
    s = OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)
    f1 = OptFaculty(id=1, department_id=1, max_weekly_load=40)
    f2 = OptFaculty(id=2, department_id=1, max_weekly_load=40)
    a1 = OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1, batch_id=None)
    a2 = OptCourseAssignment(id=2, course_id=2, faculty_id=2, section_id=1, batch_id=None)
    
    r1 = OptRoom(id=1, building_id=1, capacity=50, room_type="CLASSROOM")
    r2 = OptRoom(id=2, building_id=1, capacity=50, room_type="CLASSROOM")
    
    ts = OptTimeSlot(id=1, day="MON", start_time=time(9, 0), end_time=time(10, 0), slot_type="CLASS")
    scope = GenerationScope(academic_year_id=1, semester_id=1, department_id=1, program_id=1)
    
    opt_input = OptimizerInput(
        scope=scope,
        sections=[s],
        courses=[c1, c2],
        course_assignments=[a1, a2],
        faculty=[f1, f2],
        faculty_availability=[],
        rooms=[r1, r2],
        labs=[],
        time_slots=[ts],
        academic_calendar=[],
        elective_groups=[eg],
        elective_group_courses=[egc1, egc2]
    )
    
    solver = TimetableSolver(opt_input, time_limit=10)
    result = solver.solve()
    
    assert result.feasible is False
    
    ts2 = OptTimeSlot(id=2, day="TUE", start_time=time(9, 0), end_time=time(10, 0), slot_type="CLASS")
    opt_input.time_slots = [ts, ts2]
    
    solver2 = TimetableSolver(opt_input, time_limit=10)
    result2 = solver2.solve()
    
    assert result2.feasible is True
    assert len(result2.entries) == 2
    assert result2.entries[0].slot_id != result2.entries[1].slot_id
