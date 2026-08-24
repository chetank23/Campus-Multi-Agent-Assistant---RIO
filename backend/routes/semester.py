from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.academic import Semester
from backend.models.identity import User
from backend.schemas.semester import SemesterCreate, SemesterUpdate, SemesterResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/semesters", tags=["Semesters"])


@router.get("/", response_model=List[SemesterResponse])
def get_semesters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Allow all authenticated users to list
    return db.query(Semester).all()


@router.get("/{semester_id}", response_model=SemesterResponse)
def get_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sem = db.query(Semester).filter(Semester.id == semester_id).first()
    if not sem:
        raise HTTPException(status_code=404, detail="Semester not found")
    # Allow all authenticated users to view
    return sem


@router.post("/", response_model=SemesterResponse)
def create_semester(
    semester: SemesterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_sem = Semester(**semester.model_dump())
    db.add(db_sem)
    db.commit()
    db.refresh(db_sem)
    return db_sem


@router.put("/{semester_id}", response_model=SemesterResponse)
def update_semester(
    semester_id: int,
    semester: SemesterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_sem = db.query(Semester).filter(Semester.id == semester_id).first()
    if not db_sem:
        raise HTTPException(status_code=404, detail="Semester not found")
    for key, value in semester.model_dump(exclude_unset=True).items():
        setattr(db_sem, key, value)
    db.commit()
    db.refresh(db_sem)
    return db_sem


@router.delete("/{semester_id}")
def delete_semester(
    semester_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_sem = db.query(Semester).filter(Semester.id == semester_id).first()
    if not db_sem:
        raise HTTPException(status_code=404, detail="Semester not found")
    db.delete(db_sem)
    db.commit()
    return {"ok": True}