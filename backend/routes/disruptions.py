"""
backend/routes/disruptions.py
-----------------------------
REST API endpoints for Academic Timetable Disruption Intake,
Minimal-Perturbation Rescheduling Proposals, and Approved Publication.
"""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import require_role
from backend.models.identity import User
from backend.services.disruption_service import (
    DisruptionSpec,
    DisruptionImpactAnalysis,
    ReschedulingProposalResult,
    ReschedulingPublishResult,
    analyze_disruption_impact,
    create_rescheduling_proposal,
    execute_publish_rescheduled_proposal,
)

router = APIRouter(prefix="/timetable/disruptions", tags=["Disruptions & Rescheduling"])


class ConfirmDisruptionProposalRequest(BaseModel):
    proposal_id: str = Field(..., description="Idempotency token starting with disrupt_prop_")


@router.post("/analyze", response_model=DisruptionImpactAnalysis)
def analyze_disruption(
    spec: DisruptionSpec,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_role("ADMIN")),
):
    """
    ADMIN only: Analyzes the impact of an academic disruption against the active published timetable.
    Determines all affected sessions, faculty, rooms, courses, sections, and student counts
    without making any changes to the current published timetable.
    """
    return analyze_disruption_impact(db=db, spec=spec)


@router.post("/propose", response_model=ReschedulingProposalResult)
def propose_reschedule(
    spec: DisruptionSpec,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_role("ADMIN")),
):
    """
    ADMIN only: Computes a minimal-perturbation revised timetable using Google OR-Tools CP-SAT.
    Locks all unaffected assignments in place and heavily penalizes slot and room deviations.
    Generates a before-and-after diff and saves a bounded revision proposal awaiting admin confirmation.
    """
    return create_rescheduling_proposal(db=db, spec=spec, current_user=admin_user)


@router.post("/confirm", response_model=ReschedulingPublishResult)
def confirm_and_publish_reschedule(
    req: ConfirmDisruptionProposalRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_role("ADMIN")),
):
    """
    ADMIN only: Atomically publishes an approved minimal-perturbation rescheduling proposal.
    - Validates source timetable and proposal single-use idempotency.
    - Persists new PUBLISHED TimetableVersion and archives prior version.
    - Dispatches targeted notifications to affected faculty and enrolled student batches via durable outbox.
    """
    return execute_publish_rescheduled_proposal(db=db, proposal_id=req.proposal_id, current_user=admin_user)

