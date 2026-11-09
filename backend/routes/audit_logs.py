from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import require_role
from backend.models.identity import User
from backend.models.workflow import AuditLog

router = APIRouter(prefix="/admin/audit-logs", tags=["Audit Logs"])


@router.get("")
def list_audit_logs(
    response: Response,
    user_id: Optional[int] = Query(None, gt=0),
    action: Optional[str] = Query(None, min_length=1, max_length=150),
    entity_type: Optional[str] = Query(None, min_length=1, max_length=50),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    query = db.query(AuditLog)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if since:
        query = query.filter(AuditLog.timestamp >= since)
    if until:
        query = query.filter(AuditLog.timestamp <= until)

    total = query.count()
    rows = (
        query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "timestamp": row.timestamp,
            }
            for row in rows
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }
