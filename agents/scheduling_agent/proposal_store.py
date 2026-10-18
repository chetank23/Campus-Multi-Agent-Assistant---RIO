"""
agents/scheduling_agent/proposal_store.py
-----------------------------------------
Thread-safe, request-scoped proposal storage with expiry and single-use idempotency.
Guarantees:
- Proposals are associated with caller ID and ADMIN role.
- One-time consumption prevents duplicate or replayed generation runs.
- Automatic TTL expiry (default 15 minutes).
"""

from __future__ import annotations

import time
import uuid
import secrets
import threading
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SchedulingProposal(BaseModel):
    proposal_id: str
    user_id: int
    role: str
    scope: Dict[str, Any]
    scope_display: Dict[str, str]
    readiness_status: str
    readiness_summary: Dict[str, Any]
    strategy: str = "BALANCED"
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    consumed: bool = False


class ProposalStore:
    def __init__(self, ttl_seconds: int = 900):  # 15 min TTL
        self.ttl_seconds = ttl_seconds
        self._proposals: Dict[str, SchedulingProposal] = {}
        self._lock = threading.Lock()

    def create_proposal(
        self,
        user_id: int,
        role: str,
        scope: Dict[str, Any],
        scope_display: Dict[str, str],
        readiness_status: str,
        readiness_summary: Dict[str, Any],
        strategy: str = "BALANCED",
    ) -> SchedulingProposal:
        with self._lock:
            self._purge_expired()
            proposal_id = f"prop_{secrets.token_hex(16)}"
            now = time.time()
            proposal = SchedulingProposal(
                proposal_id=proposal_id,
                user_id=user_id,
                role=role,
                scope=scope,
                scope_display=scope_display,
                readiness_status=readiness_status,
                readiness_summary=readiness_summary,
                strategy=strategy,
                created_at=now,
                expires_at=now + self.ttl_seconds,
                consumed=False,
            )
            self._proposals[proposal_id] = proposal
            return proposal

    def get_proposal(self, proposal_id: str) -> Optional[SchedulingProposal]:
        with self._lock:
            self._purge_expired()
            return self._proposals.get(proposal_id)

    def consume_proposal(
        self,
        proposal_id: str,
        user_id: int,
    ) -> tuple[bool, Optional[SchedulingProposal], str]:
        """
        Atomically checks and consumes a proposal.
        Returns: (success, proposal, error_message)
        """
        with self._lock:
            self._purge_expired()
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                return False, None, "Proposal not found or has expired. Please create a new schedule request."

            if proposal.user_id != user_id:
                return False, None, "Access denied: Proposal belongs to another user session."

            if proposal.consumed:
                return False, None, "Proposal has already been confirmed and executed (duplicate submission blocked)."

            if time.time() > proposal.expires_at:
                del self._proposals[proposal_id]
                return False, None, "Proposal has expired. Please request a fresh schedule review."

            # Mark consumed
            proposal.consumed = True
            return True, proposal, ""

    def _purge_expired(self):
        now = time.time()
        expired_keys = [k for k, v in self._proposals.items() if now > v.expires_at]
        for k in expired_keys:
            del self._proposals[k]


# Singleton in-process proposal store
proposal_store = ProposalStore()
