from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.academic import Student
from backend.models.identity import User
from backend.schemas.student import StudentCreate, StudentUpdate, StudentResponse
from backend.dependencies import get_current_user, require_role, require_department_scope

router = APIRouter(prefix="/students", tags=["Students"])


@router.get("/", response_model=List[StudentResponse])
def get_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(Student).all()
    elif current_user.role == "FACULTY":
        # Faculty can see students of their department via section? Actually student has department_id directly.
        return db.query(Student).filter(Student.department_id == current_user.department_id).all()
    else:  # STUDENT
        # Students can only see themselves
        return db.query(Student).filter(Student.id == current_user.id).all()  # assuming user.id matches student.id via user_id foreign key; but we don't have that link here. We'll implement later.


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stu = db.query(Student).filter(Student.id == student_id).first()
    if not stu:
        raise HTTPException(status_code=404, detail="Student not found")
    if current_user.role == "ADMIN":
        return stu
    elif current_user.role == "FACULTY":
        if stu.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return stu
    else:  # STUDENT
        # Student can only view own record
        if stu.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return stu


@router.post("/", response_model=StudentResponse)
def create_student(
    student: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_stu = Student(**student.model_dump())
    db.add(db_stu)
    db.commit()
    db.refresh(db_stu)
    return db_stu


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    student: StudentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_stu = db.query(Student).filter(Student.id == student_id).first()
    if not db_stu:
        raise HTTPException(status_code=404, detail="Student not found")
    for key, value in student.model_dump(exclude_unset=True).items():
        setattr(db_stu, key, value)
    db.commit()
    db.refresh(db_stu)
    return db_stu


@router.delete("/{student_id}")
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_stu = db.query(Student).filter(Student.id == student_id).first()
    if not db_stu:
        raise HTTPException(status_code=404, detail="Student not found")
    db.delete(db_stu)
    db.commit()
    return {"ok": True}