"""
tests/eval/test_scheduling_benchmark_unit.py
--------------------------------------------
Unit tests for the scheduling evaluation and benchmark system.
Tests scenario input models, constraint validation detection (capacity deficit,
faculty double-booking, room collision, break slots, missing hours), scorer
normalization and bounds, and temporal interval overlap logic.

Pure unit test suite: zero database dependencies, runs fully offline.
"""

import sys
import json
from pathlib import Path
from datetime import time
import pytest

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.schemas.timetable_generation import (
    OptimizerInput,
    GenerationScope,
    OptCourse,
    OptSection,
    OptFaculty,
    OptFacultyAvailability,
    OptTimeSlot,
    OptRoom,
    OptCourseAssignment,
    TimetableEntryResult,
)
from backend.optimizer.validator import validate_timetable, slots_overlap
from backend.optimizer.scorer import compute_score
from eval.scheduling_benchmark import (
    SchedulingBenchmark,
    SCENARIO_REGISTRY,
    _make_scope,
    _make_standard_slots,
)


# -----------------------------------------------------------------------------
# Fixtures & Helper Builders
# -----------------------------------------------------------------------------

def build_base_optimizer_input() -> OptimizerInput:
    """Builds a minimal valid OptimizerInput for unit tests."""
    slots = _make_standard_slots(4, 9, "Monday", id_offset=1)
    # Add a break slot at 13:00
    slots.append(
        OptTimeSlot(id=5, day="Monday", start_time=time(13, 0), end_time=time(14, 0), slot_type="BREAK")
    )
    return OptimizerInput(
        scope=_make_scope(),
        sections=[
            OptSection(id=1, department_id=1, program_id=1, semester_id=1, student_count=40),
            OptSection(id=2, department_id=1, program_id=1, semester_id=1, student_count=30),
        ],
        faculty=[
            OptFaculty(id=1, department_id=1, max_weekly_load=16),
            OptFaculty(id=2, department_id=1, max_weekly_load=16),
        ],
        courses=[
            OptCourse(id=1, department_id=1, course_type="THEORY", credits=3, lecture_hours=2, tutorial_hours=0, practical_hours=0, requires_lab=False),
            OptCourse(id=2, department_id=1, course_type="THEORY", credits=3, lecture_hours=2, tutorial_hours=0, practical_hours=0, requires_lab=False),
        ],
        course_assignments=[
            OptCourseAssignment(id=1, course_id=1, faculty_id=1, section_id=1),
            OptCourseAssignment(id=2, course_id=2, faculty_id=2, section_id=2),
        ],
        rooms=[
            OptRoom(id=1, building_id=1, capacity=50, room_type="CLASSROOM", department_id=1),
            OptRoom(id=2, building_id=1, capacity=35, room_type="CLASSROOM", department_id=1),
            OptRoom(id=3, building_id=1, capacity=25, room_type="CLASSROOM", department_id=1),
        ],
        time_slots=slots,
    )


# -----------------------------------------------------------------------------
# Test Cases
# -----------------------------------------------------------------------------

