"""
agents/resource_agent/proposal_store.py
---------------------------------------
Thread-safe, request-scoped proposal storage with expiry and single-use idempotency
specifically for Resource Booking proposals.
Guarantees:
- Proposals are associated with caller ID and verified role.
- One-time consumption prevents duplicate booking submissions and replay attacks.
- Automatic TTL expiry (default 15 minutes).
- Cryptographically strong, high-entropy proposal tokens (res_prop_<128-bit hex>).
- Clean isolation from timetable scheduling proposals.
"""

from __future__ import annotations

import time
import secrets
import threading
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field


class ResourceProposal(BaseModel):
    proposal_id: str
    user_id: int
    role: str
    resource_id: int
    resource_name: str
    resource_type: str
    location: Optional[str] = None
    capacity: Optional[int] = None
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM:SS
    end_time: str  # HH:MM:SS
    purpose: str
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    consumed: bool = False


class ResourceProposalStore:
    def __init__(self, ttl_seconds: int = 900):  # 15 minutes TTL
        self.ttl_seconds = ttl_seconds
        self._proposals: Dict[str, ResourceProposal] = {}
        self._lock = threading.Lock()

    def create_proposal(
        self,
        user_id: int,
        role: str,
        resource_id: int,
        resource_name: str,
        resource_type: str,
        date: str,
        start_time: str,
        end_time: str,
        purpose: str,
        location: Optional[str] = None,
        capacity: Optional[int] = None,
    ) -> ResourceProposal:
        with self._lock:
            self._purge_expired()
            proposal_id = f"res_prop_{secrets.token_hex(16)}"
            now = time.time()
            proposal = ResourceProposal(
                proposal_id=proposal_id,
                user_id=user_id,
                role=role,
                resource_id=resource_id,
                resource_name=resource_name,
                resource_type=resource_type,
                location=location,
                capacity=capacity,
                date=date,
                start_time=start_time,
                end_time=end_time,
                purpose=purpose,
                created_at=now,
                expires_at=now + self.ttl_seconds,
                consumed=False,
            )
            self._proposals[proposal_id] = proposal
            return proposal

    def get_proposal(self, proposal_id: str) -> Optional[ResourceProposal]:
        with self._lock:
            self._purge_expired()
            return self._proposals.get(proposal_id)

    def consume_proposal(
        self,
        proposal_id: str,
        user_id: int,
    ) -> Tuple[bool, Optional[ResourceProposal], str]:
        """
        Atomically checks and consumes a resource booking proposal.
        Returns: (success, proposal, error_message)
        """
        with self._lock:
            self._purge_expired()
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                return False, None, "Proposal not found or has expired. Please create a new booking request."

            if proposal.user_id != user_id:
                return False, None, "Access denied: Proposal belongs to another user session."

            if proposal.consumed:
                return False, None, "Proposal has already been confirmed and processed (duplicate submission blocked)."

            if time.time() > proposal.expires_at:
                del self._proposals[proposal_id]
                return False, None, "Proposal has expired. Please check current availability and request again."

            # Mark consumed atomically
            proposal.consumed = True
            return True, proposal, ""

    def _purge_expired(self):
        now = time.time()
        expired_keys = [k for k, v in self._proposals.items() if now > v.expires_at]
        for k in expired_keys:
            del self._proposals[k]


# Singleton in-process resource proposal store
resource_proposal_store = ResourceProposalStore()
