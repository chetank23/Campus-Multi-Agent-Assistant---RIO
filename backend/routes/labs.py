from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.space_time import Lab
from backend.schemas.lab import LabCreate, LabUpdate, LabResponse

router = APIRouter(prefix="/labs", tags=["Labs"])

@router.get("/", response_model=List[LabResponse])
def get_labs(db: Session = Depends(get_db)):
    return db.query(Lab).all()

@router.post("/", response_model=LabResponse)
def create_lab(lab: LabCreate, db: Session = Depends(get_db)):
    db_lab = Lab(**lab.model_dump())
    db.add(db_lab)
    db.commit()
    db.refresh(db_lab)
    return db_lab

@router.get("/{lab_id}", response_model=LabResponse)
def get_lab(lab_id: int, db: Session = Depends(get_db)):
    db_lab = db.query(Lab).filter(Lab.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    return db_lab

@router.put("/{lab_id}", response_model=LabResponse)
def update_lab(lab_id: int, lab: LabUpdate, db: Session = Depends(get_db)):
    db_lab = db.query(Lab).filter(Lab.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    for key, value in lab.model_dump(exclude_unset=True).items():
        setattr(db_lab, key, value)
    db.commit()
    db.refresh(db_lab)
    return db_lab

@router.delete("/{lab_id}")
def delete_lab(lab_id: int, db: Session = Depends(get_db)):
    db_lab = db.query(Lab).filter(Lab.id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    db.delete(db_lab)
    db.commit()
    return {"ok": True}
