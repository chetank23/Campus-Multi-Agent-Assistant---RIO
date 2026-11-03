from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.academic import AcademicYear
from backend.models.identity import User
from backend.schemas.academic_year import AcademicYearCreate, AcademicYearUpdate, AcademicYearResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/academic-years", tags=["Academic Years"])


@router.get("", include_in_schema=False)
@router.get("/", response_model=List[AcademicYearResponse])
def get_academic_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Allow all authenticated users to list
    return db.query(AcademicYear).all()


@router.get("/{year_id}", response_model=AcademicYearResponse)
def get_academic_year(
    year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    yr = db.query(AcademicYear).filter(AcademicYear.id == year_id).first()
    if not yr:
        raise HTTPException(status_code=404, detail="Academic year not found")
    # Allow all authenticated users to view
    return yr


@router.post("/", response_model=AcademicYearResponse)
def create_academic_year(
    year: AcademicYearCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_yr = AcademicYear(**year.model_dump())
    db.add(db_yr)
    db.commit()
    db.refresh(db_yr)
    return db_yr


@router.put("/{year_id}", response_model=AcademicYearResponse)
def update_academic_year(
    year_id: int,
    year: AcademicYearUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_yr = db.query(AcademicYear).filter(AcademicYear.id == year_id).first()
    if not db_yr:
        raise HTTPException(status_code=404, detail="Academic year not found")
    for key, value in year.model_dump(exclude_unset=True).items():
        setattr(db_yr, key, value)
    db.commit()
    db.refresh(db_yr)
    return db_yr


@router.delete("/{year_id}")
def delete_academic_year(
    year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_yr = db.query(AcademicYear).filter(AcademicYear.id == year_id).first()
    if not db_yr:
        raise HTTPException(status_code=404, detail="Academic year not found")
    db.delete(db_yr)
    db.commit()
    return {"ok": True}