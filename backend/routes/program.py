from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import csv
import io

from backend.database import get_db
from backend.models.academic import Program
from backend.models.identity import User
from backend.schemas.program import ProgramCreate, ProgramUpdate, ProgramResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/programs", tags=["Programs"])


@router.get("/", response_model=List[ProgramResponse])
def get_programs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "ADMIN":
        return db.query(Program).all()
    elif current_user.role == "FACULTY":
        # Faculty can see programs of their own department
        return db.query(Program).filter(Program.department_id == current_user.department_id).all()
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.get("/{program_id}", response_model=ProgramResponse)
def get_program(
    program_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prog = db.query(Program).filter(Program.id == program_id).first()
    if not prog:
        raise HTTPException(status_code=404, detail="Program not found")
    if current_user.role == "ADMIN":
        return prog
    elif current_user.role == "FACULTY":
        if prog.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return prog
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("/", response_model=ProgramResponse)
def create_program(
    program: ProgramCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_prog = Program(**program.model_dump())
    db.add(db_prog)
    db.commit()
    db.refresh(db_prog)
    return db_prog


@router.put("/{program_id}", response_model=ProgramResponse)
def update_program(
    program_id: int,
    program: ProgramUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_prog = db.query(Program).filter(Program.id == program_id).first()
    if not db_prog:
        raise HTTPException(status_code=404, detail="Program not found")
    for key, value in program.model_dump(exclude_unset=True).items():
        setattr(db_prog, key, value)
    db.commit()
    db.refresh(db_prog)
    return db_prog


@router.delete("/{program_id}")
def delete_program(
    program_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_prog = db.query(Program).filter(Program.id == program_id).first()
    if not db_prog:
        raise HTTPException(status_code=404, detail="Program not found")
    db.delete(db_prog)
    db.commit()
    return {"ok": True}


# CSV import endpoints
@router.post("/import")
def import_programs_preview(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))

    valid_rows = []
    errors = []

    required_cols = {"department_id", "program_name", "degree", "duration"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must contain at least columns: {required_cols}")

    for idx, row in enumerate(reader, start=2):
        row_errors = []
        dept_id = row.get("department_id", "").strip()
        prog_name = row.get("program_name", "").strip()
        degree = row.get("degree", "").strip()
        dur = row.get("duration", "").strip()

        if not dept_id:
            row_errors.append("Missing department_id")
        else:
            try:
                int(dept_id)
            except ValueError:
                row_errors.append("department_id must be integer")
        if not prog_name:
            row_errors.append("Missing program_name")
        if not degree:
            row_errors.append("Missing degree")
        if not dur:
            row_errors.append("Missing duration")
        else:
            try:
                int(dur)
                if int(dur) <= 0:
                    row_errors.append("duration must be positive")
            except ValueError:
                row_errors.append("duration must be integer")

        if row_errors:
            errors.append({"row": idx, "errors": row_errors})
        else:
            valid_rows.append({
                "department_id": int(dept_id),
                "program_name": prog_name,
                "degree": degree,
                "duration": int(dur)
            })

    return {"valid_rows": valid_rows, "errors": errors}


@router.post("/import/confirm")
def import_programs_confirm(rows: List[ProgramCreate], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    inserted = []
    for row in rows:
        db_prog = Program(**row.model_dump())
        db.add(db_prog)
        inserted.append(db_prog)
    db.commit()
    return {"message": f"Successfully imported {len(inserted)} programs"}