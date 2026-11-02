"""
backend/routes/data_import.py
-----------------------------
Transactional Data Import & Pre-commit Validation engine for RIO-MJP.
Supports previewing, row-level error reporting, duplicate checking, foreign-key
verification, and explicit Admin confirmation.
Restricted to ADMIN role.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import require_role
from backend.models.academic import Department, Faculty, Section, Student
from backend.models.courses import Course
from backend.models.identity import User
from backend.models.space_time import Building, Room
from backend.models.workflow import AuditLog

router = APIRouter(prefix="/admin/import", tags=["Data Import & Validation"])

EntityType = Literal["rooms", "courses", "faculty", "students"]


class ImportPreviewRequest(BaseModel):
    entity_type: EntityType
    rows: List[Dict[str, Any]] = Field(..., min_length=1, max_length=500)


class RowError(BaseModel):
    row_index: int
    field: str
    message: str


class ImportPreviewResponse(BaseModel):
    entity_type: EntityType
    total_rows: int
    valid_rows_count: int
    invalid_rows_count: int
    errors: List[RowError]
    preview_data: List[Dict[str, Any]]


class ImportCommitRequest(BaseModel):
    entity_type: EntityType
    rows: List[Dict[str, Any]] = Field(..., min_length=1, max_length=500)


class ImportCommitResponse(BaseModel):
    success: bool
    entity_type: EntityType
    imported_count: int
    message: str


def _validate_import_rows(
    entity_type: EntityType,
    rows: List[Dict[str, Any]],
    db: Session,
) -> tuple[List[Dict[str, Any]], List[RowError]]:
    """
    Core validation engine for institutional import data rows.
    Validates missing fields, types, foreign key existence, payload uniqueness,
    and database conflict prevention.
    """
    errors: List[RowError] = []
    valid_rows: List[Dict[str, Any]] = []

    # Cache foreign keys for performance
    buildings_cache = {b.id: b for b in db.query(Building).all()}
    departments_cache = {d.id: d for d in db.query(Department).all()}
    sections_cache = {s.id: s for s in db.query(Section).all()}

    # Track duplicates within incoming payload
    seen_identifiers = set()

    for idx, row in enumerate(rows):
        row_has_error = False

        if entity_type == "rooms":
            room_num = str(row.get("room_number", "")).strip()
            bld_id = row.get("building_id")
            cap = row.get("capacity")
            rtype = str(row.get("room_type", "CLASSROOM")).strip().upper()

            if not room_num:
                errors.append(RowError(row_index=idx, field="room_number", message="Room number is required."))
                row_has_error = True
            elif room_num in seen_identifiers:
                errors.append(RowError(row_index=idx, field="room_number", message=f"Duplicate room '{room_num}' in payload."))
                row_has_error = True
            else:
                existing = db.query(Room).filter(Room.room_number.ilike(room_num)).first()
                if existing:
                    errors.append(RowError(row_index=idx, field="room_number", message=f"Room '{room_num}' already exists in database."))
                    row_has_error = True
                seen_identifiers.add(room_num)

            try:
                bld_id_int = int(bld_id)
                if bld_id_int not in buildings_cache:
                    errors.append(RowError(row_index=idx, field="building_id", message=f"Building ID #{bld_id_int} does not exist."))
                    row_has_error = True
            except (ValueError, TypeError):
                errors.append(RowError(row_index=idx, field="building_id", message="Valid integer building_id is required."))
                row_has_error = True

            try:
                cap_int = int(cap)
                if cap_int <= 0:
                    errors.append(RowError(row_index=idx, field="capacity", message="Capacity must be greater than zero."))
                    row_has_error = True
            except (ValueError, TypeError):
                errors.append(RowError(row_index=idx, field="capacity", message="Valid positive integer capacity is required."))
                row_has_error = True

            if rtype not in ("CLASSROOM", "LAB", "SEMINAR_HALL", "AUDITORIUM"):
                errors.append(RowError(row_index=idx, field="room_type", message="room_type must be CLASSROOM, LAB, SEMINAR_HALL, or AUDITORIUM."))
                row_has_error = True

            if not row_has_error:
                valid_rows.append({
                    "room_number": room_num,
                    "building_id": int(bld_id),
                    "capacity": int(cap),
                    "room_type": rtype,
                })

        elif entity_type == "courses":
            code = str(row.get("course_code", "")).strip().upper()
            name = str(row.get("course_name", "")).strip()
            dept_id = row.get("department_id")
            ctype = str(row.get("course_type", "THEORY")).strip().upper()
            credits_val = row.get("credits", 3)

            if not code:
                errors.append(RowError(row_index=idx, field="course_code", message="Course code is required."))
                row_has_error = True
            elif code in seen_identifiers:
                errors.append(RowError(row_index=idx, field="course_code", message=f"Duplicate course code '{code}' in payload."))
                row_has_error = True
            else:
                existing = db.query(Course).filter(Course.course_code == code).first()
                if existing:
                    errors.append(RowError(row_index=idx, field="course_code", message=f"Course '{code}' already exists in database."))
                    row_has_error = True
                seen_identifiers.add(code)

            if not name:
                errors.append(RowError(row_index=idx, field="course_name", message="Course name is required."))
                row_has_error = True

            try:
                dept_id_int = int(dept_id)
                if dept_id_int not in departments_cache:
                    errors.append(RowError(row_index=idx, field="department_id", message=f"Department ID #{dept_id_int} does not exist."))
                    row_has_error = True
            except (ValueError, TypeError):
                errors.append(RowError(row_index=idx, field="department_id", message="Valid integer department_id is required."))
                row_has_error = True

            if ctype not in ("THEORY", "LAB", "INTEGRATED", "ELECTIVE"):
                errors.append(RowError(row_index=idx, field="course_type", message="course_type must be THEORY, LAB, INTEGRATED, or ELECTIVE."))
                row_has_error = True

            if not row_has_error:
                valid_rows.append({
                    "course_code": code,
                    "course_name": name,
                    "department_id": int(dept_id),
                    "course_type": ctype,
                    "credits": int(credits_val) if str(credits_val).isdigit() else 3,
                })

        elif entity_type == "faculty":
            fid = str(row.get("faculty_id", "")).strip().upper()
            name = str(row.get("name", "")).strip()
            email = str(row.get("email", "")).strip().lower()
            dept_id = row.get("department_id")
            desig = str(row.get("designation", "Assistant Professor")).strip()

            if not fid:
                errors.append(RowError(row_index=idx, field="faculty_id", message="Faculty ID is required."))
                row_has_error = True
            elif fid in seen_identifiers:
                errors.append(RowError(row_index=idx, field="faculty_id", message=f"Duplicate faculty ID '{fid}' in payload."))
                row_has_error = True
            else:
                existing = db.query(Faculty).filter(Faculty.faculty_id == fid).first()
                if existing:
                    errors.append(RowError(row_index=idx, field="faculty_id", message=f"Faculty ID '{fid}' already exists."))
                    row_has_error = True
                seen_identifiers.add(fid)

            if not name:
                errors.append(RowError(row_index=idx, field="name", message="Faculty name is required."))
                row_has_error = True

            if not email or "@" not in email:
                errors.append(RowError(row_index=idx, field="email", message="Valid email is required."))
                row_has_error = True
            else:
                u_exist = db.query(User).filter(User.email == email).first()
                if u_exist:
                    errors.append(RowError(row_index=idx, field="email", message=f"Email '{email}' is already registered."))
                    row_has_error = True

            try:
                dept_id_int = int(dept_id)
                if dept_id_int not in departments_cache:
                    errors.append(RowError(row_index=idx, field="department_id", message=f"Department #{dept_id_int} does not exist."))
                    row_has_error = True
            except (ValueError, TypeError):
                errors.append(RowError(row_index=idx, field="department_id", message="Valid integer department_id is required."))
                row_has_error = True

            if not row_has_error:
                valid_rows.append({
                    "faculty_id": fid,
                    "name": name,
                    "email": email,
                    "department_id": int(dept_id),
                    "designation": desig,
                })

        elif entity_type == "students":
            sid = str(row.get("student_id", "")).strip().upper()
            name = str(row.get("name", "")).strip()
            email = str(row.get("email", "")).strip().lower()
            dept_id = row.get("department_id")
            sec_id = row.get("section_id")

            if not sid:
                errors.append(RowError(row_index=idx, field="student_id", message="Student ID is required."))
                row_has_error = True
            elif sid in seen_identifiers:
                errors.append(RowError(row_index=idx, field="student_id", message=f"Duplicate student ID '{sid}' in payload."))
                row_has_error = True
            else:
                s_exist = db.query(Student).filter(Student.student_id == sid).first()
                if s_exist:
                    errors.append(RowError(row_index=idx, field="student_id", message=f"Student ID '{sid}' already exists."))
                    row_has_error = True
                seen_identifiers.add(sid)

            if not name:
                errors.append(RowError(row_index=idx, field="name", message="Student name is required."))
                row_has_error = True

            if not email or "@" not in email:
                errors.append(RowError(row_index=idx, field="email", message="Valid email is required."))
                row_has_error = True
            else:
                u_exist = db.query(User).filter(User.email == email).first()
                if u_exist:
                    errors.append(RowError(row_index=idx, field="email", message=f"Email '{email}' is already registered."))
                    row_has_error = True

            try:
                dept_id_int = int(dept_id)
                if dept_id_int not in departments_cache:
                    errors.append(RowError(row_index=idx, field="department_id", message=f"Department #{dept_id_int} does not exist."))
                    row_has_error = True
            except (ValueError, TypeError):
                errors.append(RowError(row_index=idx, field="department_id", message="Valid integer department_id is required."))
                row_has_error = True

            try:
                sec_id_int = int(sec_id)
                if sec_id_int not in sections_cache:
                    errors.append(RowError(row_index=idx, field="section_id", message=f"Section #{sec_id_int} does not exist."))
                    row_has_error = True
            except (ValueError, TypeError):
                errors.append(RowError(row_index=idx, field="section_id", message="Valid integer section_id is required."))
                row_has_error = True

            if not row_has_error:
                valid_rows.append({
                    "student_id": sid,
                    "name": name,
                    "email": email,
                    "department_id": int(dept_id),
                    "section_id": int(sec_id),
                })

    return valid_rows, errors


@router.post("/preview", response_model=ImportPreviewResponse)
def preview_import(
    body: ImportPreviewRequest,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Validates institutional data rows before commit.
    Checks missing fields, type constraints, foreign key validity, and database duplicates.
    """
    valid_rows, errors = _validate_import_rows(body.entity_type, body.rows, db)

    return ImportPreviewResponse(
        entity_type=body.entity_type,
        total_rows=len(body.rows),
        valid_rows_count=len(valid_rows),
        invalid_rows_count=len(errors),
        errors=errors,
        preview_data=valid_rows[:15],
    )