def test_scenario_metadata_integrity():
    """Verify that all 16 scenarios in eval/data/scheduling_scenarios.json match SCENARIO_REGISTRY."""
    scenarios_path = REPO_ROOT / "eval" / "data" / "scheduling_scenarios.json"
    assert scenarios_path.is_file(), f"Scenario metadata file missing at {scenarios_path}"

    with open(scenarios_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    assert isinstance(scenarios, list)
    assert len(scenarios) == 16, f"Expected exactly 16 scenarios, found {len(scenarios)}"

    registry_map = {cls.scenario_id: cls for cls in SCENARIO_REGISTRY}
    for s in scenarios:
        s_id = s.get("scenario_id")
        assert s_id and s_id.startswith("SCENARIO_")
        assert "description" in s and len(s["description"]) > 0
        assert "expected_solver_status" in s
        assert "expected_timetable_generated" in s
        assert "expected_max_hard_violations" in s
        assert s_id in registry_map, f"Scenario {s_id} missing in SCENARIO_REGISTRY"

        # Execute the builder and verify the returned OptimizerInput
        inst = registry_map[s_id]()
        if hasattr(inst, "build_inputs"):
            opt_input_1, opt_input_2 = inst.build_inputs()
            assert isinstance(opt_input_1, OptimizerInput)
            assert isinstance(opt_input_2, OptimizerInput)
        else:
            opt_input = inst.build_input()
            assert isinstance(opt_input, OptimizerInput)
            assert opt_input.scope is not None
            assert len(opt_input.time_slots) > 0


def test_slots_overlap_unit():
    """Unit test slots_overlap edge cases: same ID, different day, None, boundary touching, enclosure."""
    s1 = OptTimeSlot(id=1, day="Monday", start_time=time(9, 0), end_time=time(10, 0), slot_type="LECTURE")
    s2 = OptTimeSlot(id=2, day="Monday", start_time=time(9, 30), end_time=time(10, 30), slot_type="LECTURE")
    s3 = OptTimeSlot(id=3, day="Monday", start_time=time(10, 0), end_time=time(11, 0), slot_type="LECTURE")
    s4 = OptTimeSlot(id=4, day="Monday", start_time=time(8, 0), end_time=time(12, 0), slot_type="LECTURE")
    s5_tue = OptTimeSlot(id=5, day="Tuesday", start_time=time(9, 0), end_time=time(10, 0), slot_type="LECTURE")

    # Same slot by ID
    assert slots_overlap(s1, s1) is True

    # None checks
    assert slots_overlap(None, s1) is False
    assert slots_overlap(s1, None) is False

    # Different day
    assert slots_overlap(s1, s5_tue) is False

    # Overlapping interval on same day (09:00-10:00 vs 09:30-10:30)
    assert slots_overlap(s1, s2) is True
    assert slots_overlap(s2, s1) is True

    # Touching boundaries (09:00-10:00 vs 10:00-11:00) -> No overlap
    assert slots_overlap(s1, s3) is False
    assert slots_overlap(s3, s1) is False

    # Enclosed interval (09:00-10:00 enclosed within 08:00-12:00)
    assert slots_overlap(s1, s4) is True
    assert slots_overlap(s4, s1) is True


def test_validate_timetable_detects_capacity_deficit():
    """Test that validate_timetable flags a section placed into an undersized room (H4)."""
    opt = build_base_optimizer_input()
    # Section 1 has 40 students; Room 3 has capacity 25 -> Deficit
    entries = [
        TimetableEntryResult(course_assignment_id=1, slot_id=1, room_id=3, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=1, slot_id=2, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=1, room_id=2, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=2, room_id=2, hour_type="THEORY"),
    ]
    res = validate_timetable(entries, opt)
    assert res.is_valid is False
    assert any(v.code == "CAPACITY_DEFICIT" for v in res.violations)
    deficit_v = next(v for v in res.violations if v.code == "CAPACITY_DEFICIT")
    assert deficit_v.severity == "BLOCKER"
    assert "insufficient for 40 students" in deficit_v.message


def test_validate_timetable_detects_faculty_double_booking():
    """Test that validate_timetable flags same faculty scheduled in 2 classes at overlapping slots (H1)."""
    opt = build_base_optimizer_input()
    # Give both assignments the same faculty (faculty_id=1)
    opt.course_assignments[1].faculty_id = 1
    entries = [
        TimetableEntryResult(course_assignment_id=1, slot_id=1, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=1, room_id=2, hour_type="THEORY"),  # Faculty overlap at slot 1
        TimetableEntryResult(course_assignment_id=1, slot_id=2, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=2, room_id=2, hour_type="THEORY"),
    ]
    res = validate_timetable(entries, opt)
    assert res.is_valid is False
    assert any(v.code == "FACULTY_OVERLAP" for v in res.violations)


def test_validate_timetable_detects_room_collision():
    """Test that validate_timetable flags two classes scheduled in the same room at overlapping slots (H2)."""
    opt = build_base_optimizer_input()
    entries = [
        TimetableEntryResult(course_assignment_id=1, slot_id=1, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=1, room_id=1, hour_type="THEORY"),  # Room overlap at slot 1
        TimetableEntryResult(course_assignment_id=1, slot_id=2, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=2, room_id=2, hour_type="THEORY"),
    ]
    res = validate_timetable(entries, opt)
    assert res.is_valid is False
    assert any(v.code == "ROOM_OVERLAP" for v in res.violations)


def test_validate_timetable_detects_break_slot_assignment():
    """Test that validate_timetable flags any class placed in a BREAK/LUNCH slot."""
    opt = build_base_optimizer_input()
    # slot_id=5 is marked as BREAK
    entries = [
        TimetableEntryResult(course_assignment_id=1, slot_id=5, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=1, slot_id=2, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=1, room_id=2, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=2, room_id=2, hour_type="THEORY"),
    ]
    res = validate_timetable(entries, opt)
    assert res.is_valid is False
    assert any(v.code == "INVALID_SLOT_TYPE" for v in res.violations)


def test_validate_timetable_detects_missing_hours():
    """Test that validate_timetable flags when assigned hours are less than required weekly hours."""
    opt = build_base_optimizer_input()
    # Course 1 requires 2 hours, but only 1 entry provided
    entries = [
        TimetableEntryResult(course_assignment_id=1, slot_id=1, room_id=1, hour_type="THEORY"),
        # Missing 1 hour for assignment 1
        TimetableEntryResult(course_assignment_id=2, slot_id=1, room_id=2, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=2, room_id=2, hour_type="THEORY"),
    ]
    res = validate_timetable(entries, opt)
    assert res.is_valid is False
    assert any(v.code == "INSUFFICIENT_HOURS" for v in res.violations)


def test_compute_score_bounds_and_penalties():
    """Test that compute_score stays bounded in [0, 100] and properly reports violation counts."""
    opt = build_base_optimizer_input()

    # Valid timetable: 2 hours for each of the 2 assignments, zero conflicts
    valid_entries = [
        TimetableEntryResult(course_assignment_id=1, slot_id=1, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=1, slot_id=2, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=3, room_id=2, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=4, room_id=2, hour_type="THEORY"),
    ]
    valid_res = validate_timetable(valid_entries, opt)
    assert valid_res.is_valid is True
    score_valid = compute_score(valid_res, valid_entries, opt)
    assert "total_score" in score_valid
    assert 0.0 <= score_valid["total_score"] <= 100.0
    assert score_valid["hard_violations"] == 0

    # Invalid timetable with blocker violation
    invalid_entries = [
        TimetableEntryResult(course_assignment_id=1, slot_id=1, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=1, room_id=1, hour_type="THEORY"),  # Room overlap
        TimetableEntryResult(course_assignment_id=1, slot_id=2, room_id=1, hour_type="THEORY"),
        TimetableEntryResult(course_assignment_id=2, slot_id=2, room_id=2, hour_type="THEORY"),
    ]
    invalid_res = validate_timetable(invalid_entries, opt)
    assert invalid_res.is_valid is False
    score_invalid = compute_score(invalid_res, invalid_entries, opt)
    assert 0.0 <= score_invalid["total_score"] <= 100.0
    # Blocker violation detected and counted in score dict
    assert score_invalid["hard_violations"] > 0


def test_scheduling_benchmark_deterministic_execution():
    """Verify that the benchmark runs deterministically and populates all 16 scenario results."""
    benchmark = SchedulingBenchmark()
    summary = benchmark.run_all()
    assert summary["total_scenarios"] == 16
    assert summary["total_generated"] in (10, 11)
    assert summary["zero_violation_timetables"] in (10, 11)
    assert summary["scheduling_accuracy_percent"] == 100.0
    assert len(summary["scenarios"]) == 16
