"""
backend/routes/search.py
------------------------
Role-aware Global Search endpoint across authorized academic and campus entities.
Enforces strict RBAC scoping:
- ADMIN / SUPER_ADMIN: Students, Faculty, Departments, Programs, Courses, Rooms, Labs
- FACULTY: Authorized Students (assigned sections/courses), Faculty, Departments, Courses, Rooms, Labs
- STUDENT: Faculty (public academic info only), Departments, Courses, Rooms, Labs (never other students' private info)
"""

from __future__ import annotations

from typing import List, Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.academic import Department, Faculty, Program, Section, Student
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.space_time import Lab, Room

router = APIRouter(prefix="/search", tags=["Global Search"])

SearchEntityType = Literal["student", "faculty", "department", "program", "course", "room", "lab"]


class GlobalSearchResultItem(BaseModel):
    id: int
    entity_type: SearchEntityType
    title: str
    subtitle: str
    route: str


class GlobalSearchResponse(BaseModel):
    query: str
    total: int
    results: List[GlobalSearchResultItem]


def _role_route(role: str, entity_type: SearchEntityType) -> str:
    if role == "SUPER_ADMIN":
        mapping = {
            "department": "/super-admin/curriculum",
            "program": "/super-admin/curriculum",
            "course": "/super-admin/curriculum",
            "faculty": "/super-admin",
            "student": "/super-admin",
            "room": "/super-admin",
            "lab": "/super-admin",
        }
        return mapping.get(entity_type, "/super-admin")
    if role == "ADMIN":
        mapping = {
            "student": "/admin/people/students",
            "faculty": "/admin/people/faculty",
            "department": "/admin/academic/departments",
            "program": "/admin/academic/programs",
            "course": "/admin/courses",
            "room": "/admin/campus/rooms",
            "lab": "/admin/campus/rooms",
        }
        return mapping.get(entity_type, "/admin")
    if role == "FACULTY":
        mapping = {
            "student": "/faculty/dept-timetable",
            "faculty": "/faculty/dept-timetable",
            "department": "/faculty/dept-timetable",
            "program": "/faculty/dept-timetable",
            "course": "/faculty/timetable",
            "room": "/faculty/resources",
            "lab": "/faculty/resources",
        }
        return mapping.get(entity_type, "/faculty")
    # STUDENT
    mapping = {
        "faculty": "/student/timetable",
        "department": "/student/courses",
        "program": "/student/courses",
        "course": "/student/courses",
        "room": "/student/timetable",
        "lab": "/student/timetable",
        "student": "/student",
    }
    return mapping.get(entity_type, "/student")


