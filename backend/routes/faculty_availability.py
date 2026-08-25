from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.space_time import FacultyAvailability
from backend.models.academic import Faculty
from backend.models.identity import User
from backend.schemas.faculty_availability import FacultyAvailabilityCreate, FacultyAvailabilityUpdate, FacultyAvailabilityResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/faculty-availability", tags=["Faculty Availability"])

@router.get("/", response_model=List[FacultyAvailabilityResponse])
def get_all_faculty_availability(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(FacultyAvailability).all()
    elif current_user.role == "FACULTY":
        # Return only their own availability
        return db.query(FacultyAvailability).join(Faculty).filter(Faculty.user_id == current_user.id).all()
    else: # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.get("/{fa_id}", response_model=FacultyAvailabilityResponse)
def get_faculty_availability(
    fa_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fa = db.query(FacultyAvailability).filter(FacultyAvailability.id == fa_id).first()
    if not fa:
        raise HTTPException(status_code=404, detail="Faculty availability not found")
    
    if current_user.role == "ADMIN":
        return fa
    elif current_user.role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.id == fa.faculty_id).first()
        if not fac or fac.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of scope")
        return fa
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.post("/", response_model=FacultyAvailabilityResponse)
def create_faculty_availability(
    fa: FacultyAvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        
    if current_user.role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.id == fa.faculty_id).first()
        if not fac or fac.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create availability for other faculty")
            
    db_fa = FacultyAvailability(**fa.model_dump())
    db.add(db_fa)
    db.commit()
    db.refresh(db_fa)
    return db_fa

@router.put("/{fa_id}", response_model=FacultyAvailabilityResponse)
def update_faculty_availability(
    fa_id: int,
    fa: FacultyAvailabilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        
    db_fa = db.query(FacultyAvailability).filter(FacultyAvailability.id == fa_id).first()
    if not db_fa:
        raise HTTPException(status_code=404, detail="Faculty availability not found")
        
    if current_user.role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.id == db_fa.faculty_id).first()
        if not fac or fac.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of scope")
            
    for key, value in fa.model_dump(exclude_unset=True).items():
        setattr(db_fa, key, value)
    db.commit()
    db.refresh(db_fa)
    return db_fa

@router.delete("/{fa_id}")
def delete_faculty_availability(
    fa_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        
    db_fa = db.query(FacultyAvailability).filter(FacultyAvailability.id == fa_id).first()
    if not db_fa:
        raise HTTPException(status_code=404, detail="Faculty availability not found")
        
    if current_user.role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.id == db_fa.faculty_id).first()
        if not fac or fac.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of scope")
            
    db.delete(db_fa)
    db.commit()
    return {"ok": True}
