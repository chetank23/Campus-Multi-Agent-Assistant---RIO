# Academic Timetable Scheduling Benchmark Report

**Execution Timestamp**: 2026-11-02 11:21:45Z  
**Random Seed**: `42`  
**Total Scenarios Evaluated**: 16  

## Summary Metrics

| Metric | Formula | Value |
|---|---|---|
| **Scheduling Accuracy** | `Zero-Violation Timetables / Total Generated × 100` | **100.0%** (10/10) |
| **Feasible Timetables Generated** | Solver returned `OPTIMAL` or `FEASIBLE` | 10 |
| **Proved Infeasible** | Solver returned `INFEASIBLE` | 2 |
| **Rejected at Build** | Solver returned `INFEASIBLE_AT_BUILD` | 3 |
| **Timeouts Handled Gracefully** | Solver returned `UNKNOWN` | 1 |

## Detailed Scenario Results

| # | Scenario ID | Status | Generated | Hard Violations | Soft Score | Runtime (s) | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | `SCENARIO_01_FEASIBLE_BASIC` | `OPTIMAL` | Yes | 0 | 100.0 | 0.020 | PASS (Feasible & 0 Blocker) |
| 2 | `SCENARIO_02_MULTI_COURSE` | `OPTIMAL` | Yes | 0 | 95.7 | 0.074 | PASS (Feasible & 0 Blocker) |
| 3 | `SCENARIO_03_FACULTY_CONFLICT` | `INFEASIBLE` | No | 0 | N/A | 0.003 | PASS (Expected INFEASIBLE) |
| 4 | `SCENARIO_04_ROOM_COLLISION` | `OPTIMAL` | Yes | 0 | 100.0 | 0.009 | PASS (Feasible & 0 Blocker) |
| 5 | `SCENARIO_05_SECTION_CONFLICT` | `OPTIMAL` | Yes | 0 | 100.0 | 0.015 | PASS (Feasible & 0 Blocker) |
| 6 | `SCENARIO_06_CAPACITY` | `INFEASIBLE_AT_BUILD` | No | 0 | N/A | 0.001 | PASS (Expected INFEASIBLE_AT_BUILD) |
| 7 | `SCENARIO_07_FACULTY_AVAILABILITY` | `INFEASIBLE_AT_BUILD` | No | 0 | N/A | 0.000 | PASS (Expected INFEASIBLE_AT_BUILD) |
| 8 | `SCENARIO_08_LAB_SUITABILITY` | `INFEASIBLE_AT_BUILD` | No | 0 | N/A | 0.000 | PASS (Expected INFEASIBLE_AT_BUILD) |
| 9 | `SCENARIO_09_BREAK_EXCLUSION` | `OPTIMAL` | Yes | 0 | 79.5 | 0.014 | PASS (Feasible & 0 Blocker) |
| 10 | `SCENARIO_10_OVERLAPPING_INTERVALS` | `OPTIMAL` | Yes | 0 | 100.0 | 0.016 | PASS (Feasible & 0 Blocker) |
| 11 | `SCENARIO_11_TIGHT_CAPACITY` | `OPTIMAL` | Yes | 0 | 100.0 | 0.015 | PASS (Feasible & 0 Blocker) |
| 12 | `SCENARIO_12_INFEASIBLE` | `INFEASIBLE` | No | 0 | N/A | 0.003 | PASS (Expected INFEASIBLE) |
| 13 | `SCENARIO_13_TIMEOUT` | `UNKNOWN` | No | 0 | N/A | 1.622 | PASS (Expected UNKNOWN) |
| 14 | `SCENARIO_14_SOFT_PREFERENCES` | `OPTIMAL` | Yes | 0 | 100.0 | 0.007 | PASS (Feasible & 0 Blocker) |
| 15 | `SCENARIO_15_FAILED_THEN_REGENERATE` | `OPTIMAL` | Yes | 0 | 100.0 | 0.019 | PASS (Feasible & 0 Blocker) |
| 16 | `SCENARIO_16_PUBLICATION_SAFEGUARD` | `OPTIMAL` | Yes | 4 | 0.0 | 0.018 | PASS (Safeguard Blocked Publication) |

