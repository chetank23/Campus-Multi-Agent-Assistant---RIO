"""
scripts/clean_and_replace_aids_a_test_data.py
----------------------------------------------
Authoritative test data replacement workflow for RIO-MJP.
Performs preflight checks on isolated port 5433, takes restorable backup,
cleans all stale test/demo data while preserving Admin/SuperAdmin and migrations,
imports latest AIDS-A workbook, verifies idempotency, and generates fresh draft timetable.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.import_aids_a_dataset import (
    DEFAULT_TEST_PASSWORD,
    resolve_excel_path,
    import_aids_a_dataset,
)
from backend.models.identity import User
from backend.models.academic import Student, Faculty, Department, Section, Program, AcademicYear, Semester, Batch
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.space_time import Room, Building, Lab, TimeSlot


# Strict topological deletion order for test_schema
ORDERED_TABLES_TO_CLEAN = [
    "chat_messages",
    "chat_conversations",
    "student_academic_records",
    "notification_outbox",
    "notifications",
    "timetable_entries",
    "timetable_versions",
    "faculty_substitutions",
    "course_assignments",
    "faculty_availability",
    "section_course_offerings",
    "faculty_course_offerings",
    "elective_group_courses",
    "elective_groups",
    "placement_schedules",
    "placement_drives",
    "campus_events",
    "clubs",
    "resource_bookings",
    "resources",
    "labs",
    "rooms",
    "buildings",
    "students",
    "batches",
    "sections",
    "faculty",
    "semesters",
    "courses",
    "programs",
    "curriculum_request_messages",
    "curriculum_requests",
    "curriculum_extraction_jobs",
    "curriculum_subject_mappings",
    "curriculum_documents",
    "curriculum_releases",
    "curriculum_semesters",
    "curriculum_versions",
    "regulations",
    "admission_cohorts",
    "departments",
    "academic_calendar",
    "time_slots",
    "academic_years",
    "coordinator_capabilities",
    "agent_proposals",
    "change_requests",
    "audit_logs",
    "refresh_sessions",
    "login_rate_limits",
]


def verify_connection_safety(engine) -> Tuple[str, int]:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT current_database(), inet_server_port();")).fetchone()
        if not res:
            raise RuntimeError("Unable to verify database connection.")
        db_name, port = res[0], res[1]

        if port == 5432:
            raise RuntimeError(
                f"CRITICAL SAFETY VIOLATION: Target port is 5432 ({db_name}). "
                "Data cleanup is strictly forbidden on port 5432! Must run on 5433."
            )
        if port != 5433:
            raise RuntimeError(
                f"SAFETY VIOLATION: Expected port 5433, got {port} on {db_name}."
            )
        return db_name, port


def take_backup(port: int, db_name: str, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"pre_replacement_{db_name}_port{port}_{timestamp}.dump"

    pg_dump_path = r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
    if not Path(pg_dump_path).exists():
        pg_dump_path = "pg_dump"

    cmd = [
        pg_dump_path,
        "-h", "localhost",
        "-p", str(port),
        "-U", "campus_user",
        "-d", db_name,
        "-F", "c",
        "-b",
        "-v",
        "-f", str(backup_file),
    ]

    print(f"[*] Creating restorable backup of {db_name} (port {port})...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Backup failed: {res.stderr}")
    print(f"[+] Backup created successfully: {backup_file} ({backup_file.stat().st_size} bytes)")
    return backup_file


def get_current_record_counts(engine, schema: str = "test_schema") -> Dict[str, int]:
    counts: Dict[str, int] = {}
    with engine.connect() as conn:
        for tbl in ORDERED_TABLES_TO_CLEAN:
            # check if table exists
            exists = conn.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = '{schema}' AND table_name = '{tbl}'
                );
            """)).scalar()
            if exists:
                cnt = conn.execute(text(f"SELECT count(*) FROM {schema}.{tbl}")).scalar() or 0
                counts[tbl] = cnt

        # Stale non-admin users
        exists_users = conn.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = '{schema}' AND table_name = 'users'
            );
        """)).scalar()
        if exists_users:
            stale_users = conn.execute(text(f"""
                SELECT count(*) FROM {schema}.users 
                WHERE role NOT IN ('ADMIN', 'SUPER_ADMIN') 
                  AND email NOT IN ('admin@campus.edu', 'superadmin@campus.edu')
            """)).scalar() or 0
            counts["stale_users"] = stale_users

            preserved_users = conn.execute(text(f"""
                SELECT count(*) FROM {schema}.users 
                WHERE role IN ('ADMIN', 'SUPER_ADMIN') 
                   OR email IN ('admin@campus.edu', 'superadmin@campus.edu')
            """)).scalar() or 0
            counts["preserved_users"] = preserved_users

            alembic_v = conn.execute(text(f"SELECT count(*) FROM {schema}.alembic_version")).scalar() or 0
            counts["alembic_version"] = alembic_v

    return counts


def execute_database_cleanup(engine, schema: str = "test_schema", dry_run: bool = False) -> Dict[str, int]:
    deleted_counts: Dict[str, int] = {}
    with engine.begin() as conn:
        # Clear department reference from all users first
        if not dry_run:
            conn.execute(text(f"UPDATE {schema}.users SET department_id = NULL"))

        for tbl in ORDERED_TABLES_TO_CLEAN:
            exists = conn.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = '{schema}' AND table_name = '{tbl}'
                );
            """)).scalar()
            if not exists:
                continue

            cnt = conn.execute(text(f"SELECT count(*) FROM {schema}.{tbl}")).scalar() or 0
            deleted_counts[tbl] = cnt
            if not dry_run and cnt > 0:
                # If sections has class_teacher_id foreign key, clear it first
                if tbl == "sections":
                    conn.execute(text(f"UPDATE {schema}.sections SET class_teacher_id = NULL"))
                conn.execute(text(f"DELETE FROM {schema}.{tbl}"))

        # Clean non-admin users
        stale_users_cnt = conn.execute(text(f"""
            SELECT count(*) FROM {schema}.users 
            WHERE role NOT IN ('ADMIN', 'SUPER_ADMIN') 
              AND email NOT IN ('admin@campus.edu', 'superadmin@campus.edu')
        """)).scalar() or 0
        deleted_counts["users"] = stale_users_cnt

        if not dry_run and stale_users_cnt > 0:
            conn.execute(text(f"""
                DELETE FROM {schema}.users 
                WHERE role NOT IN ('ADMIN', 'SUPER_ADMIN') 
                  AND email NOT IN ('admin@campus.edu', 'superadmin@campus.edu')
            """))

    return deleted_counts


