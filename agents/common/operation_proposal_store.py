"""
agents/common/operation_proposal_store.py
-----------------------------------------
Thread-safe, request-scoped proposal storage with expiry and single-use idempotency
for consequential application operations (approvals, rejections, cancellations, lifecycle mutations).
"""

from __future__ import annotations

import time
import secrets
import threading
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field


class OperationProposal(BaseModel):
    proposal_id: str
    user_id: int
    role: str
    action_name: str
    entity_type: str
    entity_id: int
    entity_name: str
    changes: Dict[str, Any]
    consequences: str
    proposal_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    consumed: bool = False


class OperationProposalStore:
    def __init__(self, ttl_seconds: int = 900):  # 15 minutes TTL
        self.ttl_seconds = ttl_seconds
        self._proposals: Dict[str, OperationProposal] = {}
        self._lock = threading.Lock()

    def create_proposal(
        self,
        user_id: int,
        role: str,
        action_name: str,
        entity_type: str,
        entity_id: int,
        entity_name: str,
        changes: Dict[str, Any],
        consequences: str,
        proposal_data: Optional[Dict[str, Any]] = None,
    ) -> OperationProposal:
        with self._lock:
            self._purge_expired()
            proposal_id = f"op_prop_{secrets.token_hex(16)}"
            now = time.time()
            proposal = OperationProposal(
                proposal_id=proposal_id,
                user_id=user_id,
                role=role,
                action_name=action_name,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                changes=changes,
                consequences=consequences,
                proposal_data=proposal_data or {},
                created_at=now,
                expires_at=now + self.ttl_seconds,
                consumed=False,
            )
            self._proposals[proposal_id] = proposal
            return proposal

    def get_proposal(self, proposal_id: str) -> Optional[OperationProposal]:
        with self._lock:
            self._purge_expired()
            return self._proposals.get(proposal_id)

    def consume_proposal(
        self,
        proposal_id: str,
        user_id: int,
    ) -> Tuple[bool, Optional[OperationProposal], str]:
        with self._lock:
            self._purge_expired()
            p = self._proposals.get(proposal_id)
            if not p:
                return False, None, "Proposal not found or has expired. Please initiate the request again."

            if p.user_id != user_id:
                return False, None, "Access denied: Proposal belongs to another user session."

            if p.consumed:
                return False, None, "Proposal has already been confirmed and processed (duplicate execution blocked)."

            if time.time() > p.expires_at:
                del self._proposals[proposal_id]
                return False, None, "Proposal has expired. Please initiate a fresh request."

            p.consumed = True
            return True, p, ""

    def get_latest_pending_proposal(self, user_id: int) -> Optional[OperationProposal]:
        with self._lock:
            self._purge_expired()
            now = time.time()
            user_props = [
                p for p in self._proposals.values()
                if p.user_id == user_id and not p.consumed and now <= p.expires_at
            ]
            if not user_props:
                return None
            user_props.sort(key=lambda p: p.created_at, reverse=True)
            return user_props[0]

    def discard_proposal(self, proposal_id: str, user_id: int) -> bool:
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p and p.user_id == user_id and not p.consumed:
                del self._proposals[proposal_id]
                return True
            return False

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._proposals.items() if now > v.expires_at]
        for k in expired:
            del self._proposals[k]


operation_proposal_store = OperationProposalStore()
