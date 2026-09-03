import pytest
from datetime import time, date
from backend.schemas.timetable_generation import (
    GenerationScope, OptSection, OptBatch, OptCourse, OptCourseAssignment,
    OptFaculty, OptFacultyAvailability, OptTimeSlot, OptRoom, OptLab,
    OptAcademicCalendar, OptElectiveGroup, OptElectiveGroupCourse,
    OptimizerInput, TimetableEntryResult
)
from backend.optimizer.validator import ValidationResult, ValidationViolation
from backend.optimizer.scorer import compute_score

def create_base_input():
    scope = GenerationScope(
        academic_year_id=1, semester_id=1, department_id=1, program_id=1
    )
    
    sections = [
        OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=60)
    ]
    
    courses = [
        OptCourse(id=1, department_id=1, course_type='CORE', credits=3, lecture_hours=2, tutorial_hours=0, practical_hours=0, requires_lab=False),
        OptCourse(id=2, department_id=1, course_type='LAB', credits=1, lecture_hours=0, tutorial_hours=0, practical_hours=2, requires_lab=True)
    ]
    
    faculty = [
        OptFaculty(id=1, department_id=1, max_weekly_load=16),
        OptFaculty(id=2, department_id=1, max_weekly_load=16)
    ]
    
    assignments = [
        OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
        OptCourseAssignment(id=2, course_id=2, faculty_id=2, section_id=1)
    ]
    
    slots = [
        OptTimeSlot(id=1, day='MON', start_time=time(9, 0), end_time=time(10, 0), slot_type='THEORY'),
        OptTimeSlot(id=2, day='MON', start_time=time(10, 0), end_time=time(11, 0), slot_type='THEORY'),
        OptTimeSlot(id=3, day='MON', start_time=time(14, 0), end_time=time(16, 0), slot_type='LAB'), # late lab slot
        OptTimeSlot(id=4, day='TUE', start_time=time(9, 0), end_time=time(10, 0), slot_type='THEORY'),
        OptTimeSlot(id=5, day='TUE', start_time=time(10, 0), end_time=time(12, 0), slot_type='LAB') # early lab slot
    ]
    
    rooms = [
        OptRoom(id=1, building_id=1, capacity=70, room_type='CLASSROOM'),
        OptRoom(id=2, building_id=1, capacity=70, room_type='LAB')
    ]
    
    labs = [
        OptLab(id=1, room_id=2, department_id=1)
    ]
    
    # Faculty 1 prefers slot 1
    availability = [
        OptFacultyAvailability(id=1, faculty_id=1, slot_id=1, availability='PREFERRED', preference=1),
        OptFacultyAvailability(id=2, faculty_id=1, slot_id=2, availability='AVAILABLE', preference=0)
    ]
    
    return OptimizerInput(
        scope=scope,
        sections=sections,
        courses=courses,
        faculty=faculty,
        course_assignments=assignments,
        time_slots=slots,
        rooms=rooms,
        labs=labs,
        faculty_availability=availability
    )

