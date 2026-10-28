"""
eval/query_benchmark.py
-----------------------
Reproducible benchmark harness for query classification, role-based access control,
and agent routing across the RIO-MJP Multi-Agent System.

Modes:
- `--mode unit`: Pure in-memory intent classification and supervisor routing evaluation.
                 Evaluates all labeled queries from eval/data/query_dataset.json against
                 classify_intent() and supervisor_node() without database dependencies.
- `--mode integration`: End-to-end execution through execute_supervisor() against live test DB.

Outputs:
- JSON summary to eval/results/query_benchmark_results.json
- Markdown summary to eval/results/query_benchmark_report.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.supervisor.agent import classify_intent, supervisor_node


def normalize_intent(intent: str) -> str:
    """Normalizes minor equivalent intent aliases."""
    if intent in ("TIMETABLE_QUERY", "QUERY_AGENT"):
        return "QUERY_AGENT"
    return intent


class QueryBenchmark:
    def __init__(self, dataset_path: str = "eval/data/query_dataset.json"):
        self.dataset_path = dataset_path
        with open(dataset_path, "r", encoding="utf-8") as f:
            self.dataset: List[Dict[str, Any]] = json.load(f)

    def run_unit_benchmark(self) -> Dict[str, Any]:
        results = []
        category_stats = defaultdict(lambda: {"total": 0, "correct_intent": 0, "correct_routing": 0, "passed": 0})
        intent_stats = defaultdict(lambda: {"total": 0, "correct": 0})

        total = len(self.dataset)
        correct_intents = 0
        correct_routings = 0
        total_passed = 0
        abstentions = 0
        failures = []

        for item in self.dataset:
            qid = item["id"]
            query = item["query"]
            role = item.get("user_role", "STUDENT")
            exp_intent = item["expected_intent"]
            exp_agent = item.get("expected_agent", "NONE").upper()
            category = item.get("category", "general")

            t0 = time.time()
            classified_raw = classify_intent(query)
            state = {
                "message": query,
                "user_id": 1,
                "role": role,
            }
            node_out = supervisor_node(state)
            latency = time.time() - t0

            selected_agent_raw = node_out.get("selected_agent")
            pred_agent = (selected_agent_raw or "NONE").upper()

            # Compare intent
            intent_match = (
                classified_raw == exp_intent
                or normalize_intent(classified_raw) == normalize_intent(exp_intent)
                or (exp_intent.startswith("UNSUPPORTED:") and classified_raw == exp_intent)
            )

            # Compare routing
            routing_match = (pred_agent == exp_agent)

            passed = intent_match and routing_match

            category_stats[category]["total"] += 1
            intent_stats[exp_intent]["total"] += 1

            if intent_match:
                correct_intents += 1
                category_stats[category]["correct_intent"] += 1
                intent_stats[exp_intent]["correct"] += 1

            if routing_match:
                correct_routings += 1
                category_stats[category]["correct_routing"] += 1

            if passed:
                total_passed += 1
                category_stats[category]["passed"] += 1
            else:
                failures.append({
                    "id": qid,
                    "query": query,
                    "role": role,
                    "expected_intent": exp_intent,
                    "classified_intent": classified_raw,
                    "expected_agent": exp_agent,
                    "predicted_agent": pred_agent,
                    "category": category,
                })

            if classified_raw == "UNKNOWN":
                abstentions += 1

            results.append({
                "id": qid,
                "query": query,
                "role": role,
                "category": category,
                "expected_intent": exp_intent,
                "classified_intent": classified_raw,
                "expected_agent": exp_agent,
                "predicted_agent": pred_agent,
                "intent_match": intent_match,
                "routing_match": routing_match,
                "passed": passed,
                "latency_seconds": round(latency, 5),
            })

        intent_accuracy = round(correct_intents / total * 100.0, 2) if total > 0 else 0.0
        routing_accuracy = round(correct_routings / total * 100.0, 2) if total > 0 else 0.0
        overall_accuracy = round(total_passed / total * 100.0, 2) if total > 0 else 0.0

        return {
            "benchmark_name": "RIO-MJP Query Intent & Routing Benchmark",
            "mode": "unit",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
            "total_queries": total,
            "correct_intents": correct_intents,
            "intent_accuracy_percent": intent_accuracy,
            "correct_routings": correct_routings,
            "routing_accuracy_percent": routing_accuracy,
            "overall_passed": total_passed,
            "overall_accuracy_percent": overall_accuracy,
            "abstention_count": abstentions,
            "failure_count": len(failures),
            "category_breakdown": dict(category_stats),
            "intent_breakdown": dict(intent_stats),
            "failures": failures,
            "query_results": results,
        }

    def run_integration_benchmark(self) -> Dict[str, Any]:
        """Runs full agent execution with database access."""
        from sqlalchemy.orm import Session
        from backend.config import engine
        from backend.models.identity import User
        from agents.supervisor.agent import execute_supervisor

        unit_summary = self.run_unit_benchmark()
        integration_results = []
        exec_passed = 0
        total = len(self.dataset)

        with Session(engine) as db:
            for item in self.dataset:
                qid = item["id"]
                query = item["query"]
                role = item.get("user_role", "STUDENT")

                user = db.query(User).filter(User.role == role).first()
                if not user:
                    user = User(
                        id=999,
                        username=f"test_{role.lower()}",
                        email=f"{role.lower()}@test.edu",
                        role=role,
                        password_hash="mock",
                    )

                t0 = time.time()
                res = execute_supervisor(message=query, user=user, db=db)
                lat = time.time() - t0

                success = res.get("success", False)
                if success:
                    exec_passed += 1

                integration_results.append({
                    "id": qid,
                    "query": query,
                    "role": role,
                    "reply_preview": (res.get("reply") or "")[:120],
                    "success": success,
                    "sources": res.get("sources", []),
                    "latency_seconds": round(lat, 4),
                })

        unit_summary["mode"] = "integration"
        unit_summary["integration_executed"] = total
        unit_summary["integration_passed"] = exec_passed
        unit_summary["integration_success_rate"] = round(exec_passed / total * 100.0, 2)
        unit_summary["integration_results"] = integration_results
        return unit_summary

    def generate_markdown_report(self, summary: Dict[str, Any]) -> str:
        lines = [
            "# Query Intent Classification & Agent Routing Benchmark Report",
            "",
            f"**Execution Mode**: `{summary['mode']}`  ",
            f"**Execution Timestamp**: {summary['timestamp']}  ",
            f"**Total Evaluated Queries**: {summary['total_queries']}  ",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Formula | Value |",
            "|---|---|---|",
            f"| **Intent Classification Accuracy** | `Correct Intents / Total Queries × 100` | **{summary['intent_accuracy_percent']}%** ({summary['correct_intents']}/{summary['total_queries']}) |",
            f"| **Agent Routing Accuracy** | `Correct Agent Nodes / Total Queries × 100` | **{summary['routing_accuracy_percent']}%** ({summary['correct_routings']}/{summary['total_queries']}) |",
            f"| **Overall Accuracy (Both Match)** | `(Intent & Routing Correct) / Total × 100` | **{summary['overall_accuracy_percent']}%** ({summary['overall_passed']}/{summary['total_queries']}) |",
            f"| **Abstentions / Unmatched** | Classified as `UNKNOWN` | {summary['abstention_count']} |",
            f"| **Failures / Mismatches** | Failed intent or routing check | {summary['failure_count']} |",
        ]

        if summary.get("mode") == "integration":
            lines.extend([
                f"| **Integration Execution Success** | `Successful Agent Invocations / Total × 100` | **{summary.get('integration_success_rate', 0.0)}%** ({summary.get('integration_passed', 0)}/{summary['total_queries']}) |",
            ])

        lines.extend([
            "",
            "## Category Breakdown",
            "",
            "| Category | Total | Intent Accuracy | Routing Accuracy | Overall Passed |",
            "|---|---|---|---|---|",
        ])

        for cat, stats in sorted(summary["category_breakdown"].items()):
            tot = stats["total"]
            int_pct = round(stats["correct_intent"] / tot * 100.0, 1) if tot > 0 else 0.0
            rt_pct = round(stats["correct_routing"] / tot * 100.0, 1) if tot > 0 else 0.0
            pass_pct = round(stats["passed"] / tot * 100.0, 1) if tot > 0 else 0.0
            lines.append(f"| `{cat}` | {tot} | {int_pct}% ({stats['correct_intent']}/{tot}) | {rt_pct}% ({stats['correct_routing']}/{tot}) | **{pass_pct}%** ({stats['passed']}/{tot}) |")

        lines.extend([
            "",
            "## Intent Category Breakdown",
            "",
            "| Intent Type | Count | Correct | Accuracy |",
            "|---|---|---|---|",
        ])

        for intent, stats in sorted(summary["intent_breakdown"].items()):
            tot = stats["total"]
            corr = stats["correct"]
            pct = round(corr / tot * 100.0, 1) if tot > 0 else 0.0
            lines.append(f"| `{intent}` | {tot} | {corr} | {pct}% |")

        if summary["failures"]:
            lines.extend([
                "",
                "## Observed Failures / Discrepancies",
                "",
                "| ID | Query | Role | Expected Intent | Got Intent | Expected Agent | Got Agent |",
                "|---|---|---|---|---|---|---|",
            ])
            for f in summary["failures"]:
                lines.append(f"| `{f['id']}` | \"{f['query']}\" | `{f['role']}` | `{f['expected_intent']}` | `{f['classified_intent']}` | `{f['expected_agent']}` | `{f['predicted_agent']}` |")
        else:
            lines.extend([
                "",
                "## Observed Failures / Discrepancies",
                "",
                "*Zero failures observed across all 55 labeled test queries.*",
            ])

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run RIO-MJP Query Intent Benchmark")
    parser.add_argument("--mode", choices=["unit", "integration"], default="unit", help="Benchmark execution mode")
    parser.add_argument("--dataset", default="eval/data/query_dataset.json", help="Path to labeled query dataset")
    parser.add_argument("--output", default="eval/results", help="Directory to store benchmark outputs")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    benchmark = QueryBenchmark(dataset_path=args.dataset)
    if args.mode == "integration":
        summary = benchmark.run_integration_benchmark()
    else:
        summary = benchmark.run_unit_benchmark()

    json_path = os.path.join(args.output, "query_benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    report_path = os.path.join(args.output, "query_benchmark_report.md")
    report_md = benchmark.generate_markdown_report(summary)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print("Query Benchmark Complete.")
    print(f"Total Queries: {summary['total_queries']}")
    print(f"Intent Classification Accuracy: {summary['intent_accuracy_percent']}% ({summary['correct_intents']}/{summary['total_queries']})")
    print(f"Agent Routing Accuracy: {summary['routing_accuracy_percent']}% ({summary['correct_routings']}/{summary['total_queries']})")
    print(f"Overall Accuracy: {summary['overall_accuracy_percent']}% ({summary['overall_passed']}/{summary['total_queries']})")
    print(f"Failures: {summary['failure_count']}")
    print(f"Outputs saved to {json_path} and {report_path}")


if __name__ == "__main__":
    main()