## Infeasibility & Diagnostics Inspection

### `SCENARIO_03_FACULTY_CONFLICT`
- **Description**: 1 faculty assigned to 2 courses (6 total hours), but only 4 slots exist (solver detects conflict)
- **Solver Status**: `INFEASIBLE`
- **Diagnostics / Messages**:
  - No feasible timetable exists with the current constraints.
  - Faculty availability shortage: Faculty ID 1 needs 6 teaching hours but only provided 0 available slots. Suggest adding 6 more available slots for this faculty.

### `SCENARIO_06_CAPACITY`
- **Description**: Room capacity 30, section has 50 students (expect INFEASIBLE_AT_BUILD)
- **Solver Status**: `INFEASIBLE_AT_BUILD`
- **Diagnostics / Messages**:
  - No eligible rooms for THEORY of course 1
  - Faculty availability shortage: Faculty ID 1 needs 3 teaching hours but only provided 0 available slots. Suggest adding 3 more available slots for this faculty.

### `SCENARIO_07_FACULTY_AVAILABILITY`
- **Description**: Faculty marked UNAVAILABLE for all but 2 slots; course needs 3 theory hours (expect INFEASIBLE_AT_BUILD)
- **Solver Status**: `INFEASIBLE_AT_BUILD`
- **Diagnostics / Messages**:
  - Not enough available slots for faculty 1 teaching 1
  - Faculty availability shortage: Faculty ID 1 needs 3 teaching hours but only provided 2 available slots. Suggest adding 1 more available slots for this faculty.

### `SCENARIO_08_LAB_SUITABILITY`
- **Description**: Practical course, only classrooms available without lab designation (expect INFEASIBLE_AT_BUILD)
- **Solver Status**: `INFEASIBLE_AT_BUILD`
- **Diagnostics / Messages**:
  - No eligible rooms for PRACTICAL of course 1
  - Faculty availability shortage: Faculty ID 1 needs 3 teaching hours but only provided 0 available slots. Suggest adding 3 more available slots for this faculty.
  - Lab capacity shortage: Need 3 lab room-slots but only 0 are available. Suggest adding 3 more slots or lab rooms.

### `SCENARIO_12_INFEASIBLE`
- **Description**: More required hours (6) than available room-slots (4); solver proves INFEASIBLE
- **Solver Status**: `INFEASIBLE`
- **Diagnostics / Messages**:
  - No feasible timetable exists with the current constraints.
  - Room capacity shortage: Need 6 room-slots but only 4 are available. Suggest adding 2 more slots or rooms.
  - Faculty availability shortage: Faculty ID 1 needs 3 teaching hours but only provided 0 available slots. Suggest adding 3 more available slots for this faculty.
  - Faculty availability shortage: Faculty ID 2 needs 3 teaching hours but only provided 0 available slots. Suggest adding 3 more available slots for this faculty.

### `SCENARIO_13_TIMEOUT`
- **Description**: Large combinatorial stress problem with time_limit=1s; expect graceful UNKNOWN status
- **Solver Status**: `UNKNOWN`
- **Diagnostics / Messages**:
  - Solver reached time limit without finding a solution.

### `SCENARIO_15_FAILED_THEN_REGENERATE`
- **Description**: First attempt infeasible, second relaxed attempt feasible; two runs logged
- **Solver Status**: `OPTIMAL`
- **Diagnostics / Messages**:
  - Attempt 1 Result: status=INFEASIBLE_AT_BUILD, message=Not enough available slots for faculty 1 teaching 1
  - Attempt 2 Recovery: status=OPTIMAL, entries=5

### `SCENARIO_16_PUBLICATION_SAFEGUARD`
- **Description**: Deliberate hard blocker injected into entries; verify validate_timetable rejects publication
- **Solver Status**: `OPTIMAL`
- **Diagnostics / Messages**:
  - Deliberate injection: Duplicate entry at slot #6
  - Validation result: is_valid=False, blocker_count=4
  - Publication safeguard active: True
  - Detected violation codes: ['FACULTY_OVERLAP', 'ROOM_OVERLAP', 'SECTION_OVERLAP', 'INSUFFICIENT_HOURS']
