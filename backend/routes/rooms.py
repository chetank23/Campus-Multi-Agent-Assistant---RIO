from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import csv
import io
from datetime import date

from backend.database import get_db
from backend.models.space_time import Room, Building
from backend.models.timetable import TimetableEntry
from backend.models.resources import ResourceBooking
from backend.schemas.room import RoomCreate, RoomUpdate, RoomResponse

router = APIRouter(prefix="/rooms", tags=["Rooms"])

@router.get("/", response_model=List[RoomResponse])
def get_rooms(db: Session = Depends(get_db)):
    return db.query(Room).all()

@router.post("/", response_model=RoomResponse)
def create_room(room: RoomCreate, db: Session = Depends(get_db)):
    db_room = Room(**room.model_dump())
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    return db_room

@router.get("/{room_id}", response_model=RoomResponse)
def get_room(room_id: int, db: Session = Depends(get_db)):
    db_room = db.query(Room).filter(Room.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="Room not found")
    return db_room

@router.put("/{room_id}", response_model=RoomResponse)
def update_room(room_id: int, room: RoomUpdate, db: Session = Depends(get_db)):
    db_room = db.query(Room).filter(Room.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="Room not found")
    for key, value in room.model_dump(exclude_unset=True).items():
        setattr(db_room, key, value)
    db.commit()
    db.refresh(db_room)
    return db_room

@router.delete("/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db)):
    db_room = db.query(Room).filter(Room.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="Room not found")
    db.delete(db_room)
    db.commit()
    return {"ok": True}

@router.get("/{room_id}/availability")
def get_room_availability(room_id: int, check_date: date, slot_id: int, db: Session = Depends(get_db)):
    # Check TimetableEntry (this assumes TimetableEntry spans the whole semester)
    # This is a stubbed basic check. True timetabling will need semester date boundary checks.
    timetable_conflict = db.query(TimetableEntry).filter(
        TimetableEntry.room_id == room_id,
        TimetableEntry.slot_id == slot_id,
        TimetableEntry.status.in_(["ACTIVE"])
    ).first()
    
    if timetable_conflict:
        return {"available": False, "reason": "Scheduled for class"}
        
    return {"available": True, "reason": None}

@router.post("/import")
def import_rooms_preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    
    valid_rows = []
    errors = []
    
    required_cols = {"building_id", "room_number", "capacity", "room_type"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must contain at least columns: {required_cols}")
        
    allowed_types = {'CLASSROOM', 'LAB', 'SEMINAR_HALL', 'AUDITORIUM', 'MEETING_ROOM'}
    
    # Pre-fetch building IDs for fast validation
    building_ids = {b.id for b in db.query(Building.id).all()}
        
    for idx, row in enumerate(reader, start=2):
        row_errors = []
        b_id = row.get("building_id", "").strip()
        r_num = row.get("room_number", "").strip()
        floor = row.get("floor_number", "").strip()
        cap = row.get("capacity", "").strip()
        r_type = row.get("room_type", "").strip()
        
        parsed_b_id = None
        if not b_id:
            row_errors.append("Missing building_id")
        else:
            try:
                parsed_b_id = int(b_id)
                if parsed_b_id not in building_ids:
                    row_errors.append(f"Building ID {parsed_b_id} does not exist")
            except ValueError:
                row_errors.append("building_id must be an integer")
                
        if not r_num:
            row_errors.append("Missing room_number")
            
        parsed_floor = None
        if floor:
            try:
                parsed_floor = int(floor)
            except ValueError:
                row_errors.append("floor_number must be an integer")
                
        parsed_cap = None
        if not cap:
            row_errors.append("Missing capacity")
        else:
            try:
                parsed_cap = int(cap)
                if parsed_cap <= 0:
                    row_errors.append("capacity must be positive")
            except ValueError:
                row_errors.append("capacity must be an integer")
                
        if r_type not in allowed_types:
            row_errors.append(f"room_type must be one of {allowed_types}")
            
        if row_errors:
            errors.append({"row": idx, "errors": row_errors})
        else:
            valid_rows.append({
                "building_id": parsed_b_id,
                "room_number": r_num,
                "floor_number": parsed_floor,
                "capacity": parsed_cap,
                "room_type": r_type,
                "has_projector": row.get("has_projector", "").lower() == "true",
                "has_smart_board": row.get("has_smart_board", "").lower() == "true",
                "status": row.get("status", "ACTIVE").strip() or "ACTIVE"
            })
            
    return {"valid_rows": valid_rows, "errors": errors}

@router.post("/import/confirm")
def import_rooms_confirm(rows: List[RoomCreate], db: Session = Depends(get_db)):
    inserted = []
    for row in rows:
        db_room = Room(**row.model_dump())
        db.add(db_room)
        inserted.append(db_room)
    db.commit()
    return {"message": f"Successfully imported {len(inserted)} rooms"}
