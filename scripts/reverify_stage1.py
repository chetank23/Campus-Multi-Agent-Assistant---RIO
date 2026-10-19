"""
scripts/reverify_stage1.py
Full Stage 1 reverification — checks every requirement from the blueprint.
Run with:  venv\\Scripts\\python scripts\\reverify_stage1.py
"""
import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

PASS = "  [PASS]"
FAIL = "  [FAIL]"
results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((condition, label))
    suffix = f"  <- {detail}" if detail else ""
    print(f"{status}  {label}{suffix}")
    return condition

print()
print("=" * 65)
print("  STAGE 1 — FULL REVERIFICATION")
print("=" * 65)

# ── 1. DIRECTORY STRUCTURE ────────────────────────────────────────
print("\n[1] DIRECTORY STRUCTURE")
required_dirs = [
    "backend/models", "backend/routes", "backend/schemas",
    "backend/services", "backend/middleware", "backend/utils",
    "agents/supervisor", "agents/query_agent", "agents/scheduling_agent",
    "agents/resource_agent", "agents/state", "agents/tools",
    "optimizer", "database/migrations/versions", "database/seeds",
    "data/raw", "data/processed", "data/sample",
    "frontend/src/pages/student", "frontend/src/pages/faculty",
    "frontend/src/pages/hod", "frontend/src/pages/coordinator",
    "frontend/src/pages/admin", "frontend/src/components",
    "frontend/src/layouts", "frontend/src/services",
    "tests/api", "tests/agents", "tests/optimizer",
    "tests/database", "tests/integration",
    "docs/architecture", "docs/database", "docs/api",
    "scripts",
]
for d in required_dirs:
    check(f"dir: {d}", (ROOT / d).is_dir())

# ── 2. KEY FILES ──────────────────────────────────────────────────
print("\n[2] KEY FILES")
required_files = [
    ".env", ".env.example", "requirements.txt", "README.md", "alembic.ini",
    "database/schema.sql", "database/seed.sql",
    "database/migrations/env.py",
    "backend/config.py", "backend/main.py",
    "backend/dependencies.py", "backend/celery_app.py",
    "backend/models/__init__.py", "backend/models/base.py",
    "backend/models/identity.py", "backend/models/academic.py",
    "backend/models/courses.py", "backend/models/space_time.py",
    "backend/models/timetable.py", "backend/models/resources.py",
    "backend/models/workflow.py",
    "scripts/verify_stage1.py",
]
for f in required_files:
    check(f"file: {f}", (ROOT / f).is_file())

# ── 3. VENV & PACKAGES ────────────────────────────────────────────
print("\n[3] PYTHON VENV & PACKAGES")
venv_python = ROOT / "venv" / "Scripts" / "python.exe"
check("venv exists", venv_python.is_file())

try:
    import sqlalchemy
    check("sqlalchemy >= 2.0", int(sqlalchemy.__version__.split(".")[0]) >= 2,
          sqlalchemy.__version__)
except ImportError:
    check("sqlalchemy installed", False)

try:
    import alembic
    check("alembic installed", True, alembic.__version__)
except ImportError:
    check("alembic installed", False)

try:
    import psycopg
    check("psycopg v3 installed", int(psycopg.__version__.split(".")[0]) >= 3,
          psycopg.__version__)
except ImportError:
    check("psycopg installed", False)

try:
    import dotenv
    check("python-dotenv installed", True)
except ImportError:
    check("python-dotenv installed", False)

try:
    import pydantic
    check("pydantic >= 2.0", int(pydantic.__version__.split(".")[0]) >= 2,
          pydantic.__version__)
except ImportError:
    check("pydantic installed", False)

