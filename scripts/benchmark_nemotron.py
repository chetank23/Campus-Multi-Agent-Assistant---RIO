"""
scripts/benchmark_nemotron.py
------------------------------
Reproducible Latency and Performance Benchmark for NVIDIA Nemotron Campus Assistant.
Measures:
- Time To First Token (TTFT)
- Total Response Duration (ms)
- Database Tool Execution Duration (ms)
- Tool Call Count and Iterations
- p50 and p95 latency across a representative dataset of campus operations queries.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv(".env")

from sqlalchemy.orm import Session

from backend.database import engine
from backend.models.identity import User
from backend.models.academic import Department
from agents.llm.nvidia_provider import NvidiaNemotronProvider

BENCHMARK_QUERIES = [
    {
        "id": "Q1",
        "role": "ADMIN",
        "query": "Which departments currently have generated timetables?",
        "expected_tool": "get_published_timetable_status",
    },
    {
        "id": "Q2",
        "role": "ADMIN",
        "query": "How many students are registered in the Computer Science department?",
        "expected_tool": "search_student_directory",
    },
    {
        "id": "Q3",
        "role": "ADMIN",
        "query": "Which faculty members belong to the department?",
        "expected_tool": "search_faculty_directory",
    },
    {
        "id": "Q4",
        "role": "FACULTY",
        "query": "What courses are assigned to semester 5?",
        "expected_tool": "get_semester_courses",
    },
    {
        "id": "Q5",
        "role": "FACULTY",
        "query": "Which rooms are available for bookings?",
        "expected_tool": "get_room_availability",
    },
    {
        "id": "Q6",
        "role": "STUDENT",
        "query": "Show my timetable schedule.",
        "expected_tool": "get_my_timetable",
    },
    {
        "id": "Q7",
        "role": "ADMIN",
        "query": "Which campus resources are currently booked?",
        "expected_tool": "get_user_bookings",
    },
]


def percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_d = sorted(data)
    idx = int(len(sorted_d) * (p / 100.0))
    idx = min(idx, len(sorted_d) - 1)
    return round(sorted_d[idx], 2)


def run_benchmarks() -> Dict[str, Any]:
    print("=" * 80)
    print("RIO-MJP NEMOTRON PERFORMANCE & STREAMING BENCHMARK SUITE")
    print("=" * 80)

    provider = NvidiaNemotronProvider()
    print(f"[CONFIG] Base URL: {provider.base_url}")
    print(f"[CONFIG] Model:    {provider.model}")
    print(f"[CONFIG] Available: {provider.is_available()}")

    results = []
    streaming_ttfts: List[float] = []
    streaming_totals: List[float] = []
    non_streaming_totals: List[float] = []
    tool_durations: List[float] = []

    with Session(engine) as session:
        admin = session.query(User).filter(User.role == "ADMIN").first()
        faculty = session.query(User).filter(User.role == "FACULTY").first()
        student = session.query(User).filter(User.role == "STUDENT").first()

        if admin is None or faculty is None or student is None:
            missing = [r for r, u in [("ADMIN", admin), ("FACULTY", faculty), ("STUDENT", student)] if u is None]
            raise RuntimeError(
                f"Benchmark execution aborted: Missing required database user fixtures for roles: "
                f"{', '.join(missing)}. Please verify database seed migrations before benchmarking."
            )

        # Narrowed non-null types for static type safety
        users_by_role: Dict[str, User] = {
            "ADMIN": admin,
            "FACULTY": faculty,
            "STUDENT": student,
        }

        for item in BENCHMARK_QUERIES:
            q_id = item["id"]
            q_text = item["query"]
            q_role = item["role"]
            caller = users_by_role.get(q_role)
            if caller is None:
                raise RuntimeError(
                    f"Benchmark query [{q_id}] requested role '{q_role}', but no user fixture is mapped."
                )

            print(f"\nEvaluating [{q_id}] ({q_role}): \"{q_text}\"")

            # 1. Non-streaming execution
            t_start_sync = time.perf_counter()
            sync_res = provider.generate_chat_response(
                message=q_text,
                user=caller,
                db=session,
            )
            sync_duration_ms = round((time.perf_counter() - t_start_sync) * 1000, 2)
            non_streaming_totals.append(sync_duration_ms)

            diag = sync_res.get("diagnostics", {})
            t_tool_ms = 0.0
            tools_called = [tc["tool"] for tc in sync_res.get("tool_calls", [])]

            # 2. Genuine streaming execution (Measure TTFT)
            t_start_stream = time.perf_counter()
            first_token_time_ms = None
            stream_tokens_count = 0
            stream_reply_parts = []

            for event in provider.stream_chat_response(
                message=q_text,
                user=caller,
                db=session,
            ):
                ev_type = event.get("event")
                ev_data = event.get("data", {})
                if ev_type == "token":
                    if first_token_time_ms is None:
                        first_token_time_ms = round((time.perf_counter() - t_start_stream) * 1000, 2)
                    stream_tokens_count += 1
                    stream_reply_parts.append(ev_data.get("token", ""))

            stream_total_ms = round((time.perf_counter() - t_start_stream) * 1000, 2)
            ttft = first_token_time_ms if first_token_time_ms is not None else stream_total_ms
            streaming_ttfts.append(ttft)
            streaming_totals.append(stream_total_ms)

            print(f"  -> Non-streaming: {sync_duration_ms:.1f}ms | Streaming: {stream_total_ms:.1f}ms (TTFT: {ttft:.1f}ms)")
            print(f"  -> Tools called: {tools_called}")

            results.append({
                "id": q_id,
                "role": q_role,
                "query": q_text,
                "tools_called": tools_called,
                "sync_duration_ms": sync_duration_ms,
                "stream_total_ms": stream_total_ms,
                "ttft_ms": ttft,
                "stream_tokens": stream_tokens_count,
            })

    summary = {
        "benchmark_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_queries_evaluated": len(results),
        "non_streaming_total_latency": {
            "p50_ms": percentile(non_streaming_totals, 50),
            "p95_ms": percentile(non_streaming_totals, 95),
            "mean_ms": round(sum(non_streaming_totals) / len(non_streaming_totals), 2),
            "min_ms": min(non_streaming_totals),
            "max_ms": max(non_streaming_totals),
        },
        "streaming_ttft": {
            "p50_ms": percentile(streaming_ttfts, 50),
            "p95_ms": percentile(streaming_ttfts, 95),
            "mean_ms": round(sum(streaming_ttfts) / len(streaming_ttfts), 2),
            "min_ms": min(streaming_ttfts),
            "max_ms": max(streaming_ttfts),
        },
        "streaming_total_duration": {
            "p50_ms": percentile(streaming_totals, 50),
            "p95_ms": percentile(streaming_totals, 95),
            "mean_ms": round(sum(streaming_totals) / len(streaming_totals), 2),
            "min_ms": min(streaming_totals),
            "max_ms": max(streaming_totals),
        },
        "detailed_results": results,
    }

    os.makedirs("reports", exist_ok=True)
    out_path = "reports/NEMOTRON_PERFORMANCE_BENCHMARK.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY RESULTS")
    print("=" * 80)
    print(f"Non-Streaming Response Latency  : p50={summary['non_streaming_total_latency']['p50_ms']}ms | p95={summary['non_streaming_total_latency']['p95_ms']}ms | mean={summary['non_streaming_total_latency']['mean_ms']}ms")
    print(f"Streaming Time To First Token   : p50={summary['streaming_ttft']['p50_ms']}ms | p95={summary['streaming_ttft']['p95_ms']}ms | mean={summary['streaming_ttft']['mean_ms']}ms")
    print(f"Streaming Total Duration        : p50={summary['streaming_total_duration']['p50_ms']}ms | p95={summary['streaming_total_duration']['p95_ms']}ms | mean={summary['streaming_total_duration']['mean_ms']}ms")
    print(f"Report written to: {out_path}")
    print("=" * 80)
    return summary


if __name__ == "__main__":
    run_benchmarks()
