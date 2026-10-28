"""
eval/resource_agent_benchmark.py
--------------------------------
Evaluation harness and benchmark for Resource Agent operations in RIO-MJP:
- Proposal state lifecycle, expiration TTL, and single-use idempotency
- Proposal user isolation and superseded state invalidation
- Natural language datetime and parameter extraction
- Interval conflict detection and boundary conditions
- Role-based authorization guards (approval/rejection/cancellation permissions)
- Integration-level database verification (when run with --mode integration)

Outputs:
- JSON results to eval/results/resource_agent_benchmark_results.json
- Markdown summary to eval/results/resource_agent_benchmark_report.md
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.resource_agent.proposal_store import ResourceProposalStore, ResourceProposal
from agents.resource_agent.parser import (
    parse_date,
    parse_time_interval,
    extract_resource_details,
)
from backend.models.identity import User
from agents.tools.resource_tools import (
    execute_approve_booking_data,
    execute_reject_booking_data,
)


def _check_intervals_overlap(s1: datetime.time, e1: datetime.time, s2: datetime.time, e2: datetime.time) -> bool:
    """Interval overlap rule: max(start1, start2) < min(end1, end2)."""
    return max(s1, s2) < min(e1, e2)


class ResourceAgentBenchmark:
    def __init__(self, mode: str = "unit"):
        self.mode = mode

    def run_unit_tests(self) -> List[Dict[str, Any]]:
        tests = []

        # 1. Proposal creation & single-use idempotency
        t0 = time.time()
        store = ResourceProposalStore(ttl_seconds=300)
        p1 = store.create_proposal(
            user_id=101,
            role="FACULTY",
            resource_id=1,
            resource_name="Seminar Hall A",
            resource_type="FACILITY",
            date="2026-11-05",
            start_time="14:00:00",
            end_time="16:00:00",
            purpose="Guest Lecture on AI",
        )
        prop_id = p1.proposal_id

        # First consumption
        ok1, prop1, err1 = store.consume_proposal(prop_id, user_id=101)
        # Second consumption (must fail)
        ok2, prop2, err2 = store.consume_proposal(prop_id, user_id=101)

        pass_idempotency = ok1 and (not ok2) and ("already been confirmed" in err2 or "duplicate submission" in err2)
        tests.append({
            "test_name": "test_proposal_lifecycle_and_single_use_idempotency",
            "category": "proposal_lifecycle",
            "passed": pass_idempotency,
            "latency_seconds": round(time.time() - t0, 5),
            "details": f"First consume: ok={ok1}; Second consume: ok={ok2}, msg='{err2}'",
        })

        # 2. Proposal user isolation
        t0 = time.time()
        store2 = ResourceProposalStore(ttl_seconds=300)
        p2 = store2.create_proposal(
            user_id=102,
            role="FACULTY",
            resource_id=2,
            resource_name="Lab 101",
            resource_type="LAB",
            date="2026-11-06",
            start_time="10:00:00",
            end_time="12:00:00",
            purpose="Lab exam",
        )
        ok_wrong_user, _, err_user = store2.consume_proposal(p2.proposal_id, user_id=999)
        pass_isolation = (not ok_wrong_user) and ("another user" in err_user.lower() or "access denied" in err_user.lower())
        tests.append({
            "test_name": "test_proposal_user_session_isolation",
            "category": "proposal_lifecycle",
            "passed": pass_isolation,
            "latency_seconds": round(time.time() - t0, 5),
            "details": f"Attempt by wrong user: ok={ok_wrong_user}, error='{err_user}'",
        })

        # 3. Proposal TTL expiry
        t0 = time.time()
        expired_store = ResourceProposalStore(ttl_seconds=-10)  # already expired
        p3 = expired_store.create_proposal(
            user_id=103,
            role="FACULTY",
            resource_id=3,
            resource_name="Room B201",
            resource_type="CLASSROOM",
            date="2026-11-07",
            start_time="09:00:00",
            end_time="10:00:00",
            purpose="Tutorial",
        )
        ok_expired, _, err_exp = expired_store.consume_proposal(p3.proposal_id, user_id=103)
        pass_expiry = (not ok_expired) and ("expired" in err_exp.lower() or "not found" in err_exp.lower())
        tests.append({
            "test_name": "test_proposal_ttl_expiry_enforcement",
            "category": "proposal_lifecycle",
            "passed": pass_expiry,
            "latency_seconds": round(time.time() - t0, 5),
            "details": f"Attempt to consume expired proposal: ok={ok_expired}, error='{err_exp}'",
        })

        # 4. Superseded proposal invalidation
        t0 = time.time()
        sup_store = ResourceProposalStore(ttl_seconds=300)
        p4a = sup_store.create_proposal(
            user_id=104, role="FACULTY", resource_id=1, resource_name="Hall A",
            resource_type="FACILITY", date="2026-11-08", start_time="10:00:00", end_time="11:00:00",
            purpose="Option 1",
        )
        # Creating a new proposal for the same user supersedes p4a
        p4b = sup_store.create_proposal(
            user_id=104, role="FACULTY", resource_id=2, resource_name="Hall B",
            resource_type="FACILITY", date="2026-11-08", start_time="10:00:00", end_time="11:00:00",
            purpose="Option 2",
        )
        ok_sup, _, err_sup = sup_store.consume_proposal(p4a.proposal_id, user_id=104)
        ok_active, _, _ = sup_store.consume_proposal(p4b.proposal_id, user_id=104)
        pass_superseded = (not ok_sup) and ok_active and ("superseded" in err_sup.lower() or "discarded" in err_sup.lower())
        tests.append({
            "test_name": "test_superseded_proposal_invalidation",
            "category": "proposal_lifecycle",
            "passed": pass_superseded,
            "latency_seconds": round(time.time() - t0, 5),
            "details": f"p4a superseded: ok={ok_sup}, err='{err_sup}'; p4b active: ok={ok_active}",
        })

        # 5. Natural Language Parameter Extraction
        t0 = time.time()
        d_parsed = parse_date("Book Seminar Hall A on 2026-11-15 from 2pm to 4pm")
        t_start, t_end = parse_time_interval("Book Seminar Hall A on 2026-11-15 from 2pm to 4pm")
        res_info = extract_resource_details("Book Seminar Hall A on 2026-11-15 from 2pm to 4pm for 60 students")

        pass_parsing = (
            d_parsed == datetime.date(2026, 11, 15)
            and t_start == datetime.time(14, 0)
            and t_end == datetime.time(16, 0)
            and res_info.get("resource_name") == "Seminar Hall A"
            and (res_info.get("min_capacity") == 60 or res_info.get("capacity") == 60)
        )
        tests.append({
            "test_name": "test_natural_language_parameter_extraction",
            "category": "nlp_parsing",
            "passed": pass_parsing,
            "latency_seconds": round(time.time() - t0, 5),
            "details": f"Parsed: date={d_parsed}, start={t_start}, end={t_end}, details={res_info}",
        })

        # 6. Temporal Interval Overlap Detection (Pure logic)
        t0 = time.time()
        # Case A: Strict overlap: 10:00-12:00 vs 11:00-13:00 -> True
        c1 = _check_intervals_overlap(datetime.time(10, 0), datetime.time(12, 0), datetime.time(11, 0), datetime.time(13, 0))
        # Case B: Disjoint intervals: 09:00-10:00 vs 11:00-12:00 -> False
        c2 = _check_intervals_overlap(datetime.time(9, 0), datetime.time(10, 0), datetime.time(11, 0), datetime.time(12, 0))
        # Case C: Boundary touching: 10:00-11:00 vs 11:00-12:00 -> False (touching boundary is allowed)
        c3 = _check_intervals_overlap(datetime.time(10, 0), datetime.time(11, 0), datetime.time(11, 0), datetime.time(12, 0))
        # Case D: Enclosure: 09:00-14:00 vs 10:00-12:00 -> True
        c4 = _check_intervals_overlap(datetime.time(9, 0), datetime.time(14, 0), datetime.time(10, 0), datetime.time(12, 0))

        pass_overlap = (c1 is True) and (c2 is False) and (c3 is False) and (c4 is True)
        tests.append({
            "test_name": "test_temporal_interval_overlap_logic",
            "category": "conflict_detection",
            "passed": pass_overlap,
            "latency_seconds": round(time.time() - t0, 5),
            "details": f"c1_overlap={c1}, c2_disjoint={c2}, c3_touching={c3}, c4_enclosed={c4}",
        })

        # 7. Role Authorization: Non-Admin Cannot Approve Booking
        t0 = time.time()
        mock_student = User(
            id=201,
            name="student_tester",
            email="student@campus.edu",
            role="STUDENT",
            password_hash="mock",
        )
        mock_faculty = User(
            id=202,
            name="faculty_tester",
            email="faculty@campus.edu",
            role="FACULTY",
            password_hash="mock",
        )

        app_res_student = execute_approve_booking_data(db=None, booking_id=1, user=mock_student)
        rej_res_faculty = execute_reject_booking_data(db=None, booking_id=1, user=mock_faculty, reason="Not admin")

        pass_role_guard = (
            app_res_student.get("success") is False
            and "access denied" in app_res_student.get("error", "").lower()
            and rej_res_faculty.get("success") is False
            and "access denied" in rej_res_faculty.get("error", "").lower()
        )
        tests.append({
            "test_name": "test_non_admin_approval_rejection_blocked",
            "category": "authorization_guards",
            "passed": pass_role_guard,
            "latency_seconds": round(time.time() - t0, 5),
            "details": f"Student approve: error='{app_res_student.get('error')}'; Faculty reject: error='{rej_res_faculty.get('error')}'",
        })

        return tests

    def run_integration_tests(self) -> List[Dict[str, Any]]:
        """Integration tests requiring database access."""
        from sqlalchemy.orm import Session
        from backend.config import engine
        from backend.models.resources import Resource, ResourceBooking
        from backend.services.resource_booking_service import check_resource_conflicts, find_alternative_resources

        tests = self.run_unit_tests()

        try:
            with Session(engine) as db:
                t0 = time.time()
                # Query an existing resource
                res = db.query(Resource).filter(Resource.status == "ACTIVE").first()
                if res:
                    has_conflict, conflicts = check_resource_conflicts(
                        db=db,
                        resource_id=res.id,
                        date=datetime.date(2026, 11, 10),
                        start_time=datetime.time(10, 0),
                        end_time=datetime.time(11, 0),
                    )
                    tests.append({
                        "test_name": "test_db_backed_resource_conflict_check",
                        "category": "integration",
                        "passed": isinstance(conflicts, list),
                        "latency_seconds": round(time.time() - t0, 5),
                        "details": f"Resource #{res.id} ({res.name}) checked; conflict={has_conflict}, list_len={len(conflicts)}",
                    })

                    t0 = time.time()
                    alts = find_alternative_resources(
                        db=db,
                        resource_id=res.id,
                        date=datetime.date(2026, 11, 10),
                        start_time=datetime.time(10, 0),
                        end_time=datetime.time(11, 0),
                        limit=5,
                    )
                    tests.append({
                        "test_name": "test_db_backed_alternative_resource_discovery",
                        "category": "integration",
                        "passed": isinstance(alts, list),
                        "latency_seconds": round(time.time() - t0, 5),
                        "details": f"Alternatives discovered: {len(alts)} for resource #{res.id}",
                    })
        except Exception as exc:
            tests.append({
                "test_name": "test_db_integration_fallback",
                "category": "integration",
                "passed": False,
                "latency_seconds": 0.0,
                "details": f"DB integration check skipped/failed: {exc}",
            })

        return tests

    def run(self) -> Dict[str, Any]:
        if self.mode == "integration":
            test_results = self.run_integration_tests()
        else:
            test_results = self.run_unit_tests()

        total = len(test_results)
        passed = sum(1 for t in test_results if t["passed"])
        pass_rate = round(passed / total * 100.0, 2) if total > 0 else 0.0

        return {
            "benchmark_name": "RIO-MJP Resource Agent Logic & Boundary Benchmark",
            "mode": self.mode,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
            "total_tests": total,
            "passed_tests": passed,
            "failed_tests": total - passed,
            "pass_rate_percent": pass_rate,
            "tests": test_results,
        }

    def generate_markdown_report(self, summary: Dict[str, Any]) -> str:
        lines = [
            "# Resource Agent Logic & Boundary Benchmark Report",
            "",
            f"**Execution Mode**: `{summary['mode']}`  ",
            f"**Execution Timestamp**: {summary['timestamp']}  ",
            f"**Total Invariant Tests**: {summary['total_tests']}  ",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Formula | Value |",
            "|---|---|---|",
            f"| **Test Pass Rate** | `Passed Tests / Total Tests × 100` | **{summary['pass_rate_percent']}%** ({summary['passed_tests']}/{summary['total_tests']}) |",
            f"| **Tests Passed** | Verified invariant checks | {summary['passed_tests']} |",
            f"| **Tests Failed** | Violated invariants | {summary['failed_tests']} |",
            "",
            "## Invariant Verification Results",
            "",
            "| # | Test Name | Category | Status | Runtime (s) | Details |",
            "|---|---|---|---|---|---|",
        ]

        for i, t in enumerate(summary["tests"], 1):
            st = "**PASS**" if t["passed"] else "**FAIL**"
            rt = f"{t['latency_seconds']:.4f}"
            lines.append(f"| {i} | `{t['test_name']}` | `{t['category']}` | {st} | {rt} | {t['details']} |")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run RIO-MJP Resource Agent Benchmark")
    parser.add_argument("--mode", choices=["unit", "integration"], default="unit", help="Benchmark execution mode")
    parser.add_argument("--output", default="eval/results", help="Directory to store benchmark outputs")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    benchmark = ResourceAgentBenchmark(mode=args.mode)
    summary = benchmark.run()

    json_path = os.path.join(args.output, "resource_agent_benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    report_path = os.path.join(args.output, "resource_agent_benchmark_report.md")
    report_md = benchmark.generate_markdown_report(summary)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print("Resource Agent Benchmark Complete.")
    print(f"Total Tests: {summary['total_tests']}")
    print(f"Pass Rate: {summary['pass_rate_percent']}% ({summary['passed_tests']}/{summary['total_tests']})")
    print(f"Failed: {summary['failed_tests']}")
    print(f"Outputs saved to {json_path} and {report_path}")


if __name__ == "__main__":
    main()
