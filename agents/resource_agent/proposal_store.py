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

import datetime
import time
import secrets
import threading
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from backend.config import SessionLocal
from backend.models.workflow import AgentProposal


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
    superseded: bool = False


class ResourceProposalStore:
    def __init__(self, ttl_seconds: int = 900):  # 15 minutes TTL
        self.ttl_seconds = ttl_seconds
        self._proposals: Dict[str, ResourceProposal] = {}
        self._lock = threading.Lock()

    def _proposal_from_db(self, ap: AgentProposal) -> ResourceProposal:
        payload = ap.payload or {}
        created_ts = ap.created_at.timestamp() if ap.created_at else time.time()
        expires_ts = ap.expires_at.timestamp() if ap.expires_at else time.time() + self.ttl_seconds
        return ResourceProposal(
            proposal_id=ap.proposal_id,
            user_id=ap.user_id,
            role=ap.role,
            resource_id=payload.get("resource_id", 0),
            resource_name=payload.get("resource_name", ""),
            resource_type=payload.get("resource_type", "FACILITY"),
            location=payload.get("location"),
            capacity=payload.get("capacity"),
            date=payload.get("date", ""),
            start_time=payload.get("start_time", ""),
            end_time=payload.get("end_time", ""),
            purpose=payload.get("purpose", ""),
            created_at=created_ts,
            expires_at=expires_ts,
            consumed=ap.consumed,
            superseded=ap.superseded,
        )

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
            now_dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).replace(tzinfo=None)
            exp_dt = datetime.datetime.fromtimestamp(now + self.ttl_seconds, tz=datetime.timezone.utc).replace(tzinfo=None)

            for p in self._proposals.values():
                if p.user_id == user_id and not p.consumed and not p.superseded:
                    p.superseded = True

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
                superseded=False,
            )
            self._proposals[proposal_id] = proposal

            # Database persistence
            try:
                with SessionLocal() as db:
                    # Supersede prior active proposals for this user
                    (
                        db.query(AgentProposal)
                        .filter(
                            AgentProposal.user_id == user_id,
                            AgentProposal.proposal_type == "RESOURCE_BOOKING",
                            AgentProposal.consumed.is_(False),
                            AgentProposal.superseded.is_(False),
                        )
                        .update({"superseded": True, "superseded_by": proposal_id})
                    )
                    ap = AgentProposal(
                        proposal_id=proposal_id,
                        proposal_type="RESOURCE_BOOKING",
                        user_id=user_id,
                        role=role,
                        revision=1,
                        consumed=False,
                        superseded=False,
                        payload={
                            "resource_id": resource_id,
                            "resource_name": resource_name,
                            "resource_type": resource_type,
                            "location": location,
                            "capacity": capacity,
                            "date": date,
                            "start_time": start_time,
                            "end_time": end_time,
                            "purpose": purpose,
                        },
                        created_at=now_dt,
                        expires_at=exp_dt,
                    )
                    db.add(ap)
                    db.commit()
            except Exception as exc:
                # A proposal must never be reported as created unless its
                # durable record was committed successfully.
                self._proposals.pop(proposal_id, None)
                raise RuntimeError(
                    "Proposal could not be persisted; no confirmation token was issued."
                ) from exc

            return proposal

    def get_proposal(self, proposal_id: str) -> Optional[ResourceProposal]:
        with self._lock:
            self._purge_expired()

            # Query database first
            try:
                with SessionLocal() as db:
                    ap = db.query(AgentProposal).filter(AgentProposal.proposal_id == proposal_id).first()
                    if ap:
                        if ap.superseded:
                            return None
                        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if now_utc <= ap.expires_at:
                            prop = self._proposal_from_db(ap)
                            self._proposals[proposal_id] = prop
                            return prop
                        else:
                            return None
            except Exception as exc:
                # Database state is authoritative; never fall back to a potentially
                # stale in-memory proposal after a persistence-layer failure.
                raise RuntimeError(
                    "Proposal storage is temporarily unavailable; retry the operation."
                ) from exc

            p = self._proposals.get(proposal_id)
            if p and getattr(p, "superseded", False):
                return None
            return p

    def consume_proposal(
        self,
        proposal_id: str,
        user_id: int,
    ) -> Tuple[bool, Optional[ResourceProposal], str]:
        with self._lock:
            self._purge_expired()

            # DB row-locked consumption
            try:
                with SessionLocal() as db:
                    ap = (
                        db.query(AgentProposal)
                        .filter(AgentProposal.proposal_id == proposal_id)
                        .with_for_update()
                        .first()
                    )
                    if ap:
                        if ap.user_id != user_id:
                            return False, None, "Access denied: Proposal belongs to another user session."
                        if ap.superseded:
                            return False, None, "Confirmation Blocked: Proposal has been discarded or superseded. Please create a new booking request."
                        if ap.consumed:
                            return False, None, "Proposal has already been confirmed and processed (duplicate submission blocked)."
                        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if now_utc > ap.expires_at:
                            return False, None, "Proposal has expired. Please check current availability and request again."

                        ap.consumed = True
                        db.commit()

                        prop = self._proposal_from_db(ap)
                        self._proposals[proposal_id] = prop
                        return True, prop, ""
            except Exception as exc:
                # Database state is authoritative; never fall back to a potentially
                # stale in-memory proposal after a persistence-layer failure.
                raise RuntimeError(
                    "Proposal storage is temporarily unavailable; retry the operation."
                ) from exc

            # In-memory fallback
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                return False, None, "Proposal not found or has expired. Please create a new booking request."

            if proposal.user_id != user_id:
                return False, None, "Access denied: Proposal belongs to another user session."

            if getattr(proposal, "superseded", False):
                return False, None, "Confirmation Blocked: Proposal has been discarded or superseded. Please create a new booking request."

            if proposal.consumed:
                return False, None, "Proposal has already been confirmed and processed (duplicate submission blocked)."

            if time.time() > proposal.expires_at:
                del self._proposals[proposal_id]
                return False, None, "Proposal has expired. Please check current availability and request again."

            proposal.consumed = True
            return True, proposal, ""

    def get_latest_pending_proposal(self, user_id: int) -> Optional[ResourceProposal]:
        with self._lock:
            self._purge_expired()

            # Check DB first
            try:
                with SessionLocal() as db:
                    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    ap = (
                        db.query(AgentProposal)
                        .filter(
                            AgentProposal.user_id == user_id,
                            AgentProposal.proposal_type == "RESOURCE_BOOKING",
                            AgentProposal.consumed == False,
                            AgentProposal.superseded == False,
                            AgentProposal.expires_at >= now_utc,
                        )
                        .order_by(AgentProposal.created_at.desc(), AgentProposal.id.desc())
                        .first()
                    )
                    if ap:
                        prop = self._proposal_from_db(ap)
                        self._proposals[prop.proposal_id] = prop
                        return prop
            except Exception as exc:
                # Database state is authoritative; never fall back to a potentially
                # stale in-memory proposal after a persistence-layer failure.
                raise RuntimeError(
                    "Proposal storage is temporarily unavailable; retry the operation."
                ) from exc

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
            db_discarded = False
            try:
                with SessionLocal() as db:
                    ap = (
                        db.query(AgentProposal)
                        .filter(AgentProposal.proposal_id == proposal_id, AgentProposal.user_id == user_id)
                        .first()
                    )
                    if ap and not ap.consumed:
                        ap.superseded = True
                        db.commit()
                        db_discarded = True
            except Exception as exc:
                # Database state is authoritative; never fall back to a potentially
                # stale in-memory proposal after a persistence-layer failure.
                raise RuntimeError(
                    "Proposal storage is temporarily unavailable; retry the operation."
                ) from exc

            p = self._proposals.get(proposal_id)
            if p and p.user_id == user_id and not p.consumed:
                p.superseded = True
                del self._proposals[proposal_id]
                return True
            return db_discarded

    def _purge_expired(self):
        now = time.time()
        expired_keys = [k for k, v in self._proposals.items() if now > v.expires_at]
        for k in expired_keys:
            del self._proposals[k]


resource_proposal_store = ResourceProposalStore()
