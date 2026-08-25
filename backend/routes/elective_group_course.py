from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.courses import ElectiveGroupCourse, ElectiveGroup
from backend.models.identity import User
from backend.schemas.courses import ElectiveGroupCourseCreate, ElectiveGroupCourseUpdate, ElectiveGroupCourseResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/elective-group-courses", tags=["Elective Group Courses"])

@router.get("/", response_model=List[ElectiveGroupCourseResponse])
def get_elective_group_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(ElectiveGroupCourse).all()
    elif current_user.role in ["FACULTY", "STUDENT"]:
        return db.query(ElectiveGroupCourse).join(ElectiveGroup).filter(ElectiveGroup.department_id == current_user.department_id).all()
    return []

@router.get("/{egc_id}", response_model=ElectiveGroupCourseResponse)
def get_elective_group_course(
    egc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    egc = db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.id == egc_id).first()
    if not egc:
        raise HTTPException(status_code=404, detail="Elective Group Course not found")
    if current_user.role == "ADMIN":
        return egc
    elif current_user.role in ["FACULTY", "STUDENT"]:
        eg = db.query(ElectiveGroup).filter(ElectiveGroup.id == egc.group_id).first()
        if not eg or eg.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return egc
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.post("/", response_model=ElectiveGroupCourseResponse)
def create_elective_group_course(
    egc: ElectiveGroupCourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_egc = ElectiveGroupCourse(**egc.model_dump())
    db.add(db_egc)
    db.commit()
    db.refresh(db_egc)
    return db_egc

@router.put("/{egc_id}", response_model=ElectiveGroupCourseResponse)
def update_elective_group_course(
    egc_id: int,
    egc: ElectiveGroupCourseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_egc = db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.id == egc_id).first()
    if not db_egc:
        raise HTTPException(status_code=404, detail="Elective Group Course not found")
    for key, value in egc.model_dump(exclude_unset=True).items():
        setattr(db_egc, key, value)
    db.commit()
    db.refresh(db_egc)
    return db_egc

@router.delete("/{egc_id}")
def delete_elective_group_course(
    egc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_egc = db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.id == egc_id).first()
    if not db_egc:
        raise HTTPException(status_code=404, detail="Elective Group Course not found")
    db.delete(db_egc)
    db.commit()
    return {"ok": True}