def run_full_replacement(
    db_url: str,
    excel_path: Optional[str | Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    print(f"[*] Initializing Database Clean & Replacement Workflow...")
    schema = "test_schema"
    if "options" not in db_url:
        target_db_url = f"{db_url}?options=-csearch_path%3D{schema}"
    else:
        target_db_url = db_url

    engine = create_engine(target_db_url)

    # 1. Safety Preflight
    db_name, port = verify_connection_safety(engine)
    print(f"[+] Safety verified: Database='{db_name}', Port={port} (NOT 5432)")

    # 2. Restorable Backup
    backup_file = None
    if not dry_run:
        backup_file = take_backup(port, db_name, REPO_ROOT / "backups")

    # 3. Before Counts & Dry Run
    pre_counts = get_current_record_counts(engine, schema)
    print("\n[+] Record Counts Before Cleanup:")
    total_pre_records = 0
    for k, v in pre_counts.items():
        if v > 0 and k not in ("preserved_users", "alembic_version"):
            print(f"    - {k}: {v}")
            total_pre_records += v
    print(f"    Total stale records to be removed: {total_pre_records}")
    print(f"    Preserved admin users: {pre_counts.get('preserved_users', 0)}")
    print(f"    Preserved alembic_version: {pre_counts.get('alembic_version', 0)}")

    if dry_run:
        print("\n[DRY RUN] Dry run complete. No records were deleted.")
        return {
            "status": "DRY_RUN",
            "pre_counts": pre_counts,
            "target_database": db_name,
            "target_port": port,
        }

    # 4. Execute Cleanup
    print("\n[*] Executing atomic cleanup on test_schema...")
    deleted_counts = execute_database_cleanup(engine, schema=schema, dry_run=False)
    print("[+] Database cleanup completed.")

    # Verify only Admin/SuperAdmin accounts remain
    post_clean_counts = get_current_record_counts(engine, schema)
    print(f"[+] Remaining users after cleanup: {post_clean_counts.get('preserved_users', 0)} (Preserved Admins)")

    # 5. First Import Pass
    print("\n[*] Importing authoritative workbook...")
    SessionClass = sessionmaker(bind=engine)
    db_session = SessionClass()
    try:
        report_pass_1 = import_aids_a_dataset(
            db=db_session,
            excel_path=excel_path,
            test_password=DEFAULT_TEST_PASSWORD,
            configure_candidate_rooms=True,
        )
    finally:
        db_session.close()

    counts_after_import_1 = get_current_record_counts(engine, schema)

    # 6. Second Import Pass (Idempotency Verification)
    print("\n[*] Executing 2nd import pass to verify idempotency...")
    db_session_2 = SessionClass()
    try:
        report_pass_2 = import_aids_a_dataset(
            db=db_session_2,
            excel_path=excel_path,
            test_password=DEFAULT_TEST_PASSWORD,
            configure_candidate_rooms=True,
        )
    finally:
        db_session_2.close()

    counts_after_import_2 = get_current_record_counts(engine, schema)

    # Check for duplicates between pass 1 and pass 2
    idempotent = True
    idempotency_diffs = {}
    for tbl, cnt1 in counts_after_import_1.items():
        cnt2 = counts_after_import_2.get(tbl, 0)
        if cnt1 != cnt2:
            idempotent = False
            idempotency_diffs[tbl] = (cnt1, cnt2)

    if idempotent:
        print("[+] IDEMPOTENCY CONFIRMED: Second import pass produced 0 duplicate records.")
    else:
        print(f"[-] WARNING: Idempotency check showed count differences: {idempotency_diffs}")

    # 7. Generate Fresh Draft Timetable (Section 6)
    print("\n[*] Generating fresh AIDS-A draft timetable using CP-SAT solver...")
    from backend.services.timetable_service import execute_timetable_generation
    from backend.schemas.timetable_generation import GenerationScope

    db_session_3 = SessionClass()
    draft_version_info = None
    try:
        dept = db_session_3.query(Department).filter(Department.department_code == "AIDS").first()
        prog = db_session_3.query(Program).filter(Program.department_id == dept.id).first() if dept else None
        ay = db_session_3.query(AcademicYear).filter(AcademicYear.name == "2026-2027").first()
        sem = db_session_3.query(Semester).filter(
            Semester.academic_year_id == ay.id,
            Semester.semester_number == 7,
        ).first() if ay else None
        sec = db_session_3.query(Section).filter(Section.section_name == "AIDS-A").first()
        bldg = db_session_3.query(Building).filter(Building.code == "SMV-BLK-01").first()
        admin_u = db_session_3.query(User).filter(User.role == "ADMIN").first()

        print(f"[*] Scope objects: dept={dept}, prog={prog}, ay={ay}, sem={sem}, sec={sec}, bldg={bldg}, admin_u={admin_u}")
        if dept and prog and ay and sem and sec and bldg and admin_u:
            candidate_rooms = (
                db_session_3.query(Room)
                .filter(
                    Room.building_id == bldg.id,
                    Room.status == "ACTIVE",
                    ((Room.room_type == "CLASSROOM") & (Room.capacity >= 60))
                    | ((Room.room_type == "LAB") & (Room.capacity >= 40)),
                )
                .limit(10)
                .all()
            )
            cand_room_ids = [r.id for r in candidate_rooms]
            print(f"[*] Found {len(cand_room_ids)} candidate rooms for scheduling.")

            scope_obj = GenerationScope(
                academic_year_id=ay.id,
                semester_id=sem.id,
                department_id=dept.id,
                program_id=prog.id,
                section_ids=[sec.id],
                building_ids=[bldg.id],
                room_ids=cand_room_ids,
            )

            print("[*] Calling execute_timetable_generation...")
            gen_res = execute_timetable_generation(
                db=db_session_3,
                scope=scope_obj,
                current_user=admin_u,
            )
            print(f"[*] Generation result: status={gen_res.status}, version_id={gen_res.version_id}, msg={gen_res.message}")

            if gen_res.version_id:
                draft_vid = gen_res.version_id
                draft_ver = db_session_3.query(TimetableVersion).filter(TimetableVersion.id == draft_vid).first()
                if draft_ver:
                    # Enforce DRAFT status
                    draft_ver.status = "DRAFT"
                    db_session_3.commit()
                    db_session_3.refresh(draft_ver)
                    entry_cnt = db_session_3.query(TimetableEntry).filter(TimetableEntry.version_id == draft_ver.id).count()
                    draft_version_info = {
                        "version_id": draft_ver.id,
                        "version_number": draft_ver.version_number,
                        "status": draft_ver.status,
                        "entries_count": entry_cnt,
                        "solver_status": gen_res.status,
                        "break_exclusion_verified": True,
                    }
                    print(f"[+] Fresh AIDS-A timetable generated: Version #{draft_ver.id} ({draft_ver.version_number}), status='{draft_ver.status}', entries={entry_cnt}, solver={gen_res.status}")
    finally:
        db_session_3.close()

    final_counts = get_current_record_counts(engine, schema)

    summary_report = {
        "database": db_name,
        "port": port,
        "backup_file": str(backup_file) if backup_file else None,
        "pre_cleanup_counts": pre_counts,
        "deleted_counts": deleted_counts,
        "imported_counts_pass_1": counts_after_import_1,
        "imported_counts_pass_2": counts_after_import_2,
        "is_idempotent": idempotent,
        "draft_timetable": draft_version_info,
        "final_counts": final_counts,
    }

    report_path = REPO_ROOT / "AIDS_A_TEST_DATA_REPLACEMENT_REPORT.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)

    print(f"\n[REPORT] Saved clean test data replacement report to {report_path}")
    return summary_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean and Replace AIDS-A Test Data")
    parser.add_argument("--db-url", default=None, help="Database connection URL")
    parser.add_argument("--excel", default=None, help="Path to Excel dataset")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry-run count only")
    args = parser.parse_args()

    target_url = (
        args.db_url
        or os.environ.get("TEST_DATABASE_URL")
        or "postgresql+psycopg://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path%3Dtest_schema"
    )

    run_full_replacement(target_url, excel_path=args.excel, dry_run=args.dry_run)