def test_scorer_perfect_timetable():
    # A perfect timetable should have:
    # - No gaps (contiguous classes)
    # - Faculty in preferred slots
    # - No room changes (or minimum possible)
    # - Early labs (before 14:00)
    # - Balanced workload
    
    opt_input = create_base_input()
    
    entries = [
        # Faculty 1 teaches course 1 in preferred slot 1, room 1
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=4, hour_type='THEORY'), # Tue morning
        
        # Faculty 2 teaches lab (course 2) in early lab slot 5, room 2
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=5, hour_type='PRACTICAL')
    ]
    
    val_result = ValidationResult(is_valid=True, violations=[])
    
    score = compute_score(val_result, entries, opt_input)
    
    # Perfect score check
    # Gaps: 0 (faculty and student only have 1 class per day or contiguous) -> quality 1.0
    # Preferred: Faculty 1 assigned slot 1 (preferred) -> quality 1.0
    # Room change: Only 1 room used per day (Mon: Room 1, Tue: Room 1 and Room 2 but different hours, wait.. Tue has slot 4 and 5)
    # Ah, Tue has slot 4 and 5. Room 1 then Room 2. So that's 1 room change. Max possible is 2 classes - 1 = 1 room change.
    # So actual = 1, max = 1. Quality = 1.0 - (1/1) = 0.0 for room change!
    # Let's fix entries so room change is 0. Wait, course 2 must be in LAB. Course 1 must be in CLASSROOM. 
    # If they are on the same day, they MUST change rooms. Max possible room change = 1. Actual = 1.
    # If max = 1, and actual = 1, quality is 0.0! That would bring score down.
    # Let's put them on different days.
    # Mon: Slot 1 (Course 1), Slot 2 (Course 1). Wait, Course 1 is 2 theory hours.
    
    entries_perfect = [
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=2, hour_type='THEORY'), # Mon morning contiguous
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=5, hour_type='PRACTICAL') # Tue morning
    ]
    
    # Check max_preferred. F1 teaches 2 hours total. F1 has 1 preferred slot available (slot 1).
    # So max_preferred = min(2, 1) = 1.
    # Actual preferred = 1 (assigned slot 1). Quality = 1/1 = 1.0.
    
    # Room changes: Mon = 2 classes, both Room 1. Actual changes = 0. Max possible = 1. Quality = 1.0.
    # Tue = 1 class, Room 2. Actual changes = 0. Max possible = 0.
    
    # Late Labs: 0. Max possible = 1. Quality = 1.0.
    
    # Workload balance: F1 teaches 2 hours, F2 teaches 1 hour (wait, practical is 2 hours).
    # Let's make practical 2 hours. course 2 practical_hours = 2.
    # Since slot 5 is length 2, it counts as 1 entry in this simplified test. Wait, the scorer counts hours by number of entries!
    # Let's make F1 teach 2 entries, F2 teach 2 entries.
    entries_perfect = [
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=2, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=4, hour_type='PRACTICAL'), # dummy early lab slot
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=5, hour_type='PRACTICAL')
    ]
    
    score = compute_score(val_result, entries_perfect, opt_input)
    assert score['faculty_gap_quality'] == 1.0
    assert score['student_gap_quality'] == 1.0
    assert score['preferred_slot_quality'] == 1.0
    assert score['room_change_quality'] == 1.0
    assert score['late_lab_quality'] == 1.0
    assert score['workload_balance_quality'] == 1.0
    assert score['total_score'] == 100.0

def test_scorer_progressively_worse():
    opt_input = create_base_input()
    val_result = ValidationResult(is_valid=True, violations=[])
    
    # Perfect
    entries_perfect = [
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=2, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=4, hour_type='PRACTICAL'), 
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=5, hour_type='PRACTICAL')
    ]
    score_perfect = compute_score(val_result, entries_perfect, opt_input)
    assert score_perfect['total_score'] == 100.0
    
    # Worse 1: Late Lab (slot 3)
    entries_worse_1 = [
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=2, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=3, hour_type='PRACTICAL'), # LATE LAB
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=4, hour_type='PRACTICAL')
    ]
    score_worse_1 = compute_score(val_result, entries_worse_1, opt_input)
    assert score_worse_1['total_score'] < score_perfect['total_score']
    assert score_worse_1['late_lab_quality'] < 1.0
    
    # Worse 2: Faculty Gap (slot 1 and 4 on same day MON)
    # We change slot 4 to day MON
    opt_input.time_slots[3].day = 'MON'
    entries_worse_2 = [
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=4, hour_type='THEORY'), # GAP!
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=3, hour_type='PRACTICAL'), # LATE
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=5, hour_type='PRACTICAL') # TUE
    ]
    score_worse_2 = compute_score(val_result, entries_worse_2, opt_input)
    assert score_worse_2['total_score'] < score_worse_1['total_score']
    assert score_worse_2['faculty_gap_quality'] < 1.0
    
def test_scorer_determinism():
    opt_input = create_base_input()
    val_result = ValidationResult(is_valid=True, violations=[])
    entries = [
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=3, hour_type='PRACTICAL')
    ]
    
    score1 = compute_score(val_result, entries, opt_input)
    score2 = compute_score(val_result, entries, opt_input)
    
    assert score1 == score2

def test_scorer_hard_violations_separate():
    opt_input = create_base_input()
    val_result = ValidationResult(
        is_valid=False, 
        violations=[ValidationViolation(severity="HARD", message="Double booking")]
    )
    entries = [
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=1, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=1, room_id=1, slot_id=2, hour_type='THEORY'),
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=4, hour_type='PRACTICAL'), 
        TimetableEntryResult(course_assignment_id=2, room_id=2, slot_id=5, hour_type='PRACTICAL')
    ]
    
    score = compute_score(val_result, entries, opt_input)
    
    # Soft quality should still be perfect (100) despite hard violation
    assert score['total_score'] == 100.0
    assert score['hard_violations'] == 1
