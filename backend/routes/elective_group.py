from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.courses import ElectiveGroup
from backend.models.identity import User
from backend.schemas.courses import ElectiveGroupCreate, ElectiveGroupUpdate, ElectiveGroupResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/elective-groups", tags=["Elective Groups"])

@router.get("/", response_model=List[ElectiveGroupResponse])
def get_elective_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(ElectiveGroup).all()
    elif current_user.role in ["FACULTY", "STUDENT"]:
        return db.query(ElectiveGroup).filter(ElectiveGroup.department_id == current_user.department_id).all()
    return []

@router.get("/{group_id}", response_model=ElectiveGroupResponse)
def get_elective_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eg = db.query(ElectiveGroup).filter(ElectiveGroup.id == group_id).first()
    if not eg:
        raise HTTPException(status_code=404, detail="Elective Group not found")
    if current_user.role == "ADMIN":
        return eg
    elif current_user.role in ["FACULTY", "STUDENT"]:
        if eg.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return eg
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.post("/", response_model=ElectiveGroupResponse)
def create_elective_group(
    group: ElectiveGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_eg = ElectiveGroup(**group.model_dump())
    db.add(db_eg)
    db.commit()
    db.refresh(db_eg)
    return db_eg

@router.put("/{group_id}", response_model=ElectiveGroupResponse)
def update_elective_group(
    group_id: int,
    group: ElectiveGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_eg = db.query(ElectiveGroup).filter(ElectiveGroup.id == group_id).first()
    if not db_eg:
        raise HTTPException(status_code=404, detail="Elective Group not found")
    for key, value in group.model_dump(exclude_unset=True).items():
        setattr(db_eg, key, value)
    db.commit()
    db.refresh(db_eg)
    return db_eg

@router.delete("/{group_id}")
def delete_elective_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_eg = db.query(ElectiveGroup).filter(ElectiveGroup.id == group_id).first()
    if not db_eg:
        raise HTTPException(status_code=404, detail="Elective Group not found")
    db.delete(db_eg)
    db.commit()
    return {"ok": True}
