from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import csv
import io

from backend.database import get_db
from backend.models.academic import Department
from backend.models.identity import User
from backend.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from backend.dependencies import get_current_user, require_role, require_department_scope

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=List[DepartmentResponse], include_in_schema=False)
@router.get("/", response_model=List[DepartmentResponse])
def get_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only admin can list all departments
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return db.query(Department).all()


@router.get("/{department_id}", response_model=DepartmentResponse)
def get_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    # Faculty can view own department; Admin can view any; Student cannot
    if current_user.role == "FACULTY":
        if current_user.department_id != department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
    elif current_user.role == "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    # ADMIN passes
    return dept


@router.post("/", response_model=DepartmentResponse)
def create_department(
    department: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_dept = Department(**department.model_dump())
    db.add(db_dept)
    db.commit()
    db.refresh(db_dept)
    return db_dept


@router.put("/{department_id}", response_model=DepartmentResponse)
def update_department(
    department_id: int,
    department: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_dept = db.query(Department).filter(Department.id == department_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    for key, value in department.model_dump(exclude_unset=True).items():
        setattr(db_dept, key, value)
    db.commit()
    db.refresh(db_dept)
    return db_dept


@router.delete("/{department_id}")
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_dept = db.query(Department).filter(Department.id == department_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(db_dept)
    db.commit()
    return {"ok": True}


# CSV import endpoints similar to building/room
@router.post("/import")
def import_departments_preview(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))

    valid_rows = []
    errors = []

    required_cols = {"department_code", "name"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must contain at least columns: {required_cols}")

    for idx, row in enumerate(reader, start=2):
        row_errors = []
        dept_code = row.get("department_code", "").strip()
        name = row.get("name", "").strip()

        if not dept_code:
            row_errors.append("Missing department_code")
        if not name:
            row_errors.append("Missing name")

        if row_errors:
            errors.append({"row": idx, "errors": row_errors})
        else:
            valid_rows.append({
                "department_code": dept_code,
                "name": name
            })

    return {"valid_rows": valid_rows, "errors": errors}


@router.post("/import/confirm")
def import_departments_confirm(rows: List[DepartmentCreate], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    inserted = []
    for row in rows:
        db_dept = Department(**row.model_dump())
        db.add(db_dept)
        inserted.append(db_dept)
    db.commit()
    return {"message": f"Successfully imported {len(inserted)} departments"}