@router.post("/commit", response_model=ImportCommitResponse)
def commit_import(
    body: ImportCommitRequest,
    admin_user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Executes explicit Admin commit of validated institutional records in an atomic transaction.
    Re-validates rows to ensure integrity and prevents altered/invalid payloads.
    """
    valid_rows, errors = _validate_import_rows(body.entity_type, body.rows, db)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot commit import: {len(errors)} validation error(s) found in payload. Row {errors[0].row_index}: {errors[0].message}",
        )

    from backend.core.security import get_password_hash

    count = 0
    try:
        if body.entity_type == "rooms":
            for r in valid_rows:
                room = Room(
                    room_number=r["room_number"],
                    building_id=r["building_id"],
                    capacity=r["capacity"],
                    room_type=r["room_type"],
                )
                db.add(room)
                count += 1

        elif body.entity_type == "courses":
            for r in valid_rows:
                course = Course(
                    course_code=r["course_code"],
                    course_name=r["course_name"],
                    department_id=r["department_id"],
                    course_type=r["course_type"],
                    credits=r.get("credits", 3),
                )
                db.add(course)
                count += 1

        elif body.entity_type == "faculty":
            for r in valid_rows:
                # 1. Create User
                user = User(
                    name=r["name"],
                    email=r["email"],
                    password_hash=get_password_hash("Test@1234"),
                    role="FACULTY",
                    department_id=r["department_id"],
                    is_active=True,
                )
                db.add(user)
                db.flush()

                # 2. Create Faculty
                fac = Faculty(
                    faculty_id=r["faculty_id"],
                    user_id=user.id,
                    department_id=r["department_id"],
                    designation=r.get("designation", "Assistant Professor"),
                )
                db.add(fac)
                count += 1

        elif body.entity_type == "students":
            for r in valid_rows:
                # 1. Create User
                user = User(
                    name=r["name"],
                    email=r["email"],
                    password_hash=get_password_hash("Test@1234"),
                    role="STUDENT",
                    department_id=r["department_id"],
                    is_active=True,
                )
                db.add(user)
                db.flush()

                # 2. Create Student
                stu = Student(
                    student_id=r["student_id"],
                    user_id=user.id,
                    department_id=r["department_id"],
                    section_id=r["section_id"],
                )
                db.add(stu)
                count += 1

        # Audit Log
        db.add(
            AuditLog(
                user_id=admin_user.id,
                action="DATA_IMPORTED",
                entity_type=body.entity_type.upper(),
                entity_id=0,
                new_value={"imported_count": count},
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import failed during commit: {str(e)}",
        )

    return ImportCommitResponse(
        success=True,
        entity_type=body.entity_type,
        imported_count=count,
        message=f"Successfully imported {count} {body.entity_type} records.",
    )

    return ImportCommitResponse(
        success=True,
        entity_type=body.entity_type,
        imported_count=count,
        message=f"Successfully imported {count} {body.entity_type} records.",
    )
