from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.academic import Faculty
from backend.models.identity import User
from backend.schemas.faculty import FacultyCreate, FacultyUpdate, FacultyResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/faculty", tags=["Faculty"])

@router.get("/", response_model=List[FacultyResponse])
def get_faculty_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(Faculty).all()
    elif current_user.role == "FACULTY":
        return db.query(Faculty).filter(Faculty.department_id == current_user.department_id).all()
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.get("/{faculty_id}", response_model=FacultyResponse)
def get_faculty(
    faculty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fac = db.query(Faculty).filter(Faculty.id == faculty_id).first()
    if not fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    if current_user.role == "ADMIN":
        return fac
    elif current_user.role == "FACULTY":
        if fac.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return fac
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.post("/", response_model=FacultyResponse)
def create_faculty(
    faculty: FacultyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_fac = Faculty(**faculty.model_dump())
    db.add(db_fac)
    db.commit()
    db.refresh(db_fac)
    return db_fac

@router.put("/{faculty_id}", response_model=FacultyResponse)
def update_faculty(
    faculty_id: int,
    faculty: FacultyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_fac = db.query(Faculty).filter(Faculty.id == faculty_id).first()
    if not db_fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    for key, value in faculty.model_dump(exclude_unset=True).items():
        setattr(db_fac, key, value)
    db.commit()
    db.refresh(db_fac)
    return db_fac

@router.delete("/{faculty_id}")
def delete_faculty(
    faculty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_fac = db.query(Faculty).filter(Faculty.id == faculty_id).first()
    if not db_fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    db.delete(db_fac)
    db.commit()
    return {"ok": True}
