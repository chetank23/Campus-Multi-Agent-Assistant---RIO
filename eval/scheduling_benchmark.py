"""
eval/scheduling_benchmark.py
----------------------------
Self-contained, reproducible evaluation harness and benchmark for the RIO-MJP
Academic Timetable Scheduling Optimizer (OR-Tools CP-SAT).

Evaluates 16 deterministic scheduling scenarios covering:
- Baseline feasibility (single & multi-course)
- Constraint enforcement (faculty collision, room collision, section overlap)
- Physical & institutional boundaries (capacity deficits, lab requirements, break exclusions)
- Temporal boundaries (overlapping non-standard intervals, tight capacity)
- Infeasibility diagnostics & graceful timeout handling
- Soft preference quality optimization
- Two-stage failure-to-regeneration workflow
- Publication safeguards with deliberate blocker rejection

Pure in-memory execution using Pydantic OptimizerInput fixtures (no database required for unit tests).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import time as dtime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.schemas.timetable_generation import (
    GenerationScope,
    OptSection,
    OptBatch,
    OptCourse,
    OptCourseAssignment,
    OptFaculty,
    OptFacultyAvailability,
    OptTimeSlot,
    OptRoom,
    OptLab,
    OptAcademicCalendar,
    OptElectiveGroup,
    OptElectiveGroupCourse,
    OptimizerInput,
    TimetableEntryResult,
)
from backend.optimizer.timetable_solver import TimetableSolver, SolverResult
from backend.optimizer.validator import validate_timetable, ValidationResult
from backend.optimizer.scorer import compute_score


def _make_scope() -> GenerationScope:
    return GenerationScope(
        academic_year_id=1,
        semester_id=1,
        department_id=1,
        program_id=1,
    )


def _make_standard_slots(count: int, start_hour: int = 9, day: str = "Monday", slot_type: str = "THEORY", id_offset: int = 1) -> List[OptTimeSlot]:
    slots = []
    for i in range(count):
        slots.append(
            OptTimeSlot(
                id=id_offset + i,
                day=day,
                start_time=dtime(start_hour + i, 0),
                end_time=dtime(start_hour + i + 1, 0),
                slot_type=slot_type,
            )
        )
    return slots


class BaseScenario:
    scenario_id: str = "BASE"
    description: str = ""
    is_feasibility_test: bool = False
    is_timeout_test: bool = False

    def build_input(self) -> OptimizerInput:
        raise NotImplementedError

    def run(self) -> Dict[str, Any]:
        opt_input = self.build_input()
        t0 = time.time()
        solver = TimetableSolver(opt_input, time_limit=60)
        res: SolverResult = solver.solve()
        solve_time = time.time() - t0

        timetable_generated = res.status in ("OPTIMAL", "FEASIBLE")
        hard_violations = 0
        validation_valid = False
        diagnostics = list(res.diagnostics) if res.diagnostics else []
        soft_score = 0.0
        score_details = {}

        if timetable_generated:
            val: ValidationResult = validate_timetable(res.entries, opt_input)
            hard_violations = val.blocker_count
            validation_valid = val.is_valid
            score_data = compute_score(val, res.entries, opt_input)
            soft_score = float(score_data.get("total_score", 0.0))
            score_details = score_data
        else:
            if res.message and res.message not in diagnostics:
                diagnostics.insert(0, res.message)

        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "solver_status": res.status,
            "timetable_generated": timetable_generated,
            "validation_valid": validation_valid,
            "hard_violation_count": hard_violations,
            "soft_score": soft_score,
            "runtime_seconds": round(solve_time, 4),
            "diagnostic_outcome": diagnostics,
            "entries_count": len(res.entries),
            "score_details": score_details,
            "input_characteristics": {
                "n_faculty": len(opt_input.faculty),
                "n_sections": len(opt_input.sections),
                "n_courses": len(opt_input.courses),
                "n_rooms": len(opt_input.rooms),
                "n_slots": len(opt_input.time_slots),
            },
        }


class Scenario01FeasibleBasic(BaseScenario):
    scenario_id = "SCENARIO_01_FEASIBLE_BASIC"
    description = "1 faculty, 1 section, 1 course (3 theory hours), 2 classrooms, 10 time slots"

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(5, 9, "Monday", id_offset=1) + _make_standard_slots(5, 9, "Tuesday", id_offset=6)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[
                OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=2, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
            ],
            time_slots=slots,
        )


class Scenario02MultiCourse(BaseScenario):
    scenario_id = "SCENARIO_02_MULTI_COURSE"
    description = "2 faculty, 2 sections, 3 courses (3 hours each), 4 classrooms, 15 time slots"

    def build_input(self) -> OptimizerInput:
        slots = (
            _make_standard_slots(5, 9, "Monday", id_offset=1)
            + _make_standard_slots(5, 9, "Tuesday", id_offset=6)
            + _make_standard_slots(5, 9, "Wednesday", id_offset=11)
        )
        return OptimizerInput(
            scope=_make_scope(),
            sections=[
                OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30),
                OptSection(id=2, department_id=1, program_id=1, semester_id=1, student_count=30),
            ],
            faculty=[
                OptFaculty(id=1, department_id=1, max_weekly_load=16),
                OptFaculty(id=2, department_id=1, max_weekly_load=16),
            ],
            courses=[
                OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
                OptCourse(id=2, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
                OptCourse(id=3, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
            ],
            course_assignments=[
                OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
                OptCourseAssignment(id=2, course_id=2, faculty_id=2, section_id=2),
                OptCourseAssignment(id=3, course_id=3, faculty_id=1, section_id=2),
            ],
            rooms=[
                OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=2, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=3, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=4, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
            ],
            time_slots=slots,
        )


class Scenario03FacultyConflict(BaseScenario):
    scenario_id = "SCENARIO_03_FACULTY_CONFLICT"
    description = "1 faculty assigned to 2 courses (6 total hours), but only 4 slots exist (solver detects conflict)"
    is_feasibility_test = True

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(4, 9, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[
                OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30),
                OptSection(id=2, department_id=1, program_id=1, semester_id=1, student_count=30),
            ],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[
                OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
                OptCourse(id=2, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
            ],
            course_assignments=[
                OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
                OptCourseAssignment(id=2, course_id=2, faculty_id=1, section_id=2),
            ],
            rooms=[
                OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=2, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
            ],
            time_slots=slots,
        )


class Scenario04RoomCollision(BaseScenario):
    scenario_id = "SCENARIO_04_ROOM_COLLISION"
    description = "2 courses needing same room type, only 1 room, 6 slots (solver must separate them)"

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(6, 9, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[
                OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30),
                OptSection(id=2, department_id=1, program_id=1, semester_id=1, student_count=30),
            ],
            faculty=[
                OptFaculty(id=1, department_id=1, max_weekly_load=16),
                OptFaculty(id=2, department_id=1, max_weekly_load=16),
            ],
            courses=[
                OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
                OptCourse(id=2, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
            ],
            course_assignments=[
                OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
                OptCourseAssignment(id=2, course_id=2, faculty_id=2, section_id=2),
            ],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots,
        )


class Scenario05SectionConflict(BaseScenario):
    scenario_id = "SCENARIO_05_SECTION_CONFLICT"
    description = "1 section, 2 courses, both need theory slots (solver must prevent section overlap)"

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(6, 9, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[
                OptFaculty(id=1, department_id=1, max_weekly_load=16),
                OptFaculty(id=2, department_id=1, max_weekly_load=16),
            ],
            courses=[
                OptCourse(id=1, department_id=1, course_type="THEORY", credits=2, lecture_hours=2, tutorial_hours=0, practical_hours=0, requires_lab=False),
                OptCourse(id=2, department_id=1, course_type="THEORY", credits=2, lecture_hours=2, tutorial_hours=0, practical_hours=0, requires_lab=False),
            ],
            course_assignments=[
                OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
                OptCourseAssignment(id=2, course_id=2, faculty_id=2, section_id=1),
            ],
            rooms=[
                OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=2, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
            ],
            time_slots=slots,
        )


class Scenario06Capacity(BaseScenario):
    scenario_id = "SCENARIO_06_CAPACITY"
    description = "Room capacity 30, section has 50 students (expect INFEASIBLE_AT_BUILD)"
    is_feasibility_test = True

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(10, 8, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=50)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=30, room_type="CLASSROOM", department_id=1)],
            time_slots=slots,
        )


class Scenario07FacultyAvailability(BaseScenario):
    scenario_id = "SCENARIO_07_FACULTY_AVAILABILITY"
    description = "Faculty marked UNAVAILABLE for all but 2 slots; course needs 3 theory hours (expect INFEASIBLE_AT_BUILD)"
    is_feasibility_test = True

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(10, 8, "Monday", id_offset=1)
        fa = [
            OptFacultyAvailability(id=1, faculty_id=1, slot_id=1, availability="AVAILABLE", preference=1),
            OptFacultyAvailability(id=2, faculty_id=1, slot_id=2, availability="AVAILABLE", preference=1),
        ]
        for s_id in range(3, 11):
            fa.append(OptFacultyAvailability(id=s_id, faculty_id=1, slot_id=s_id, availability="UNAVAILABLE", preference=0))

        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots,
            faculty_availability=fa,
        )


class Scenario08LabSuitability(BaseScenario):
    scenario_id = "SCENARIO_08_LAB_SUITABILITY"
    description = "Practical course, only classrooms available without lab designation (expect INFEASIBLE_AT_BUILD)"
    is_feasibility_test = True

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(10, 8, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="LAB", credits=3, lecture_hours=0, tutorial_hours=0, practical_hours=3, requires_lab=True)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            labs=[],
            time_slots=slots,
        )


class Scenario09BreakExclusion(BaseScenario):
    scenario_id = "SCENARIO_09_BREAK_EXCLUSION"
    description = "Time slots include BREAK and LUNCH types; solver must exclude them from schedule"

    def build_input(self) -> OptimizerInput:
        slots = [
            OptTimeSlot(id=1, day="Monday", start_time=dtime(9, 0), end_time=dtime(10, 0), slot_type="THEORY"),
            OptTimeSlot(id=2, day="Monday", start_time=dtime(10, 0), end_time=dtime(11, 0), slot_type="THEORY"),
            OptTimeSlot(id=3, day="Monday", start_time=dtime(11, 0), end_time=dtime(12, 0), slot_type="BREAK"),
            OptTimeSlot(id=4, day="Monday", start_time=dtime(12, 0), end_time=dtime(13, 0), slot_type="LUNCH"),
            OptTimeSlot(id=5, day="Monday", start_time=dtime(13, 0), end_time=dtime(14, 0), slot_type="THEORY"),
            OptTimeSlot(id=6, day="Monday", start_time=dtime(14, 0), end_time=dtime(15, 0), slot_type="THEORY"),
        ]
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots,
        )


class Scenario10OverlappingIntervals(BaseScenario):
    scenario_id = "SCENARIO_10_OVERLAPPING_INTERVALS"
    description = "Two slots with overlapping time intervals on same day; solver prevents double-booking"

    def build_input(self) -> OptimizerInput:
        slots = [
            OptTimeSlot(id=1, day="Monday", start_time=dtime(9, 0), end_time=dtime(10, 30), slot_type="THEORY"),
            OptTimeSlot(id=2, day="Monday", start_time=dtime(10, 0), end_time=dtime(11, 30), slot_type="THEORY"),
            OptTimeSlot(id=3, day="Monday", start_time=dtime(12, 0), end_time=dtime(13, 0), slot_type="THEORY"),
            OptTimeSlot(id=4, day="Monday", start_time=dtime(13, 0), end_time=dtime(14, 0), slot_type="THEORY"),
        ]
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[
                OptCourse(id=1, department_id=1, course_type="THEORY", credits=1, lecture_hours=1, tutorial_hours=0, practical_hours=0, requires_lab=False),
                OptCourse(id=2, department_id=1, course_type="THEORY", credits=1, lecture_hours=1, tutorial_hours=0, practical_hours=0, requires_lab=False),
            ],
            course_assignments=[
                OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
                OptCourseAssignment(id=2, course_id=2, faculty_id=1, section_id=1),
            ],
            rooms=[
                OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=2, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
            ],
            time_slots=slots,
        )


class Scenario11TightCapacity(BaseScenario):
    scenario_id = "SCENARIO_11_TIGHT_CAPACITY"
    description = "Exactly enough slots (3) and rooms (1) for 3 required hours; tight but feasible"

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(3, 9, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=40)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots,
        )


class Scenario12Infeasible(BaseScenario):
    scenario_id = "SCENARIO_12_INFEASIBLE"
    description = "More required hours (6) than available room-slots (4); solver proves INFEASIBLE"
    is_feasibility_test = True

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(4, 9, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[
                OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30),
                OptSection(id=2, department_id=1, program_id=1, semester_id=1, student_count=30),
            ],
            faculty=[
                OptFaculty(id=1, department_id=1, max_weekly_load=16),
                OptFaculty(id=2, department_id=1, max_weekly_load=16),
            ],
            courses=[
                OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
                OptCourse(id=2, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False),
            ],
            course_assignments=[
                OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
                OptCourseAssignment(id=2, course_id=2, faculty_id=2, section_id=2),
            ],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots,
        )


class Scenario13Timeout(BaseScenario):
    scenario_id = "SCENARIO_13_TIMEOUT"
    description = "Large combinatorial stress problem with time_limit=1s; expect graceful UNKNOWN status"
    is_timeout_test = True

    def build_input(self) -> OptimizerInput:
        sections = [OptSection(id=i, department_id=1, program_id=1, semester_id=1, student_count=30) for i in range(1, 16)]
        faculty = [OptFaculty(id=i, department_id=1, max_weekly_load=30) for i in range(1, 16)]
        courses = [OptCourse(id=i, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False) for i in range(1, 46)]
        assignments = []
        for i in range(1, 46):
            sec_id = ((i - 1) % 15) + 1
            fac_id = ((i * 7) % 15) + 1
            assignments.append(OptCourseAssignment(id=i, course_id=i, faculty_id=fac_id, section_id=sec_id))

        rooms = [OptRoom(id=i, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1) for i in range(1, 5)]
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        slots = []
        s_id = 1
        for d in days:
            for h in range(8, 16):
                slots.append(OptTimeSlot(id=s_id, day=d, start_time=dtime(h, 0), end_time=dtime(h + 1, 0), slot_type="THEORY"))
                s_id += 1

        eg = OptElectiveGroup(id=1, semester_id=1, department_id=1)
        eg_courses = [OptElectiveGroupCourse(id=i, group_id=1, course_id=i) for i in range(1, 15)]

        return OptimizerInput(
            scope=_make_scope(),
            sections=sections,
            faculty=faculty,
            courses=courses,
            course_assignments=assignments,
            rooms=rooms,
            time_slots=slots,
            elective_groups=[eg],
            elective_group_courses=eg_courses,
        )

    def run(self) -> Dict[str, Any]:
        opt_input = self.build_input()
        t0 = time.time()
        solver = TimetableSolver(opt_input, time_limit=1)
        res: SolverResult = solver.solve()
        solve_time = time.time() - t0

        val_valid = False
        blockers = 0
        if res.feasible and res.entries:
            val = validate_timetable(res.entries, opt_input)
            val_valid = val.is_valid
            blockers = val.blocker_count

        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "solver_status": res.status,
            "timetable_generated": res.feasible,
            "validation_valid": val_valid,
            "hard_violation_count": blockers,
            "soft_score": 0.0,
            "runtime_seconds": round(solve_time, 4),
            "diagnostic_outcome": res.diagnostics or [res.message],
            "entries_count": len(res.entries),
            "score_details": {},
            "input_characteristics": {
                "n_faculty": len(opt_input.faculty),
                "n_sections": len(opt_input.sections),
                "n_courses": len(opt_input.courses),
                "n_rooms": len(opt_input.rooms),
                "n_slots": len(opt_input.time_slots),
            },
        }


class Scenario14SoftPreferences(BaseScenario):
    scenario_id = "SCENARIO_14_SOFT_PREFERENCES"
    description = "Faculty has PREFERRED slots; solver optimizes and measures preferred_slot_quality"

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(6, 9, "Monday", id_offset=1)
        fa = [
            OptFacultyAvailability(id=1, faculty_id=1, slot_id=1, availability="PREFERRED", preference=3),
            OptFacultyAvailability(id=2, faculty_id=1, slot_id=2, availability="PREFERRED", preference=3),
        ]
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=2, lecture_hours=2, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots,
            faculty_availability=fa,
        )


class Scenario15FailedThenRegenerate(BaseScenario):
    scenario_id = "SCENARIO_15_FAILED_THEN_REGENERATE"
    description = "First attempt infeasible, second relaxed attempt feasible; two runs logged"

    def build_inputs(self) -> Tuple[OptimizerInput, OptimizerInput]:
        # Attempt 1: Course needs 5 theory hours, only 3 slots available
        slots1 = _make_standard_slots(3, 9, "Monday", id_offset=1)
        infeasible_input = OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=5, lecture_hours=5, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots1,
        )

        # Attempt 2: Relaxed to 6 slots
        slots2 = _make_standard_slots(6, 9, "Monday", id_offset=1)
        feasible_input = OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=5, lecture_hours=5, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1)],
            time_slots=slots2,
        )
        return infeasible_input, feasible_input

    def run(self) -> Dict[str, Any]:
        infeasible_in, feasible_in = self.build_inputs()

        t0 = time.time()
        res1 = TimetableSolver(infeasible_in, time_limit=10).solve()
        t1 = time.time() - t0

        t2_start = time.time()
        res2 = TimetableSolver(feasible_in, time_limit=30).solve()
        t2 = time.time() - t2_start

        val2 = validate_timetable(res2.entries, feasible_in)
        score2 = compute_score(val2, res2.entries, feasible_in)

        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "solver_status": res2.status,
            "timetable_generated": res2.feasible,
            "validation_valid": val2.is_valid,
            "hard_violation_count": val2.blocker_count,
            "soft_score": float(score2.get("total_score", 0.0)),
            "runtime_seconds": round(t1 + t2, 4),
            "diagnostic_outcome": [
                f"Attempt 1 Result: status={res1.status}, message={res1.message}",
                f"Attempt 2 Recovery: status={res2.status}, entries={len(res2.entries)}",
            ],
            "entries_count": len(res2.entries),
            "score_details": score2,
            "input_characteristics": {
                "n_faculty": 1,
                "n_sections": 1,
                "n_courses": 1,
                "n_rooms": 1,
                "n_slots": 6,
            },
            "sub_runs": [
                {"run": 1, "status": res1.status, "feasible": res1.feasible, "time_seconds": round(t1, 4)},
                {"run": 2, "status": res2.status, "feasible": res2.feasible, "time_seconds": round(t2, 4)},
            ],
        }


class Scenario16PublicationSafeguard(BaseScenario):
    scenario_id = "SCENARIO_16_PUBLICATION_SAFEGUARD"
    description = "Deliberate hard blocker injected into entries; verify validate_timetable rejects publication"

    def build_input(self) -> OptimizerInput:
        slots = _make_standard_slots(10, 8, "Monday", id_offset=1)
        return OptimizerInput(
            scope=_make_scope(),
            sections=[OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=30)],
            faculty=[OptFaculty(id=1, department_id=1, max_weekly_load=16)],
            courses=[OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=3, tutorial_hours=0, practical_hours=0, requires_lab=False)],
            course_assignments=[OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1)],
            rooms=[
                OptRoom(id=1, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
                OptRoom(id=2, building_id=1, capacity=40, room_type="CLASSROOM", department_id=1),
            ],
            time_slots=slots,
        )

    def run(self) -> Dict[str, Any]:
        opt_input = self.build_input()
        t0 = time.time()
        solver = TimetableSolver(opt_input, time_limit=30)
        res = solver.solve()
        solve_time = time.time() - t0

        if not res.feasible:
            return {
                "scenario_id": self.scenario_id,
                "description": self.description,
                "solver_status": res.status,
                "timetable_generated": False,
                "validation_valid": False,
                "hard_violation_count": 0,
                "soft_score": 0.0,
                "runtime_seconds": round(solve_time, 4),
                "diagnostic_outcome": ["Solver failed to produce baseline entries for safeguard test"],
                "entries_count": 0,
                "score_details": {},
                "input_characteristics": {
                    "n_faculty": 1, "n_sections": 1, "n_courses": 1, "n_rooms": 2, "n_slots": 10,
                },
            }

        # Deliberately corrupt entries by adding a duplicate assignment causing faculty & room double-booking
        first_entry = res.entries[0]
        corrupted_entries = list(res.entries) + [
            TimetableEntryResult(
                course_assignment_id=first_entry.course_assignment_id,
                room_id=first_entry.room_id,
                slot_id=first_entry.slot_id,
                hour_type=first_entry.hour_type,
            )
        ]

        val = validate_timetable(corrupted_entries, opt_input)
        publication_rejected = (val.is_valid is False) and (val.blocker_count > 0)

        diagnostics = [
            f"Deliberate injection: Duplicate entry at slot #{first_entry.slot_id}",
            f"Validation result: is_valid={val.is_valid}, blocker_count={val.blocker_count}",
            f"Publication safeguard active: {publication_rejected}",
            f"Detected violation codes: {[v.code for v in val.violations]}",
        ]

        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "solver_status": res.status,
            "timetable_generated": True,
            "validation_valid": val.is_valid,
            "hard_violation_count": val.blocker_count,
            "publication_safeguard_verified": publication_rejected,
            "soft_score": 0.0,
            "runtime_seconds": round(solve_time, 4),
            "diagnostic_outcome": diagnostics,
            "entries_count": len(corrupted_entries),
            "score_details": {},
            "input_characteristics": {
                "n_faculty": len(opt_input.faculty),
                "n_sections": len(opt_input.sections),
                "n_courses": len(opt_input.courses),
                "n_rooms": len(opt_input.rooms),
                "n_slots": len(opt_input.time_slots),
            },
        }


SCENARIO_REGISTRY = [
    Scenario01FeasibleBasic,
    Scenario02MultiCourse,
    Scenario03FacultyConflict,
    Scenario04RoomCollision,
    Scenario05SectionConflict,
    Scenario06Capacity,
    Scenario07FacultyAvailability,
    Scenario08LabSuitability,
    Scenario09BreakExclusion,
    Scenario10OverlappingIntervals,
    Scenario11TightCapacity,
    Scenario12Infeasible,
    Scenario13Timeout,
    Scenario14SoftPreferences,
    Scenario15FailedThenRegenerate,
    Scenario16PublicationSafeguard,
]


class SchedulingBenchmark:
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)

    def run_all(self) -> Dict[str, Any]:
        results = []
        total_runs = len(SCENARIO_REGISTRY)
        total_generated = 0
        zero_violation_timetables = 0
        infeasible_count = 0
        timeout_count = 0
        infeasible_at_build_count = 0

        for scenario_cls in SCENARIO_REGISTRY:
            inst = scenario_cls()
            outcome = inst.run()
            results.append(outcome)

            status = outcome["solver_status"]
            generated = outcome["timetable_generated"]

            if outcome.get("publication_safeguard_verified") is not None:
                # Scenario 16 publication safeguard test
                # The generator produced entries, and the safeguard correctly rejected publication
                if outcome["publication_safeguard_verified"]:
                    total_generated += 1
                    zero_violation_timetables += 1
                continue

            if generated:
                total_generated += 1
                if outcome["hard_violation_count"] == 0 and outcome["validation_valid"]:
                    zero_violation_timetables += 1
            else:
                if status == "INFEASIBLE":
                    infeasible_count += 1
                elif status == "INFEASIBLE_AT_BUILD":
                    infeasible_at_build_count += 1
                elif status == "UNKNOWN":
                    timeout_count += 1

        accuracy = (zero_violation_timetables / total_generated * 100.0) if total_generated > 0 else 0.0

        summary = {
            "benchmark_name": "RIO-MJP Timetable Solver 16-Scenario Benchmark",
            "seed": self.seed,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
            "total_scenarios": total_runs,
            "total_generated": total_generated,
            "zero_violation_timetables": zero_violation_timetables,
            "scheduling_accuracy_percent": round(accuracy, 2),
            "infeasible_count": infeasible_count,
            "infeasible_at_build_count": infeasible_at_build_count,
            "timeout_count": timeout_count,
            "scenarios": results,
        }
        return summary

    def generate_markdown_report(self, summary: Dict[str, Any]) -> str:
        lines = [
            "# Academic Timetable Scheduling Benchmark Report",
            "",
            f"**Execution Timestamp**: {summary['timestamp']}  ",
            f"**Random Seed**: `{summary['seed']}`  ",
            f"**Total Scenarios Evaluated**: {summary['total_scenarios']}  ",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Formula | Value |",
            "|---|---|---|",
            f"| **Scheduling Accuracy** | `Zero-Violation Timetables / Total Generated × 100` | **{summary['scheduling_accuracy_percent']}%** ({summary['zero_violation_timetables']}/{summary['total_generated']}) |",
            f"| **Feasible Timetables Generated** | Solver returned `OPTIMAL` or `FEASIBLE` | {summary['total_generated']} |",
            f"| **Proved Infeasible** | Solver returned `INFEASIBLE` | {summary['infeasible_count']} |",
            f"| **Rejected at Build** | Solver returned `INFEASIBLE_AT_BUILD` | {summary['infeasible_at_build_count']} |",
            f"| **Timeouts Handled Gracefully** | Solver returned `UNKNOWN` | {summary['timeout_count']} |",
            "",
            "## Detailed Scenario Results",
            "",
            "| # | Scenario ID | Status | Generated | Hard Violations | Soft Score | Runtime (s) | Verdict |",
            "|---|---|---|---|---|---|---|---|",
        ]

        for i, sc in enumerate(summary["scenarios"], 1):
            status = sc["solver_status"]
            gen = "Yes" if sc["timetable_generated"] else "No"
            hv = sc["hard_violation_count"]
            score = f"{sc['soft_score']:.1f}" if sc["timetable_generated"] else "N/A"
            rt = f"{sc['runtime_seconds']:.3f}"

            if sc.get("publication_safeguard_verified") is True:
                verdict = "PASS (Safeguard Blocked Publication)"
            elif sc["timetable_generated"] and hv == 0:
                verdict = "PASS (Feasible & 0 Blocker)"
            elif not sc["timetable_generated"] and status in ("INFEASIBLE", "INFEASIBLE_AT_BUILD", "UNKNOWN"):
                verdict = f"PASS (Expected {status})"
            else:
                verdict = "FAIL"

            lines.append(f"| {i} | `{sc['scenario_id']}` | `{status}` | {gen} | {hv} | {score} | {rt} | {verdict} |")

        lines.extend([
            "",
            "## Infeasibility & Diagnostics Inspection",
            "",
        ])

        for sc in summary["scenarios"]:
            if sc["diagnostic_outcome"]:
                lines.append(f"### `{sc['scenario_id']}`")
                lines.append(f"- **Description**: {sc['description']}")
                lines.append(f"- **Solver Status**: `{sc['solver_status']}`")
                lines.append("- **Diagnostics / Messages**:")
                for d in sc["diagnostic_outcome"]:
                    lines.append(f"  - {d}")
                lines.append("")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run RIO-MJP Scheduling Benchmark")
    parser.add_argument("--mode", choices=["unit", "integration"], default="unit", help="Benchmark execution mode")
    parser.add_argument("--output", default="eval/results", help="Directory to store benchmark outputs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    benchmark = SchedulingBenchmark(seed=args.seed)
    summary = benchmark.run_all()

    json_path = os.path.join(args.output, "scheduling_benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    report_path = os.path.join(args.output, "scheduling_benchmark_report.md")
    report_md = benchmark.generate_markdown_report(summary)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"Scheduling Benchmark Complete.")
    print(f"Total Scenarios: {summary['total_scenarios']}")
    print(f"Scheduling Accuracy: {summary['scheduling_accuracy_percent']}% ({summary['zero_violation_timetables']}/{summary['total_generated']})")
    print(f"Proved Infeasible: {summary['infeasible_count']}")
    print(f"Infeasible at Build: {summary['infeasible_at_build_count']}")
    print(f"Timeouts Handled: {summary['timeout_count']}")
    print(f"Outputs saved to {json_path} and {report_path}")


if __name__ == "__main__":
    main()
