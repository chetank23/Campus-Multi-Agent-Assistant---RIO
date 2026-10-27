"""
agents/common/operation_proposal_store.py
-----------------------------------------
Thread-safe, request-scoped proposal storage with expiry and single-use idempotency
for consequential application operations (approvals, rejections, cancellations, lifecycle mutations).
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
    superseded: bool = False


class OperationProposalStore:
    def __init__(self, ttl_seconds: int = 900):  # 15 minutes TTL
        self.ttl_seconds = ttl_seconds
        self._proposals: Dict[str, OperationProposal] = {}
        self._lock = threading.Lock()

    def _proposal_from_db(self, ap: AgentProposal) -> OperationProposal:
        payload = ap.payload or {}
        created_ts = ap.created_at.timestamp() if ap.created_at else time.time()
        expires_ts = ap.expires_at.timestamp() if ap.expires_at else time.time() + self.ttl_seconds
        return OperationProposal(
            proposal_id=ap.proposal_id,
            user_id=ap.user_id,
            role=ap.role,
            action_name=payload.get("action_name", ""),
            entity_type=payload.get("entity_type", ""),
            entity_id=payload.get("entity_id", 0),
            entity_name=payload.get("entity_name", ""),
            changes=payload.get("changes", {}),
            consequences=payload.get("consequences", ""),
            proposal_data=payload.get("proposal_data", {}),
            created_at=created_ts,
            expires_at=expires_ts,
            consumed=ap.consumed,
            superseded=ap.superseded,
        )

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
            now_dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).replace(tzinfo=None)
            exp_dt = datetime.datetime.fromtimestamp(now + self.ttl_seconds, tz=datetime.timezone.utc).replace(tzinfo=None)

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

            # Database persistence
            try:
                with SessionLocal() as db:
                    ap = AgentProposal(
                        proposal_id=proposal_id,
                        proposal_type="OPERATION",
                        user_id=user_id,
                        role=role,
                        revision=1,
                        consumed=False,
                        superseded=False,
                        payload={
                            "action_name": action_name,
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "entity_name": entity_name,
                            "changes": changes,
                            "consequences": consequences,
                            "proposal_data": proposal_data or {},
                        },
                        created_at=now_dt,
                        expires_at=exp_dt,
                    )
                    db.add(ap)
                    db.commit()
            except Exception:
                pass

            return proposal

    def get_proposal(self, proposal_id: str) -> Optional[OperationProposal]:
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
            except Exception:
                pass

            p = self._proposals.get(proposal_id)
            if p and getattr(p, "superseded", False):
                return None
            return p

    def consume_proposal(
        self,
        proposal_id: str,
        user_id: int,
    ) -> Tuple[bool, Optional[OperationProposal], str]:
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
                        if ap.consumed:
                            return False, None, "Proposal has already been confirmed and processed (duplicate execution blocked)."
                        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        if now_utc > ap.expires_at:
                            return False, None, "Proposal has expired. Please initiate a fresh request."

                        ap.consumed = True
                        db.commit()

                        prop = self._proposal_from_db(ap)
                        self._proposals[proposal_id] = prop
                        return True, prop, ""
            except Exception:
                pass

            # In-memory fallback
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

            # Check DB first
            try:
                with SessionLocal() as db:
                    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    ap = (
                        db.query(AgentProposal)
                        .filter(
                            AgentProposal.user_id == user_id,
                            AgentProposal.proposal_type == "OPERATION",
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
            except Exception:
                pass

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
            except Exception:
                pass

            p = self._proposals.get(proposal_id)
            if p and p.user_id == user_id and not p.consumed:
                p.superseded = True
                del self._proposals[proposal_id]
                return True
            return db_discarded

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._proposals.items() if now > v.expires_at]
        for k in expired:
            del self._proposals[k]


operation_proposal_store = OperationProposalStore()
