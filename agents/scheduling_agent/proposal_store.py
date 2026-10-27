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
    revision: int = 1
    parent_proposal_id: Optional[str] = None
    superseded: bool = False
    superseded_by: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
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
        parameters: Optional[Dict[str, Any]] = None,
        revision: int = 1,
        parent_proposal_id: Optional[str] = None,
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
                revision=revision,
                parent_proposal_id=parent_proposal_id,
                superseded=False,
                superseded_by=None,
                parameters=parameters or {},
                created_at=now,
                expires_at=now + self.ttl_seconds,
                consumed=False,
            )
            self._proposals[proposal_id] = proposal
            return proposal

    def revise_proposal(
        self,
        parent_proposal_id: str,
        user_id: int,
        updates: Dict[str, Any],
    ) -> tuple[bool, Optional[SchedulingProposal], str]:
        """
        Safely supersedes an active pending proposal with a revised version.
        Guarantees:
        - Parent proposal is marked superseded and cannot be confirmed.
        - Revision number is incremented.
        - New proposal inherits scope and display, applying requested strategy/parameter changes.
        """
        with self._lock:
            self._purge_expired()
            parent = self._proposals.get(parent_proposal_id)
            if not parent:
                return False, None, "Parent proposal not found or has expired. Please create a new schedule request."

            if parent.user_id != user_id:
                return False, None, "Access denied: Proposal belongs to another user session."

            if parent.consumed:
                return False, None, "Cannot revise: Proposal has already been confirmed and executed."

            if parent.superseded:
                return False, None, f"Cannot revise: Proposal has already been superseded by revision {parent.superseded_by}."

            if time.time() > parent.expires_at:
                del self._proposals[parent_proposal_id]
                return False, None, "Cannot revise: Proposal has expired. Please request a fresh schedule review."

            now = time.time()
            new_id = f"prop_{secrets.token_hex(16)}"
            new_revision = parent.revision + 1

            # Update parent as superseded
            parent.superseded = True
            parent.superseded_by = new_id

            # Merge parameters
            merged_params = dict(parent.parameters)
            if "parameters" in updates:
                merged_params.update(updates["parameters"])

            new_strategy = updates.get("strategy", parent.strategy)
            new_scope = updates.get("scope", parent.scope)
            new_scope_display = updates.get("scope_display", parent.scope_display)
            new_readiness_status = updates.get("readiness_status", parent.readiness_status)
            new_readiness_summary = updates.get("readiness_summary", parent.readiness_summary)

            revised = SchedulingProposal(
                proposal_id=new_id,
                user_id=user_id,
                role=parent.role,
                scope=new_scope,
                scope_display=new_scope_display,
                readiness_status=new_readiness_status,
                readiness_summary=new_readiness_summary,
                strategy=new_strategy,
                revision=new_revision,
                parent_proposal_id=parent.proposal_id,
                superseded=False,
                superseded_by=None,
                parameters=merged_params,
                created_at=now,
                expires_at=now + self.ttl_seconds,
                consumed=False,
            )
            self._proposals[new_id] = revised
            return True, revised, ""

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
        Rejects expired, consumed, superseded, or mismatched proposals.
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

            if proposal.superseded:
                return False, None, f"Confirmation Blocked: Proposal {proposal_id} has been superseded by revision {proposal.superseded_by}. Please confirm the latest revision."

            if time.time() > proposal.expires_at:
                del self._proposals[proposal_id]
                return False, None, "Proposal has expired. Please request a fresh schedule review."

            # Mark consumed
            proposal.consumed = True
            return True, proposal, ""

    def get_latest_pending_proposal(self, user_id: int) -> Optional[SchedulingProposal]:
        """Returns the most recent unconsumed, un-superseded, active proposal created by user_id."""
        with self._lock:
            self._purge_expired()
            now = time.time()
            user_props = [
                p for p in self._proposals.values()
                if p.user_id == user_id and not p.consumed and not p.superseded and now <= p.expires_at
            ]
            if not user_props:
                return None
            user_props.sort(key=lambda p: (p.created_at, p.revision), reverse=True)
            return user_props[0]

    def discard_proposal(self, proposal_id: str, user_id: int) -> bool:
        """Discards an active proposal if owned by user_id."""
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p and p.user_id == user_id and not p.consumed:
                del self._proposals[proposal_id]
                return True
            return False

    def _purge_expired(self):
        now = time.time()
        expired_keys = [k for k, v in self._proposals.items() if now > v.expires_at]
        for k in expired_keys:
            del self._proposals[k]


# Singleton in-process proposal store
proposal_store = ProposalStore()
