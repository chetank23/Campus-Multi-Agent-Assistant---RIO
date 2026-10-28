# Query Intent Classification & Agent Routing Benchmark Report

**Execution Mode**: `unit`  
**Execution Timestamp**: 2026-10-28 15:52:49Z  
**Total Evaluated Queries**: 55  

## Summary Metrics

| Metric | Formula | Value |
|---|---|---|
| **Intent Classification Accuracy** | `Correct Intents / Total Queries × 100` | **100.0%** (55/55) |
| **Agent Routing Accuracy** | `Correct Agent Nodes / Total Queries × 100` | **100.0%** (55/55) |
| **Overall Accuracy (Both Match)** | `(Intent & Routing Correct) / Total × 100` | **100.0%** (55/55) |
| **Abstentions / Unmatched** | Classified as `UNKNOWN` | 0 |
| **Failures / Mismatches** | Failed intent or routing check | 0 |

## Category Breakdown

| Category | Total | Intent Accuracy | Routing Accuracy | Overall Passed |
|---|---|---|---|---|
| `ambiguous_incomplete` | 5 | 100.0% (5/5) | 100.0% (5/5) | **100.0%** (5/5) |
| `composite_multi_agent` | 4 | 100.0% (4/4) | 100.0% (4/4) | **100.0%** (4/4) |
| `conflict_inspection` | 4 | 100.0% (4/4) | 100.0% (4/4) | **100.0%** (4/4) |
| `course_info` | 6 | 100.0% (6/6) | 100.0% (6/6) | **100.0%** (6/6) |
| `faculty_timetable` | 6 | 100.0% (6/6) | 100.0% (6/6) | **100.0%** (6/6) |
| `resource_booking` | 6 | 100.0% (6/6) | 100.0% (6/6) | **100.0%** (6/6) |
| `scheduling_generation` | 6 | 100.0% (6/6) | 100.0% (6/6) | **100.0%** (6/6) |
| `student_timetable` | 6 | 100.0% (6/6) | 100.0% (6/6) | **100.0%** (6/6) |
| `unauthorized_action` | 6 | 100.0% (6/6) | 100.0% (6/6) | **100.0%** (6/6) |
| `unsupported_request` | 6 | 100.0% (6/6) | 100.0% (6/6) | **100.0%** (6/6) |

## Intent Category Breakdown

| Intent Type | Count | Correct | Accuracy |
|---|---|---|---|
| `ACTION_REGISTRY_HELP` | 1 | 1 | 100.0% |
| `CAMPUS_GREETING` | 3 | 3 | 100.0% |
| `COMPOSITE_BOOKING_SUPERVISION` | 4 | 4 | 100.0% |
| `QUERY_AGENT` | 18 | 18 | 100.0% |
| `RESOURCE_BOOKING` | 9 | 9 | 100.0% |
| `TIMETABLE_GENERATION` | 13 | 13 | 100.0% |
| `TIMETABLE_READINESS` | 1 | 1 | 100.0% |
| `UNSUPPORTED:course deletion` | 1 | 1 | 100.0% |
| `UNSUPPORTED:department deletion` | 1 | 1 | 100.0% |
| `UNSUPPORTED:fee payment and refund processing` | 1 | 1 | 100.0% |
| `UNSUPPORTED:grade management` | 1 | 1 | 100.0% |
| `UNSUPPORTED:password management` | 1 | 1 | 100.0% |
| `UNSUPPORTED:user account creation or deletion` | 1 | 1 | 100.0% |

## Observed Failures / Discrepancies

*Zero failures observed across all 55 labeled test queries.*