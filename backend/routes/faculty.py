from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List

from backend.database import get_db
from backend.models.academic import Faculty
from backend.models.identity import User
from backend.schemas.faculty import FacultyCreate, FacultyUpdate, FacultyResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/faculty", tags=["Faculty"])


def _to_response(fac: Faculty) -> FacultyResponse:
    """Convert a Faculty ORM object to FacultyResponse, populating the joined User name."""
    resp = FacultyResponse.model_validate(fac)
    if fac.user:
        resp.name = fac.user.name
    return resp


@router.get("/", response_model=List[FacultyResponse])
def get_faculty_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Faculty).options(joinedload(Faculty.user))
    if current_user.role == "ADMIN":
        rows = q.all()
    elif current_user.role == "FACULTY":
        rows = q.filter(Faculty.department_id == current_user.department_id).all()
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return [_to_response(f) for f in rows]

@router.get("/{faculty_id}", response_model=FacultyResponse)
def get_faculty(
    faculty_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fac = db.query(Faculty).options(joinedload(Faculty.user)).filter(Faculty.id == faculty_id).first()
    if not fac:
        raise HTTPException(status_code=404, detail="Faculty not found")
    if current_user.role == "ADMIN":
        return _to_response(fac)
    elif current_user.role == "FACULTY":
        if fac.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return _to_response(fac)
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
    # Re-fetch with joined user for the response
    db_fac = db.query(Faculty).options(joinedload(Faculty.user)).filter(Faculty.id == db_fac.id).first()
    return _to_response(db_fac)

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
    db_fac = db.query(Faculty).options(joinedload(Faculty.user)).filter(Faculty.id == faculty_id).first()
    return _to_response(db_fac)

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