# ── 4. MODEL IMPORTS ──────────────────────────────────────────────
print("\n[4] SQLALCHEMY MODEL IMPORTS")
sys.path.insert(0, str(ROOT))
try:
    from backend.models import (
        metadata, User, Department, Program, AcademicYear, Semester,
        Section, Batch, Student, Faculty, Course, CourseAssignment,
        ElectiveGroup, ElectiveGroupCourse, Building, Room, Lab,
        TimeSlot, FacultyAvailability, AcademicCalendar,
        TimetableVersion, TimetableEntry, Resource, ResourceBooking,
        ChangeRequest, Notification, AuditLog,
    )
    registered = list(metadata.tables.keys())
    expected_tables = [
        "users", "departments", "programs", "academic_years", "semesters",
        "sections", "batches", "students", "faculty", "courses",
        "course_assignments", "elective_groups", "elective_group_courses",
        "buildings", "rooms", "labs", "time_slots", "faculty_availability",
        "academic_calendar", "timetable_versions", "timetable_entries",
        "resources", "resource_bookings", "change_requests",
        "notifications", "audit_logs",
    ]
    check("all 26 models import cleanly", True)
    for t in expected_tables:
        check(f"model registered: {t}", t in registered)
except Exception as e:
    check("models import", False, str(e)[:80])

# ── 5. .ENV & DATABASE URL ────────────────────────────────────────
print("\n[5] .ENV CONFIGURATION")
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
db_url = os.environ.get("DATABASE_URL", "")
check("DATABASE_URL set", bool(db_url))
check("uses psycopg v3 driver (postgresql+psycopg://)",
      db_url.startswith("postgresql+psycopg://"))
check("points to campus_ai", "campus_ai" in db_url)
check("uses campus_user", "campus_user" in db_url)
check("SECRET_KEY present", bool(os.environ.get("SECRET_KEY")))
check("ENV=development", os.environ.get("ENV") == "development")

# ── 6. DATABASE CONNECTION ────────────────────────────────────────
print("\n[6] DATABASE CONNECTION")
try:
    from sqlalchemy import create_engine, text, inspect
    engine = create_engine(db_url, pool_pre_ping=True)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT current_database(), current_user, version()"
        )).fetchone()
        assert row is not None
        check("connects successfully", True)
        check("connected to campus_ai", row[0] == "campus_ai", f"got: {row[0]}")
        check("connected as campus_user", row[1] == "campus_user", f"got: {row[1]}")
        check("PostgreSQL 18", "PostgreSQL 18" in row[2], row[2][:40])
except Exception as e:
    check("database connection", False, str(e)[:80])
    print("\n  Cannot continue DB checks without a connection.")
    sys.exit(1)

# ── 7. TABLES ─────────────────────────────────────────────────────
print("\n[7] TABLES IN DATABASE")
with engine.connect() as conn:
    tables_in_db = {
        r[0] for r in conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        ).fetchall()
    }
    expected_db_tables = [
        "users", "departments", "programs", "academic_years", "semesters",
        "sections", "batches", "students", "faculty", "courses",
        "course_assignments", "elective_groups", "elective_group_courses",
        "buildings", "rooms", "labs", "time_slots", "faculty_availability",
        "academic_calendar", "timetable_versions", "timetable_entries",
        "resources", "resource_bookings", "change_requests",
        "notifications", "audit_logs", "alembic_version",
    ]
    check(f"total tables = 27", len(tables_in_db) == 27, f"found {len(tables_in_db)}")
    for t in expected_db_tables:
        check(f"table exists: {t}", t in tables_in_db)

# ── 8. FOREIGN KEYS ───────────────────────────────────────────────
print("\n[8] FOREIGN KEYS")
with engine.connect() as conn:
    fk_count = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE constraint_type='FOREIGN KEY' AND table_schema='public'"
    )).scalar()
    check(f"foreign key count = 51", fk_count == 51, f"found {fk_count}")

    # Verify specific critical FKs
    critical_fks = [
        ("users", "department_id", "departments"),
        ("faculty", "user_id", "users"),
        ("students", "section_id", "sections"),
        ("timetable_entries", "faculty_id", "faculty"),
        ("timetable_entries", "room_id", "rooms"),
        ("timetable_entries", "slot_id", "time_slots"),
        ("timetable_entries", "section_id", "sections"),
        ("timetable_entries", "version_id", "timetable_versions"),
        ("audit_logs", "user_id", "users"),
    ]
    fk_rows = conn.execute(text("""
        SELECT tc.table_name, kcu.column_name, ccu.table_name AS ref_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'
    """)).fetchall()
    fk_set = {(r[0], r[1], r[2]) for r in fk_rows}
    for tbl, col, ref in critical_fks:
        check(f"FK {tbl}.{col} -> {ref}", (tbl, col, ref) in fk_set)

