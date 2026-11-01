from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models.identity import User
from backend.models.workflow import AuditLog, ChangeRequest
from backend.schemas.change_request import (
    ChangeRequestCreate,
    ChangeRequestResponse,
    ChangeRequestReview,
)

router = APIRouter(prefix="/change-requests", tags=["Change Requests"])


def _response(item: ChangeRequest) -> dict:
    return {
        "id": item.id,
        "requested_by": item.requested_by,
        "request_type": item.request_type,
        "related_entity_id": item.related_entity_id,
        "reason": item.reason,
        "status": item.status,
        "reviewed_by": item.reviewed_by,
        "created_at": item.created_at,
        "review_note": (item.review_note if hasattr(item, "review_note") else None),
    }


@router.post("", response_model=ChangeRequestResponse, status_code=status.HTTP_201_CREATED)
def create_change_request(
    body: ChangeRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = ChangeRequest(
        requested_by=current_user.id,
        request_type=body.request_type,
        related_entity_id=body.related_entity_id,
        reason=body.reason.strip(),
        status="PENDING",
    )
    db.add(item)
    db.flush()
    db.add(AuditLog(
        user_id=current_user.id,
        action="CHANGE_REQUEST_CREATED",
        entity_type="ChangeRequest",
        entity_id=item.id,
        new_value={"request_type": body.request_type, "status": "PENDING"},
    ))
    db.commit()
    db.refresh(item)
    return _response(item)


@router.get("", response_model=list[ChangeRequestResponse])
def list_change_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ChangeRequest)
    if current_user.role != "ADMIN":
        query = query.filter(ChangeRequest.requested_by == current_user.id)
    return [_response(item) for item in query.order_by(ChangeRequest.created_at.desc()).offset(skip).limit(limit).all()]


@router.get("/pending", response_model=list[ChangeRequestResponse])
def list_pending_change_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    items = (
        db.query(ChangeRequest)
        .filter(ChangeRequest.status == "PENDING")
        .order_by(ChangeRequest.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_response(item) for item in items]


@router.patch("/{request_id}/review", response_model=ChangeRequestResponse)
def review_change_request(
    request_id: int,
    body: ChangeRequestReview,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    item = (
        db.query(ChangeRequest)
        .filter(ChangeRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    if item.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending requests can be reviewed")

    old_value = {"status": item.status}
    item.status = body.status
    item.reviewed_by = admin_user.id
    db.add(AuditLog(
        user_id=admin_user.id,
        action=f"CHANGE_REQUEST_{body.status}",
        entity_type="ChangeRequest",
        entity_id=item.id,
        old_value=old_value,
        new_value={"status": body.status, "review_note": body.review_note},
    ))
    db.commit()
    db.refresh(item)
    result = _response(item)
    result["review_note"] = body.review_note
    return result
