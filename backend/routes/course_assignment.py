from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.courses import CourseAssignment, Course
from backend.models.identity import User
from backend.schemas.courses import CourseAssignmentCreate, CourseAssignmentUpdate, CourseAssignmentResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/course-assignments", tags=["Course Assignments"])

@router.get("/", response_model=List[CourseAssignmentResponse])
def get_course_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(CourseAssignment).all()
    elif current_user.role in ["FACULTY", "STUDENT"]:
        # Complex scoping: they can see assignments for courses in their department
        return db.query(CourseAssignment).join(Course).filter(Course.department_id == current_user.department_id).all()
    return []

@router.get("/{assignment_id}", response_model=CourseAssignmentResponse)
def get_course_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ca = db.query(CourseAssignment).filter(CourseAssignment.id == assignment_id).first()
    if not ca:
        raise HTTPException(status_code=404, detail="Course Assignment not found")
    if current_user.role == "ADMIN":
        return ca
    elif current_user.role in ["FACULTY", "STUDENT"]:
        course = db.query(Course).filter(Course.id == ca.course_id).first()
        if not course or course.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return ca
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

@router.post("/", response_model=CourseAssignmentResponse)
def create_course_assignment(
    assignment: CourseAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_ca = CourseAssignment(**assignment.model_dump())
    db.add(db_ca)
    db.commit()
    db.refresh(db_ca)
    return db_ca

@router.put("/{assignment_id}", response_model=CourseAssignmentResponse)
def update_course_assignment(
    assignment_id: int,
    assignment: CourseAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_ca = db.query(CourseAssignment).filter(CourseAssignment.id == assignment_id).first()
    if not db_ca:
        raise HTTPException(status_code=404, detail="Course Assignment not found")
    for key, value in assignment.model_dump(exclude_unset=True).items():
        setattr(db_ca, key, value)
    db.commit()
    db.refresh(db_ca)
    return db_ca

@router.delete("/{assignment_id}")
def delete_course_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_ca = db.query(CourseAssignment).filter(CourseAssignment.id == assignment_id).first()
    if not db_ca:
        raise HTTPException(status_code=404, detail="Course Assignment not found")
    db.delete(db_ca)
    db.commit()
    return {"ok": True}