@router.get("", response_model=GlobalSearchResponse, summary="Role-aware global search")
def global_search(
    q: str = Query(..., min_length=2, max_length=100, description="Search query string"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GlobalSearchResponse:
    clean_q = q.strip()
    if len(clean_q) < 2:
        return GlobalSearchResponse(query=clean_q, total=0, results=[])

    pattern = f"%{clean_q}%"
    role = current_user.role
    per_cat = max(3, min(6, limit // 3))
    results: List[GlobalSearchResultItem] = []

    # 1. Students (ADMIN, SUPER_ADMIN, or FACULTY scoped to assigned sections)
    if role in ("ADMIN", "SUPER_ADMIN"):
        students = (
            db.query(Student)
            .join(User, Student.user_id == User.id)
            .filter(or_(User.name.ilike(pattern), Student.student_id.ilike(pattern), User.email.ilike(pattern)))
            .limit(per_cat)
            .all()
        )
        for s in students:
            sec_name = s.section.section_name if s.section else "Unassigned"
            results.append(
                GlobalSearchResultItem(
                    id=s.id,
                    entity_type="student",
                    title=(s.user.name if s.user else None) or s.student_id or "Student",
                    subtitle=f"Student · {s.student_id} · Section {sec_name}",
                    route=_role_route(role, "student"),
                )
            )
    elif role == "FACULTY":
        fac = db.query(Faculty).filter(Faculty.user_id == current_user.id).first()
        if fac:
            assigned_sec_ids = [
                ca.section_id
                for ca in db.query(CourseAssignment.section_id)
                .filter(CourseAssignment.faculty_id == fac.id, CourseAssignment.section_id.isnot(None))
                .distinct()
                .all()
            ]
            if assigned_sec_ids:
                students = (
                    db.query(Student)
                    .join(User, Student.user_id == User.id)
                    .filter(
                        Student.section_id.in_(assigned_sec_ids),
                        or_(User.name.ilike(pattern), Student.student_id.ilike(pattern)),
                    )
                    .limit(per_cat)
                    .all()
                )
                for s in students:
                    sec_name = s.section.section_name if s.section else "Section"
                    results.append(
                        GlobalSearchResultItem(
                            id=s.id,
                            entity_type="student",
                            title=(s.user.name if s.user else None) or s.student_id or "Student",
                            subtitle=f"Assigned Student · {s.student_id} · {sec_name}",
                            route=_role_route(role, "student"),
                        )
                    )

    # 2. Faculty (All authenticated roles, never leaking private phone numbers)
    faculties = (
        db.query(Faculty)
        .join(User, Faculty.user_id == User.id)
        .filter(
            or_(
                User.name.ilike(pattern),
                Faculty.faculty_id.ilike(pattern),
                Faculty.designation.ilike(pattern),
            )
        )
        .limit(per_cat)
        .all()
    )
    for f in faculties:
        dept_name = f.department.name if f.department else "Faculty"
        results.append(
            GlobalSearchResultItem(
                id=f.id,
                entity_type="faculty",
                title=(f.user.name if f.user else None) or f.faculty_id or "Faculty",
                subtitle=f"Faculty · {f.designation or 'Faculty Member'} · {dept_name}",
                route=_role_route(role, "faculty"),
            )
        )

    # 3. Courses
    courses = (
        db.query(Course)
        .filter(or_(Course.course_code.ilike(pattern), Course.course_name.ilike(pattern)))
        .limit(per_cat)
        .all()
    )
    for c in courses:
        results.append(
            GlobalSearchResultItem(
                id=c.id,
                entity_type="course",
                title=f"{c.course_code} — {c.course_name}",
                subtitle=f"Course · {c.course_type or 'THEORY'} · {c.credits or 0} Credits",
                route=_role_route(role, "course"),
            )
        )

    # 4. Departments & Programs (Programs only for Admin / Super Admin)
    depts = (
        db.query(Department)
        .filter(or_(Department.name.ilike(pattern), Department.department_code.ilike(pattern)))
        .limit(per_cat)
        .all()
    )
    for d in depts:
        results.append(
            GlobalSearchResultItem(
                id=d.id,
                entity_type="department",
                title=d.name,
                subtitle=f"Department · {d.department_code}",
                route=_role_route(role, "department"),
            )
        )

    if role in ("ADMIN", "SUPER_ADMIN"):
        progs = (
            db.query(Program)
            .filter(Program.program_name.ilike(pattern))
            .limit(per_cat)
            .all()
        )
        for p in progs:
            results.append(
                GlobalSearchResultItem(
                    id=p.id,
                    entity_type="program",
                    title=p.program_name or f"Program #{p.id}",
                    subtitle="Academic Program",
                    route=_role_route(role, "program"),
                )
            )

    # 5. Rooms & Labs
    rooms = (
        db.query(Room)
        .filter(or_(Room.room_number.ilike(pattern), Room.room_type.ilike(pattern)))
        .limit(per_cat)
        .all()
    )
    for rm in rooms:
        bld_name = rm.building.name if rm.building else "Campus"
        results.append(
            GlobalSearchResultItem(
                id=rm.id,
                entity_type="room",
                title=f"Room {rm.room_number}",
                subtitle=f"{rm.room_type or 'ROOM'} · {bld_name} · Cap {rm.capacity or 'N/A'}",
                route=_role_route(role, "room"),
            )
        )

    labs = (
        db.query(Lab)
        .filter(Lab.lab_name.ilike(pattern))
        .limit(per_cat)
        .all()
    )
    for lb in labs:
        results.append(
            GlobalSearchResultItem(
                id=lb.id,
                entity_type="lab",
                title=lb.lab_name or f"Lab #{lb.id}",
                subtitle="Laboratory",
                route=_role_route(role, "lab"),
            )
        )

    trimmed = results[:limit]
    return GlobalSearchResponse(query=clean_q, total=len(trimmed), results=trimmed)