# ── 9. CHECK CONSTRAINTS ──────────────────────────────────────────
print("\n[9] CHECK CONSTRAINTS")
with engine.connect() as conn:
    ck_count = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE constraint_type='CHECK' AND table_schema='public'"
    )).scalar()
    check(f"CHECK constraint count >= 8", ck_count >= 8, f"found {ck_count}")

    # Verify critical CHECK constraints exist by name
    ck_names = {r[0] for r in conn.execute(text(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE constraint_type='CHECK' AND table_schema='public'"
    )).fetchall()}
    critical_checks = [
        "ck_users_role",
        "ck_courses_course_type",
        "ck_rooms_room_type",
        "ck_time_slots_slot_type",
        "ck_fa_availability",
        "ck_tv_status",
        "ck_te_status",
        "ck_rb_status",
        "ck_cr_request_type",
        "ck_resources_resource_type",
        "ck_ac_event_type",
    ]
    for ck in critical_checks:
        check(f"CHECK constraint: {ck}", ck in ck_names)

# ── 10. COMPOSITE INDEXES ─────────────────────────────────────────
print("\n[10] COMPOSITE INDEXES ON timetable_entries")
with engine.connect() as conn:
    idx_rows = conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE tablename='timetable_entries' AND schemaname='public'"
    )).fetchall()
    idx_map = {r[0]: r[1] for r in idx_rows}

    check("ix_timetable_entries_faculty_slot exists",
          "ix_timetable_entries_faculty_slot" in idx_map)
    check("  -> btree(faculty_id, slot_id)",
          "faculty_id, slot_id" in idx_map.get("ix_timetable_entries_faculty_slot",""))

    check("ix_timetable_entries_room_slot exists",
          "ix_timetable_entries_room_slot" in idx_map)
    check("  -> btree(room_id, slot_id)",
          "room_id, slot_id" in idx_map.get("ix_timetable_entries_room_slot",""))

    check("ix_timetable_entries_section_slot exists",
          "ix_timetable_entries_section_slot" in idx_map)
    check("  -> btree(section_id, slot_id)",
          "section_id, slot_id" in idx_map.get("ix_timetable_entries_section_slot",""))

# ── 11. ALEMBIC MIGRATION TRACKING ───────────────────────────────
print("\n[11] ALEMBIC MIGRATION")
with engine.connect() as conn:
    ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    check("alembic_version table exists", ver is not None)
    check("migration applied (revision present)", bool(ver), f"rev: {ver}")

    # Confirm alembic.ini script_location is correct
    ini_path = ROOT / "alembic.ini"
    ini_content = ini_path.read_text()
    check("alembic.ini script_location set", "database/migrations" in ini_content)

    # Confirm env.py reads from .env
    env_py = (ROOT / "database/migrations/env.py").read_text()
    check("env.py loads from .env", "load_dotenv" in env_py)
    check("env.py uses target_metadata from models", "target_metadata" in env_py)
    check("env.py reads DATABASE_URL from environ", 'DATABASE_URL' in env_py)

# ── 12. SCHEMA.SQL ────────────────────────────────────────────────
print("\n[12] database/schema.sql")
schema_sql = (ROOT / "database/schema.sql").read_text()
for keyword in [
    "CREATE TABLE users", "CREATE TABLE departments",
    "CREATE TABLE timetable_entries", "CREATE TABLE audit_logs",
    "ix_timetable_entries_faculty_slot", "ix_timetable_entries_room_slot",
    "ix_timetable_entries_section_slot", "REFERENCES", "CHECK",
]:
    check(f"schema.sql contains: {keyword}", keyword in schema_sql)

# ── SUMMARY ───────────────────────────────────────────────────────
total = len(results)
passed = sum(1 for ok, _ in results if ok)
failed = total - passed

print()
print("=" * 65)
print(f"  STAGE 1 REVERIFICATION SUMMARY")
print("=" * 65)
print(f"  Total checks : {total}")
print(f"  Passed       : {passed}")
print(f"  Failed       : {failed}")
print()

if failed == 0:
    print("  ALL CHECKS PASSED — Stage 1 is complete and correct.")
else:
    print("  FAILURES:")
    for ok, label in results:
        if not ok:
            print(f"    [FAIL] {label}")
print()
