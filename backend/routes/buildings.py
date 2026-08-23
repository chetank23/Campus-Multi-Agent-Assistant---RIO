from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import csv
import io

from backend.database import get_db
from backend.models.space_time import Building
from backend.schemas.building import BuildingCreate, BuildingUpdate, BuildingResponse

router = APIRouter(prefix="/buildings", tags=["Buildings"])

@router.get("/", response_model=List[BuildingResponse])
def get_buildings(db: Session = Depends(get_db)):
    return db.query(Building).all()

@router.post("/", response_model=BuildingResponse)
def create_building(building: BuildingCreate, db: Session = Depends(get_db)):
    db_building = Building(**building.model_dump())
    db.add(db_building)
    db.commit()
    db.refresh(db_building)
    return db_building

@router.get("/{building_id}", response_model=BuildingResponse)
def get_building(building_id: int, db: Session = Depends(get_db)):
    db_building = db.query(Building).filter(Building.id == building_id).first()
    if not db_building:
        raise HTTPException(status_code=404, detail="Building not found")
    return db_building

@router.put("/{building_id}", response_model=BuildingResponse)
def update_building(building_id: int, building: BuildingUpdate, db: Session = Depends(get_db)):
    db_building = db.query(Building).filter(Building.id == building_id).first()
    if not db_building:
        raise HTTPException(status_code=404, detail="Building not found")
    for key, value in building.model_dump(exclude_unset=True).items():
        setattr(db_building, key, value)
    db.commit()
    db.refresh(db_building)
    return db_building

@router.delete("/{building_id}")
def delete_building(building_id: int, db: Session = Depends(get_db)):
    db_building = db.query(Building).filter(Building.id == building_id).first()
    if not db_building:
        raise HTTPException(status_code=404, detail="Building not found")
    db.delete(db_building)
    db.commit()
    return {"ok": True}

@router.post("/import")
def import_buildings_preview(file: UploadFile = File(...)):
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    
    valid_rows = []
    errors = []
    
    required_cols = {"name", "code"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must contain at least columns: {required_cols}")
        
    for idx, row in enumerate(reader, start=2):
        row_errors = []
        name = row.get("name", "").strip()
        code = row.get("code", "").strip()
        location = row.get("location", "").strip()
        floors = row.get("number_of_floors", "").strip()
        
        if not name:
            row_errors.append("Missing name")
        if not code:
            row_errors.append("Missing code")
            
        floor_num = None
        if floors:
            try:
                floor_num = int(floors)
            except ValueError:
                row_errors.append("number_of_floors must be an integer")
                
        if row_errors:
            errors.append({"row": idx, "errors": row_errors})
        else:
            valid_rows.append({
                "name": name,
                "code": code,
                "location": location if location else None,
                "number_of_floors": floor_num
            })
            
    return {"valid_rows": valid_rows, "errors": errors}

@router.post("/import/confirm")
def import_buildings_confirm(rows: List[BuildingCreate], db: Session = Depends(get_db)):
    inserted = []
    for row in rows:
        db_building = Building(**row.model_dump())
        db.add(db_building)
        inserted.append(db_building)
    db.commit()
    return {"message": f"Successfully imported {len(inserted)} buildings"}
