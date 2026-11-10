"""
agents/common/diagnostics.py
----------------------------
Safe, internal request tracing and diagnostic logging for RIO Campus Assistant.
Tracks request lifecycle across authentication, provider selection, NVIDIA NIM
invocations, tool validations, database queries, and response generation.

Strict Security:
- Zero secrets: NEVER logs API keys, passwords, JWTs, or private student records.
- Records safe operational metadata (request ID, timestamps, tool names, record counts).
"""

from __future__ import annotations

import datetime
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolExecutionTrace:
    """Safe metadata for an individual executed tool call."""
    tool_name: str
    arguments_summary: Dict[str, Any]
    records_returned: int
    execution_time_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class ChatRequestTrace:
    """End-to-end trace of a single chat request lifecycle."""
    request_id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")
    user_id: Optional[int] = None
    role: Optional[str] = None
    message_length: int = 0
    provider: str = "nvidia"
    model: str = ""
    llm_mode: bool = True
    reached_nvidia: bool = False
    nvidia_request_started_at: Optional[str] = None
    nvidia_response_received_at: Optional[str] = None
    tools_requested: List[str] = field(default_factory=list)
    tools_executed: List[ToolExecutionTrace] = field(default_factory=list)
    db_queries_executed: int = 0
    total_records_returned: int = 0
    final_response_generated: bool = False
    success: bool = True
    error: Optional[str] = None
    start_time: float = field(default_factory=time.perf_counter)
    total_duration_ms: float = 0.0

    def mark_nvidia_start(self, model: str) -> None:
        self.model = model
        self.reached_nvidia = True
        self.nvidia_request_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def mark_nvidia_received(self) -> None:
        self.nvidia_response_received_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def record_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        records_count: int,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        self.tools_requested.append(tool_name)
        # Sanitize args: never include sensitive keywords
        safe_args = {k: v for k, v in args.items() if not any(s in k.lower() for s in ["pass", "token", "secret", "key"])}
        self.tools_executed.append(
            ToolExecutionTrace(
                tool_name=tool_name,
                arguments_summary=safe_args,
                records_returned=records_count,
                execution_time_ms=round(duration_ms, 2),
                success=success,
                error=error,
            )
        )
        self.db_queries_executed += 1
        self.total_records_returned += records_count

    def finalize(self, success: bool = True, error: Optional[str] = None) -> Dict[str, Any]:
        self.total_duration_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        self.success = success
        if error:
            self.error = error
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "llm_mode": self.llm_mode,
            "reached_nvidia": self.reached_nvidia,
            "tools_invoked": [t.tool_name for t in self.tools_executed],
            "db_queries_executed": self.db_queries_executed,
            "records_returned": self.total_records_returned,
            "duration_ms": self.total_duration_ms,
            "success": self.success,
            "error": self.error,
        }

