from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.space_time import TimeSlot
from backend.models.identity import User
from backend.schemas.time_slot import TimeSlotCreate, TimeSlotUpdate, TimeSlotResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/time-slots", tags=["Time Slots"])

@router.get("/", response_model=List[TimeSlotResponse])
def get_time_slots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(TimeSlot).all()

@router.get("/{slot_id}", response_model=TimeSlotResponse)
def get_time_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    slot = db.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    return slot

@router.post("/", response_model=TimeSlotResponse)
def create_time_slot(
    slot: TimeSlotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_slot = TimeSlot(**slot.model_dump())
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)
    return db_slot

@router.put("/{slot_id}", response_model=TimeSlotResponse)
def update_time_slot(
    slot_id: int,
    slot: TimeSlotUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_slot = db.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
    if not db_slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    for key, value in slot.model_dump(exclude_unset=True).items():
        setattr(db_slot, key, value)
    db.commit()
    db.refresh(db_slot)
    return db_slot

@router.delete("/{slot_id}")
def delete_time_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_slot = db.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
    if not db_slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    db.delete(db_slot)
    db.commit()
    return {"ok": True}
