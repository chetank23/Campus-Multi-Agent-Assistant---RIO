from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.academic import Batch, Section
from backend.models.identity import User
from backend.schemas.batch import BatchCreate, BatchUpdate, BatchResponse
from backend.dependencies import get_current_user, require_role, require_department_scope

router = APIRouter(prefix="/batches", tags=["Batches"])


@router.get("/", response_model=List[BatchResponse])
def get_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(Batch).all()
    elif current_user.role == "FACULTY":
        # Faculty can see batches of sections in their department via join
        # For simplicity, we can filter via section.department_id
        return db.query(Batch).join(Batch.section).filter(Section.department_id == current_user.department_id).all()
    else:  # STUDENT
        # Students can see their own batch (via student record)
        # We'll implement later via student endpoint; for now return empty.
        return []


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if current_user.role == "ADMIN":
        return batch
    elif current_user.role == "FACULTY":
        # check via section department
        if not batch.section or batch.section.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return batch
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("/", response_model=BatchResponse)
def create_batch(
    batch: BatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_batch = Batch(**batch.model_dump())
    db.add(db_batch)
    db.commit()
    db.refresh(db_batch)
    return db_batch


@router.put("/{batch_id}", response_model=BatchResponse)
def update_batch(
    batch_id: int,
    batch: BatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not db_batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    for key, value in batch.model_dump(exclude_unset=True).items():
        setattr(db_batch, key, value)
    db.commit()
    db.refresh(db_batch)
    return db_batch


@router.delete("/{batch_id}")
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not db_batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    db.delete(db_batch)
    db.commit()
    return {"ok": True}