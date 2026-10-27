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

import datetime
import time
import uuid
import secrets
import threading
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from backend.config import SessionLocal
from backend.models.workflow import AgentProposal
from backend.utils.datetime_utils import utc_now


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

    def _proposal_from_db(self, ap: AgentProposal) -> SchedulingProposal:
        payload = ap.payload or {}
        created_ts = ap.created_at.timestamp() if ap.created_at else time.time()
        expires_ts = ap.expires_at.timestamp() if ap.expires_at else time.time() + self.ttl_seconds
        return SchedulingProposal(
            proposal_id=ap.proposal_id,
            user_id=ap.user_id,
            role=ap.role,
            scope=payload.get("scope", {}),
            scope_display=payload.get("scope_display", {}),
            readiness_status=payload.get("readiness_status", "UNKNOWN"),
            readiness_summary=payload.get("readiness_summary", {}),
            strategy=payload.get("strategy", "BALANCED"),
            revision=ap.revision,
            parent_proposal_id=ap.parent_proposal_id,
            superseded=ap.superseded,
            superseded_by=ap.superseded_by,
            parameters=payload.get("parameters", {}),
            created_at=created_ts,
            expires_at=expires_ts,
            consumed=ap.consumed,
        )

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
            now_dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).replace(tzinfo=None)
            exp_dt = datetime.datetime.fromtimestamp(now + self.ttl_seconds, tz=datetime.timezone.utc).replace(tzinfo=None)

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

            # Database persistence
            try:
                with SessionLocal() as db:
                    ap = AgentProposal(
                        proposal_id=proposal_id,
                        proposal_type="SCHEDULING",
                        user_id=user_id,
                        role=role,
                        revision=revision,
                        parent_proposal_id=parent_proposal_id,
                        superseded=False,
                        superseded_by=None,
                        consumed=False,
                        payload={
                            "scope": scope,
                            "scope_display": scope_display,
                            "readiness_status": readiness_status,
                            "readiness_summary": readiness_summary,
                            "strategy": strategy,
                            "parameters": parameters or {},
                        },
                        created_at=now_dt,
                        expires_at=exp_dt,
                    )
                    db.add(ap)
                    db.commit()
            except Exception:
                pass

            return proposal

    def revise_proposal(
        self,
        parent_proposal_id: str,
        user_id: int,
        updates: Dict[str, Any],
    ) -> tuple[bool, Optional[SchedulingProposal], str]:
        with self._lock:
            self._purge_expired()

            # Attempt DB-backed transactional revision first
            try:
                with SessionLocal() as db:
                    ap_parent = (
                        db.query(AgentProposal)
                        .filter(AgentProposal.proposal_id == parent_proposal_id)
                        .with_for_update()
                        .first()
                    )
                    if ap_parent:
                        if ap_parent.user_id != user_id:
                            return False, None, "Access denied: Proposal belongs to another user session."
                        if ap_parent.consumed:
                            return False, None, "Cannot revise: Proposal has already been confirmed and executed."
                        if ap_parent.superseded:
                            return False, None, f"Cannot revise: Proposal has already been superseded by revision {ap_parent.superseded_by}."
                        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if now_utc > ap_parent.expires_at:
                            return False, None, "Cannot revise: Proposal has expired. Please request a fresh schedule review."

                        new_id = f"prop_{secrets.token_hex(16)}"
                        new_revision = ap_parent.revision + 1
                        ap_parent.superseded = True
                        ap_parent.superseded_by = new_id

                        parent_payload = ap_parent.payload or {}
                        merged_params = dict(parent_payload.get("parameters", {}))
                        if "parameters" in updates:
                            merged_params.update(updates["parameters"])

                        new_strategy = updates.get("strategy", parent_payload.get("strategy", "BALANCED"))
                        new_scope = updates.get("scope", parent_payload.get("scope", {}))
                        new_scope_display = updates.get("scope_display", parent_payload.get("scope_display", {}))
                        new_readiness_status = updates.get("readiness_status", parent_payload.get("readiness_status", "UNKNOWN"))
                        new_readiness_summary = updates.get("readiness_summary", parent_payload.get("readiness_summary", {}))

                        now_ts = time.time()
                        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc).replace(tzinfo=None)
                        exp_dt = datetime.datetime.fromtimestamp(now_ts + self.ttl_seconds, tz=datetime.timezone.utc).replace(tzinfo=None)

                        ap_child = AgentProposal(
                            proposal_id=new_id,
                            proposal_type="SCHEDULING",
                            user_id=user_id,
                            role=ap_parent.role,
                            revision=new_revision,
                            parent_proposal_id=ap_parent.proposal_id,
                            superseded=False,
                            superseded_by=None,
                            consumed=False,
                            payload={
                                "scope": new_scope,
                                "scope_display": new_scope_display,
                                "readiness_status": new_readiness_status,
                                "readiness_summary": new_readiness_summary,
                                "strategy": new_strategy,
                                "parameters": merged_params,
                            },
                            created_at=now_dt,
                            expires_at=exp_dt,
                        )
                        db.add(ap_child)
                        db.commit()

                        revised = self._proposal_from_db(ap_child)
                        self._proposals[new_id] = revised
                        if parent_proposal_id in self._proposals:
                            self._proposals[parent_proposal_id].superseded = True
                            self._proposals[parent_proposal_id].superseded_by = new_id
                        return True, revised, ""
            except Exception:
                pass

            # Fallback to in-memory revision if DB was not reachable
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

            parent.superseded = True
            parent.superseded_by = new_id

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

            # Query database first for authoritative durability across restarts
            try:
                with SessionLocal() as db:
                    ap = db.query(AgentProposal).filter(AgentProposal.proposal_id == proposal_id).first()
                    if ap:
                        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if now_utc <= ap.expires_at:
                            prop = self._proposal_from_db(ap)
                            self._proposals[proposal_id] = prop
                            return prop
                        else:
                            return None
            except Exception:
                pass

            return self._proposals.get(proposal_id)

    def consume_proposal(
        self,
        proposal_id: str,
        user_id: int,
    ) -> tuple[bool, Optional[SchedulingProposal], str]:
        with self._lock:
            self._purge_expired()

            # Database row-locked consumption
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
                            return False, None, f"Confirmation Blocked: Proposal {proposal_id} has been superseded by revision {ap.superseded_by}. Please confirm the latest revision."
                        if ap.consumed:
                            return False, None, "Proposal has already been confirmed and executed (duplicate submission blocked)."
                        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if now_utc > ap.expires_at:
                            return False, None, "Proposal has expired. Please request a fresh schedule review."

                        ap.consumed = True
                        db.commit()

                        prop = self._proposal_from_db(ap)
                        self._proposals[proposal_id] = prop
                        return True, prop, ""
            except Exception:
                pass

            # In-memory fallback
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

            proposal.consumed = True
            return True, proposal, ""

    def get_latest_pending_proposal(self, user_id: int) -> Optional[SchedulingProposal]:
        with self._lock:
            self._purge_expired()

            # Check DB first for cross-worker / post-restart durability
            try:
                with SessionLocal() as db:
                    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    ap = (
                        db.query(AgentProposal)
                        .filter(
                            AgentProposal.user_id == user_id,
                            AgentProposal.proposal_type == "SCHEDULING",
                            AgentProposal.consumed == False,
                            AgentProposal.superseded == False,
                            AgentProposal.expires_at >= now_utc,
                        )
                        .order_by(AgentProposal.created_at.desc(), AgentProposal.revision.desc())
                        .first()
                    )
                    if ap:
                        prop = self._proposal_from_db(ap)
                        self._proposals[prop.proposal_id] = prop
                        return prop
            except Exception:
                pass

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
        with self._lock:
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
            except Exception:
                pass

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


proposal_store = ProposalStore()
