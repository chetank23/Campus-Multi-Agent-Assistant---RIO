"""
backend/routes/users.py
-----------------------
Administrative User & Role Management endpoints for RIO-MJP.
Strictly restricted to users with ADMIN role.
All mutations are recorded in AuditLog.
"""

from __future__ import annotations

from typing import Literal, Optional, cast
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from backend.core.security import get_password_hash
from backend.database import get_db
from backend.dependencies import require_role
from backend.models.academic import Department
from backend.models.identity import User
from backend.models.workflow import AuditLog
from backend.schemas.user import (
    UserAdminCreate,
    UserAdminResponse,
    UserAdminUpdate,
    UserListResponse,
    UserPasswordReset,
)

router = APIRouter(prefix="/users", tags=["Users & Roles"])


def _to_user_admin_response(u: User) -> UserAdminResponse:
    dept_name = u.department.name if u.department else None
    role_lit = cast(Literal["ADMIN", "FACULTY", "STUDENT", "SUPER_ADMIN"], u.role if u.role in ("ADMIN", "FACULTY", "STUDENT", "SUPER_ADMIN") else "STUDENT")
    return UserAdminResponse(
        id=u.id,
        name=u.name,
        email=u.email,
        role=role_lit,
        department_id=u.department_id,
        department_name=dept_name,
        is_active=u.is_active,
        created_at=u.created_at,
    )


@router.get("", response_model=UserListResponse)
@router.get("/", response_model=UserListResponse, include_in_schema=False)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    role: Optional[str] = Query(None, pattern="^(ADMIN|FACULTY|STUDENT|SUPER_ADMIN)$"),
    department_id: Optional[int] = Query(None, gt=0),
    search: Optional[str] = Query(None, min_length=1),
    is_active: Optional[bool] = Query(None),
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    ADMIN only: List registered campus users with optional filtering and pagination.
    """
    query = db.query(User).options(joinedload(User.department))

    if role:
        query = query.filter(User.role == role)
    if department_id:
        query = query.filter(User.department_id == department_id)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter((User.name.ilike(s)) | (User.email.ilike(s)))

    total = query.count()
    users = query.order_by(User.id.asc()).offset(skip).limit(limit).all()

    return UserListResponse(
        items=[_to_user_admin_response(u) for u in users],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{user_id}", response_model=UserAdminResponse)
def get_user_detail(
    user_id: int,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    ADMIN only: Retrieve detailed profile of a specific user.
    """
    u = (
        db.query(User)
        .options(joinedload(User.department))
        .filter(User.id == user_id)
        .first()
    )
    if not u:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User #{user_id} not found",
        )
    return _to_user_admin_response(u)


@router.post("", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_user(
    body: UserAdminCreate,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    ADMIN only: Provision a new user account with hashed password and role assignment.
    """
    # Check duplicate email
    existing = db.query(User).filter(User.email.ilike(body.email.strip())).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{body.email}' already exists.",
        )

    # Check department if provided
    if body.department_id:
        dept = db.query(Department).filter(Department.id == body.department_id).first()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department #{body.department_id} not found.",
            )

    new_user = User(
        name=body.name.strip(),
        email=body.email.strip().lower(),
        password_hash=get_password_hash(body.password),
        role=body.role,
        department_id=body.department_id,
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    # Audit logging
    db.add(
        AuditLog(
            user_id=admin_user.id,
            action="USER_CREATED",
            entity_type="User",
            entity_id=new_user.id,
            new_value={
                "name": new_user.name,
                "email": new_user.email,
                "role": new_user.role,
                "department_id": new_user.department_id,
            },
        )
    )
    db.commit()
    db.refresh(new_user)
    return _to_user_admin_response(new_user)


@router.patch("/{user_id}", response_model=UserAdminResponse)
def update_user(
    user_id: int,
    body: UserAdminUpdate,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    ADMIN only: Update user role, department, name, or active/suspended status.
    Prevents self-deactivation or demotion of current admin account.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User #{user_id} not found",
        )

    # Self-protection guard
    if target.id == admin_user.id:
        if body.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own administrative account.",
            )
        if body.role and body.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot revoke your own ADMIN role.",
            )

    # Last active ADMIN protection guard
    if target.role == "ADMIN" and (body.is_active is False or (body.role and body.role != "ADMIN")):
        active_admins = (
            db.query(User)
            .filter(User.role == "ADMIN", User.is_active.is_(True))
            .count()
        )
        if target.is_active and active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate or demote the last active ADMIN in the system.",
            )

    if body.department_id is not None:
        if body.department_id > 0:
            dept = db.query(Department).filter(Department.id == body.department_id).first()
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Department #{body.department_id} not found.",
                )
        else:
            body.department_id = None

    old_vals = {}
    new_vals = {}

    if body.name is not None and body.name.strip():
        old_vals["name"] = target.name
        target.name = body.name.strip()
        new_vals["name"] = target.name

    if body.role is not None:
        old_vals["role"] = target.role
        target.role = body.role
        new_vals["role"] = target.role

    if body.department_id is not None or "department_id" in body.model_fields_set:
        old_vals["department_id"] = target.department_id
        target.department_id = body.department_id
        new_vals["department_id"] = target.department_id

    if body.is_active is not None:
        old_vals["is_active"] = target.is_active
        target.is_active = body.is_active
        new_vals["is_active"] = target.is_active

    if old_vals:
        db.add(
            AuditLog(
                user_id=admin_user.id,
                action="USER_UPDATED",
                entity_type="User",
                entity_id=target.id,
                old_value=old_vals,
                new_value=new_vals,
            )
        )
        db.commit()
        db.refresh(target)

    return _to_user_admin_response(target)


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    body: UserPasswordReset,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    ADMIN only: Securely reset a user's password without exposing password hashes.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User #{user_id} not found",
        )

    target.password_hash = get_password_hash(body.new_password)
    db.add(
        AuditLog(
            user_id=admin_user.id,
            action="USER_PASSWORD_RESET",
            entity_type="User",
            entity_id=target.id,
            new_value={"reset_by_admin": admin_user.id},
        )
    )
    db.commit()

    return {"message": f"Password for user '{target.email}' has been reset successfully."}
