from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.space_time import TimeSlot
from backend.models.timetable import TimetableEntry
from backend.models.identity import User
from backend.schemas.time_slot import TimeSlotCreate, TimeSlotUpdate, TimeSlotResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/time-slots", tags=["Time Slots"])

DAY_NORMALIZE = {
    "MONDAY": "MON", "MON": "MON",
    "TUESDAY": "TUE", "TUE": "TUE",
    "WEDNESDAY": "WED", "WED": "WED",
    "THURSDAY": "THU", "THU": "THU",
    "FRIDAY": "FRI", "FRI": "FRI",
    "SATURDAY": "SAT", "SAT": "SAT",
    "SUNDAY": "SUN", "SUN": "SUN",
}

def _norm_day(day_str: str) -> str:
    cleaned = (day_str or "").strip().upper()
    return DAY_NORMALIZE.get(cleaned, cleaned[:3])

@router.get("", response_model=List[TimeSlotResponse])
@router.get("/", response_model=List[TimeSlotResponse], include_in_schema=False)
def get_time_slots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(TimeSlot).order_by(TimeSlot.day.asc(), TimeSlot.start_time.asc()).all()

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

@router.post("", response_model=TimeSlotResponse)
@router.post("/", response_model=TimeSlotResponse, include_in_schema=False)
def create_time_slot(
    slot: TimeSlotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    
    if slot.start_time >= slot.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start time must be strictly before end time.",
        )
    
    # Overlap validation on same day
    overlap = (
        db.query(TimeSlot)
        .filter(
            TimeSlot.day == slot.day,
            TimeSlot.start_time < slot.end_time,
            TimeSlot.end_time > slot.start_time,
        )
        .first()
    )
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Time slot overlaps with existing slot #{overlap.id} ({overlap.day} {overlap.start_time}-{overlap.end_time}).",
        )

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
    
    if slot.start_time is not None or slot.end_time is not None or slot.day is not None:
        target_start = slot.start_time if slot.start_time is not None else db_slot.start_time
        target_end = slot.end_time if slot.end_time is not None else db_slot.end_time
        target_day = slot.day if slot.day is not None else db_slot.day

        if target_start and target_end and target_start >= target_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start time must be strictly before end time.",
            )

        if target_day and target_start and target_end:
            overlap = (
                db.query(TimeSlot)
                .filter(
                    TimeSlot.id != slot_id,
                    TimeSlot.day == target_day,
                    TimeSlot.start_time < target_end,
                    TimeSlot.end_time > target_start,
                )
                .first()
            )
            if overlap:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Time slot overlaps with existing slot #{overlap.id} ({overlap.day} {overlap.start_time}-{overlap.end_time}).",
                )

    slot_dict = slot.model_dump(exclude_unset=True)
    for key, value in slot_dict.items():
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
    
    referenced_entries = db.query(TimetableEntry).filter(TimetableEntry.slot_id == slot_id).count()
    if referenced_entries > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete time slot #{slot_id} because it is referenced by {referenced_entries} active timetable entry/entries.",
        )

    db.delete(db_slot)
    db.commit()
    return {"ok": True}
