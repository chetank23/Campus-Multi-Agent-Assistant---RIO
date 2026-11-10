"""
agents/tools/semantic_query_planner.py
--------------------------------------
Safe, backend-owned semantic database query planning and execution layer.
Enables NVIDIA Nemotron to answer open-ended, previously unseen queries via
structured query plans without ever generating or executing arbitrary SQL.

Validates:
1. Target logical entity against approved registry.
2. Requested fields and aggregation functions against entity schema.
3. Operators, filter types, and join paths.
4. Mandatory role-based scope injections (RLS/ownership) that model cannot override.
5. Max limit enforcement (1 to 100 rows).
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple, Type
from sqlalchemy import func, distinct, and_, or_, desc, asc
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.academic import Department, Program, AcademicYear, Semester, Section, Student, Faculty, Batch
from backend.models.courses import Course, CourseAssignment, ElectiveGroup
from backend.models.space_time import Building, Room, TimeSlot, FacultyAvailability
from backend.models.timetable import Timetable, TimetableEntry, TimetableVersion
from backend.models.workflow import AuditLog, ChangeRequest, Notification

# Approved Semantic Entities Map
ENTITY_MODELS: Dict[str, Any] = {
    "users": User,
    "students": Student,
    "faculty": Faculty,
    "departments": Department,
    "programs": Program,
    "sections": Section,
    "batches": Batch,
    "courses": Course,
    "course_assignments": CourseAssignment,
    "buildings": Building,
    "rooms": Room,
    "time_slots": TimeSlot,
    "faculty_availability": FacultyAvailability,
    "timetables": Timetable,
    "timetable_entries": TimetableEntry,
    "academic_years": AcademicYear,
    "semesters": Semester,
    "notifications": Notification,
    "audit_logs": AuditLog,
}

# Approved Fields per Entity
ENTITY_FIELDS: Dict[str, Dict[str, Any]] = {
    "users": {
        "id": User.id,
        "name": User.name,
        "email": User.email,
        "role": User.role,
        "department_id": User.department_id,
    },
    "students": {
        "id": Student.id,
        "student_id": Student.student_id,
        "usn": Student.student_id,
        "name": User.name,
        "email": User.email,
        "user_id": Student.user_id,
        "department_id": Student.department_id,
        "program_id": Student.program_id,
        "section_id": Student.section_id,
        "batch_id": Student.batch_id,
        "semester_id": Student.semester_id,
    },
    "faculty": {
        "id": Faculty.id,
        "faculty_id": Faculty.faculty_id,
        "name": User.name,
        "email": User.email,
        "user_id": Faculty.user_id,
        "department_id": Faculty.department_id,
        "designation": Faculty.designation,
        "specialization": Faculty.specialization,
        "contact_number": Faculty.contact_number,
        "max_weekly_load": Faculty.max_weekly_load,
    },
    "departments": {
        "id": Department.id,
        "department_code": Department.department_code,
        "name": Department.name,
    },
    "programs": {
        "id": Program.id,
        "program_name": Program.program_name,
        "department_id": Program.department_id,
        "degree": Program.degree,
        "duration": Program.duration,
    },
    "sections": {
        "id": Section.id,
        "section_name": Section.section_name,
        "department_id": Section.department_id,
        "program_id": Section.program_id,
        "student_count": Section.student_count,
        "semester_id": Section.semester_id,
        "class_teacher_id": Section.class_teacher_id,
    },
    "batches": {
        "id": Batch.id,
        "batch_name": Batch.batch_name,
        "section_id": Batch.section_id,
        "student_count": Batch.student_count,
    },
    "courses": {
        "id": Course.id,
        "course_code": Course.course_code,
        "course_name": Course.course_name,
        "course_type": Course.course_type,
        "credits": Course.credits,
        "department_id": Course.department_id,
        "lecture_hours": Course.lecture_hours,
        "tutorial_hours": Course.tutorial_hours,
        "practical_hours": Course.practical_hours,
        "requires_lab": Course.requires_lab,
    },
    "course_assignments": {
        "id": CourseAssignment.id,
        "course_id": CourseAssignment.course_id,
        "faculty_id": CourseAssignment.faculty_id,
        "section_id": CourseAssignment.section_id,
        "batch_id": CourseAssignment.batch_id,
    },
    "buildings": {
        "id": Building.id,
        "code": Building.code,
        "name": Building.name,
        "number_of_floors": Building.number_of_floors,
        "location": Building.location,
    },
    "rooms": {
        "id": Room.id,
        "room_number": Room.room_number,
        "building_id": Room.building_id,
        "floor_number": Room.floor_number,
        "room_type": Room.room_type,
        "capacity": Room.capacity,
        "department_id": Room.department_id,
        "has_projector": Room.has_projector,
        "has_smart_board": Room.has_smart_board,
        "status": Room.status,
    },
    "time_slots": {
        "id": TimeSlot.id,
        "day": TimeSlot.day,
        "start_time": TimeSlot.start_time,
        "end_time": TimeSlot.end_time,
        "slot_type": TimeSlot.slot_type,
    },
    "faculty_availability": {
        "id": FacultyAvailability.id,
        "faculty_id": FacultyAvailability.faculty_id,
        "slot_id": FacultyAvailability.slot_id,
        "availability": FacultyAvailability.availability,
        "preference": FacultyAvailability.preference,
    },
    "timetables": {
        "id": Timetable.id,
        "academic_year_id": Timetable.academic_year_id,
        "semester_id": Timetable.semester_id,
        "section_id": Timetable.section_id,
        "status": Timetable.status,
        "working_days": Timetable.working_days,
        "created_at": Timetable.created_at,
        "published_at": Timetable.published_at,
    },
    "timetable_entries": {
        "id": TimetableEntry.id,
        "timetable_id": TimetableEntry.timetable_id,
        "version_id": TimetableEntry.version_id,
        "department_id": TimetableEntry.department_id,
        "program_id": TimetableEntry.program_id,
        "semester_id": TimetableEntry.semester_id,
        "section_id": TimetableEntry.section_id,
        "batch_id": TimetableEntry.batch_id,
        "course_id": TimetableEntry.course_id,
        "faculty_id": TimetableEntry.faculty_id,
        "room_id": TimetableEntry.room_id,
        "slot_id": TimetableEntry.slot_id,
        "status": TimetableEntry.status,
    },
    "academic_years": {
        "id": AcademicYear.id,
        "name": AcademicYear.name,
        "start_date": AcademicYear.start_date,
        "end_date": AcademicYear.end_date,
    },
    "semesters": {
        "id": Semester.id,
        "semester_number": Semester.semester_number,
        "academic_year_id": Semester.academic_year_id,
        "start_date": Semester.start_date,
        "end_date": Semester.end_date,
    },
    "notifications": {
        "id": Notification.id,
        "user_id": Notification.user_id,
        "title": Notification.title,
        "message": Notification.message,
        "type": Notification.type,
        "is_read": Notification.is_read,
        "created_at": Notification.created_at,
    },
    "audit_logs": {
        "id": AuditLog.id,
        "action": AuditLog.action,
        "entity_type": AuditLog.entity_type,
        "entity_id": AuditLog.entity_id,
        "user_id": AuditLog.user_id,
        "timestamp": AuditLog.timestamp,
    },
}

SUPPORTED_OPERATORS = ["==", "!=", ">", ">=", "<", "<=", "like", "ilike", "in"]

DAY_NAME_TO_CODE = {
    "MONDAY": "MON",
    "TUESDAY": "TUE",
    "WEDNESDAY": "WED",
    "THURSDAY": "THU",
    "FRIDAY": "FRI",
    "SATURDAY": "SAT",
    "SUNDAY": "SUN",
}
DAY_CODE_TO_NAME = {v: k for k, v in DAY_NAME_TO_CODE.items()}


def execute_semantic_query_plan(
    db: Session,
    user: User,
    entity: str,
    fields: Optional[List[str]] = None,
    aggregations: Optional[List[Dict[str, str]]] = None,
    filters: Optional[List[Dict[str, Any]]] = None,
    group_by: Optional[List[str]] = None,
    order_by: Optional[List[Dict[str, str]]] = None,
    joins: Optional[List[str]] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """
    Safely executes a dynamic semantic query plan produced by NVIDIA Nemotron.
    Applies strict validation, compiles to SQLAlchemy, and injects mandatory RBAC filters.
    """
    clean_entity = entity.strip().lower()
    if clean_entity not in ENTITY_MODELS:
        return {
            "error": f"Invalid query entity '{clean_entity}'. Approved entities are: {list(ENTITY_MODELS.keys())}"
        }

    # 1. Role-based Entity Authorization Guard
    if user.role in ("STUDENT", "FACULTY") and clean_entity == "audit_logs":
        return {
            "error": "Access denied: Audit logs require administrative authorization."
        }

    model = ENTITY_MODELS[clean_entity]
    entity_field_map = ENTITY_FIELDS[clean_entity]

    # Clamp limit safely
    clamped_limit = max(1, min(100, limit))

    # 2. Build Selection Columns
    select_items = []
    output_headers = []

    # Aggregations: e.g. [{"func": "COUNT", "field": "*", "alias": "total_count"}]
    if aggregations:
        for agg in aggregations:
            f_name = agg.get("func", "COUNT").upper()
            target_f = agg.get("field", "*").lower()
            alias_name = agg.get("alias") or f"{f_name.lower()}_{target_f.replace('*', 'all')}"

            col_attr = None
            if target_f != "*":
                if target_f not in entity_field_map:
                    return {"error": f"Field '{target_f}' not recognized on entity '{clean_entity}'."}
                col_attr = entity_field_map[target_f]

            if f_name == "COUNT":
                col_expr = func.count(col_attr if col_attr is not None else getattr(model, "id", 1))
            elif f_name == "SUM" and col_attr is not None:
                col_expr = func.sum(col_attr)
            elif f_name == "AVG" and col_attr is not None:
                col_expr = func.avg(col_attr)
            elif f_name == "MIN" and col_attr is not None:
                col_expr = func.min(col_attr)
            elif f_name == "MAX" and col_attr is not None:
                col_expr = func.max(col_attr)
            elif f_name == "DISTINCT" and col_attr is not None:
                col_expr = distinct(col_attr)
            else:
                return {"error": f"Unsupported aggregation function '{f_name}' on '{target_f}'."}

            select_items.append(col_expr.label(alias_name))
            output_headers.append(alias_name)

    # Regular fields
    if fields:
        for f in fields:
            f_clean = f.strip().lower()
            if f_clean not in entity_field_map:
                return {"error": f"Field '{f_clean}' is not an approved field on '{clean_entity}'."}
            col_attr = entity_field_map[f_clean]
            select_items.append(col_attr.label(f_clean))
            output_headers.append(f_clean)

    # Default to all entity fields if neither fields nor aggregations specified
    if not select_items:
        for f_name, col_attr in entity_field_map.items():
            select_items.append(col_attr.label(f_name))
            output_headers.append(f_name)

    query = db.query(*select_items).select_from(model)

    # 3. Apply Joins if requested
    joined_models = set()
    if joins:
        for j in joins:
            j_clean = j.strip().lower()
            if j_clean not in ENTITY_MODELS:
                continue
            j_model = ENTITY_MODELS[j_clean]
            if j_model not in joined_models:
                query = query.join(j_model)
                joined_models.add(j_model)

    # Auto-join User if name/email is selected or filtered on students or faculty
    if clean_entity in ("students", "faculty") and User not in joined_models:
        user_cols = {User.name, User.email}
        needs_user = False
        if not fields and not aggregations:
            needs_user = True
        elif fields:
            needs_user = any(entity_field_map.get(f.strip().lower()) in user_cols for f in fields)
        if filters and not needs_user:
            needs_user = any(entity_field_map.get(filt.get("field", "").strip().lower()) in user_cols for filt in filters)
        if order_by and not needs_user:
            needs_user = any(entity_field_map.get(ob.get("field", "").strip().lower()) in user_cols for ob in order_by)
        if needs_user:
            query = query.join(User, getattr(model, "user_id") == User.id)
            joined_models.add(User)

    # 4. Mandatory Security & Scope Filtering (Cannot be overridden by model plan)
    where_clauses = []

    if user.role == "STUDENT":
        if clean_entity == "students":
            where_clauses.append(Student.user_id == user.id)
        elif clean_entity == "notifications":
            where_clauses.append(Notification.user_id == user.id)
        elif clean_entity in ("timetables", "timetable_entries"):
            where_clauses.append(Timetable.status == "PUBLISHED")
            stu = db.query(Student).filter(Student.user_id == user.id).first()
            if stu and stu.section_id and clean_entity == "timetable_entries":
                where_clauses.append(TimetableEntry.section_id == stu.section_id)
        elif clean_entity in ("audit_logs", "faculty_availability"):
            return {"error": f"Access denied: Students are not authorized to query entity '{clean_entity}'."}
    elif user.role == "FACULTY":
        if clean_entity == "notifications":
            where_clauses.append(Notification.user_id == user.id)
        elif clean_entity in ("timetables", "timetable_entries"):
            where_clauses.append(Timetable.status == "PUBLISHED")
        elif clean_entity == "students":
            fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
            if fac:
                ca_sec_ids = [ca[0] for ca in db.query(CourseAssignment.section_id).filter(CourseAssignment.faculty_id == fac.id).all() if ca[0]]
                te_sec_ids = [te[0] for te in db.query(TimetableEntry.section_id).filter(TimetableEntry.faculty_id == fac.id).all() if te[0]]
                ct_sec_ids = [sec.id for sec in db.query(Section).filter(Section.class_teacher_id == fac.id).all()]
                assigned_sec_ids = list(set(ca_sec_ids + te_sec_ids + ct_sec_ids))
                if assigned_sec_ids:
                    where_clauses.append(Student.section_id.in_(assigned_sec_ids))
                else:
                    where_clauses.append(Student.id == -1)
            else:
                where_clauses.append(Student.id == -1)
        elif clean_entity == "course_assignments":
            fac = db.query(Faculty).filter(Faculty.user_id == user.id).first()
            if fac:
                where_clauses.append(CourseAssignment.faculty_id == fac.id)
            else:
                where_clauses.append(CourseAssignment.id == -1)
        elif clean_entity == "audit_logs":
            return {"error": "Access denied: Audit logs require administrative authorization."}
    elif user.role == "ADMIN":
        if user.department_id:
            if clean_entity in ("students", "faculty", "sections", "courses"):
                dept_col = getattr(model, "department_id", None)
                if dept_col is not None:
                    where_clauses.append(dept_col == user.department_id)

    # 5. Model Filters Validation & Compilation
    if filters:
        for filt in filters:
            f_name = filt.get("field", "").strip().lower()
            op = filt.get("op", "==").strip()
            val = filt.get("value")

            if f_name not in entity_field_map:
                return {"error": f"Filter field '{f_name}' is not recognized on entity '{clean_entity}'."}
            if op not in SUPPORTED_OPERATORS:
                return {"error": f"Filter operator '{op}' is not supported. Use: {SUPPORTED_OPERATORS}"}

            col = entity_field_map[f_name]

            # Day code normalization for day filters
            if f_name == "day" and isinstance(val, str):
                v_clean = val.strip().upper()
                c3 = DAY_NAME_TO_CODE.get(v_clean, v_clean[:3])
                c_full = DAY_CODE_TO_NAME.get(c3, v_clean)
                if op == "==":
                    where_clauses.append(or_(col == c3, col == c_full))
                elif op == "!=":
                    where_clauses.append(and_(col != c3, col != c_full))
                elif op == "in" and isinstance(val, (list, tuple)):
                    expanded_days = []
                    for item in val:
                        s_item = str(item).strip().upper()
                        expanded_days.extend([DAY_NAME_TO_CODE.get(s_item, s_item[:3]), DAY_CODE_TO_NAME.get(s_item, s_item)])
                    where_clauses.append(col.in_(list(set(expanded_days))))
                else:
                    where_clauses.append(col == val)
            elif op == "==":
                where_clauses.append(col == val)
            elif op == "!=":
                where_clauses.append(col != val)
            elif op == ">":
                where_clauses.append(col > val)
            elif op == ">=":
                where_clauses.append(col >= val)
            elif op == "<":
                where_clauses.append(col < val)
            elif op == "<=":
                where_clauses.append(col <= val)
            elif op in ("like", "ilike"):
                where_clauses.append(col.ilike(f"%{val}%"))
            elif op == "in" and isinstance(val, (list, tuple)):
                where_clauses.append(col.in_(val))

    if where_clauses:
        query = query.filter(and_(*where_clauses))

    # 6. Group By
    if group_by:
        group_cols = []
        for g in group_by:
            g_clean = g.strip().lower()
            if g_clean not in entity_field_map:
                return {"error": f"Group by field '{g_clean}' not recognized on entity '{clean_entity}'."}
            group_cols.append(entity_field_map[g_clean])
        if group_cols:
            query = query.group_by(*group_cols)

    # 7. Order By
    if order_by:
        for ob in order_by:
            f_name = ob.get("field", "").strip().lower()
            direction = ob.get("direction", "ASC").upper()
            if f_name in entity_field_map:
                col = entity_field_map[f_name]
                query = query.order_by(desc(col) if direction == "DESC" else asc(col))

    query = query.limit(clamped_limit)

    # 8. Execution
    rows = query.all()

    # 9. Format Results
    results = []
    for r in rows:
        if hasattr(r, "_asdict"):
            r_dict = r._asdict()
        elif hasattr(r, "__dict__"):
            r_dict = {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
        elif isinstance(r, (tuple, list)):
            r_dict = {output_headers[i]: r[i] for i in range(len(output_headers))}
        else:
            r_dict = {output_headers[0]: r} if output_headers else {"result": str(r)}

        # Sanitize any dates/datetimes to ISO strings
        clean_row = {}
        for k, v in r_dict.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                clean_row[k] = v.isoformat()
            else:
                clean_row[k] = v
        results.append(clean_row)

    return {
        "success": True,
        "entity": clean_entity,
        "total_returned": len(results),
        "columns": output_headers,
        "records": results,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": f"PostgreSQL Master Registry ({clean_entity})",
    }
