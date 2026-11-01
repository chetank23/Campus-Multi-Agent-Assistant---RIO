import os
import csv
import argparse
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import (
    Department, Program, AcademicYear, Semester, Section, Batch,
    User, Faculty, Student, Course, CourseAssignment,
    ElectiveGroup, ElectiveGroupCourse, Building, Room, Lab,
    TimeSlot, FacultyAvailability, AcademicCalendar, Resource,
    TimetableVersion, TimetableEntry, ResourceBooking, ChangeRequest, Notification, AuditLog
)

# Tables in order of dependencies (parents first)
# Used for inserting
INSERT_ORDER = [
    ("departments", Department),
    ("programs", Program),
    ("academic_years", AcademicYear),
    ("semesters", Semester),
    ("sections", Section),
    ("batches", Batch),
    ("users", User),
    ("faculty", Faculty),
    ("students", Student),
    ("courses", Course),
    ("course_assignments", CourseAssignment),
    ("elective_groups", ElectiveGroup),
    ("elective_group_courses", ElectiveGroupCourse),
    ("buildings", Building),
    ("rooms", Room),
    ("labs", Lab),
    ("time_slots", TimeSlot),
    ("faculty_availability", FacultyAvailability),
    ("academic_calendar", AcademicCalendar),
    ("resources", Resource),
]

# All tables in reverse dependency order for safe TRUNCATE
TRUNCATE_ORDER = [
    "notification_outbox", "agent_proposals", "audit_logs", "notifications", "change_requests", "resource_bookings",
    "timetable_entries", "timetable_versions", 
    "resources", "academic_calendar", "faculty_availability", "time_slots",
    "labs", "rooms", "buildings",
    "elective_group_courses", "elective_groups",
    "course_assignments", "courses",
    "students", "faculty", "users",
    "batches", "sections", "semesters", "academic_years", "programs", "departments"
]


def validate_target_and_get_session():
    """
    Validates that the target database is authorized for destructive TRUNCATE operations.
    - If running under an authorized test run (IS_TEST_RUN=true) or target database name contains 'test':
      Allowed for automated testing.
    - If targeting a non-test / development database:
      Refuses by default. Requires explicit CONFIRM_DEV_SEED_RESET=yes environment variable.
    """
    load_dotenv(".env")
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required and must be set.")

    try:
        parsed = make_url(db_url)
    except Exception:
        raise RuntimeError("DATABASE_URL could not be parsed as a valid database URL.")

    db_name = (parsed.database or "").strip()
    is_test_run = os.environ.get("IS_TEST_RUN") == "true"
    is_test_db = "test" in db_name.lower()

    if is_test_run:
        if not is_test_db:
            print("=" * 70, file=sys.stderr)
            print("CRITICAL SAFETY VIOLATION: IS_TEST_RUN is set, but the target database", file=sys.stderr)
            print(f"'{db_name}' does not meet the test-database naming rule (must contain 'test').", file=sys.stderr)
            print("Refusing to execute destructive truncate operation. Aborting.", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            sys.exit(1)
        print(f"[seed_database] Verified isolated test database target: '{db_name}'.")
    elif is_test_db:
        print(f"[seed_database] Targeting test database: '{db_name}'.")
    else:
        # Development / non-test database: require explicit confirmation
        confirm = os.environ.get("CONFIRM_DEV_SEED_RESET", "").strip().lower()
        if confirm != "yes":
            print("=" * 70, file=sys.stderr)
            print("ERROR: DESTRUCTIVE OPERATION GUARD ACTIVATED", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(f"scripts/seed_database.py targets non-test database: '{db_name}'", file=sys.stderr)
            print(f"on host '{parsed.host or 'localhost'}:{parsed.port or 5432}'.", file=sys.stderr)
            print("Seeding executes TRUNCATE TABLE ... CASCADE across all application tables,", file=sys.stderr)
            print("which permanently deletes existing development data.", file=sys.stderr)
            print("", file=sys.stderr)
            print("To authorize this destructive operation on development data, set:", file=sys.stderr)
            print("  CONFIRM_DEV_SEED_RESET=yes", file=sys.stderr)
            print("", file=sys.stderr)
            print("For tests, configure TEST_DATABASE_URL pointing to a dedicated test database.", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            sys.exit(1)
        print(f"[seed_database] Target database: '{db_name}' (CONFIRM_DEV_SEED_RESET=yes authorized).")

    engine = create_engine(db_url)
    return sessionmaker(bind=engine)


def clean_value(val):
    if val == "": return None
    if val.lower() == "true": return True
    if val.lower() == "false": return False
    return val


def seed_database(dataset_name):
    csv_dir = Path(f"data/sample/{dataset_name}")
    if not csv_dir.exists():
        print(f"Error: Directory {csv_dir} does not exist. Run generator first.")
        return

    Session = validate_target_and_get_session()

    with Session() as session:
        # 1. TRUNCATE existing data
        print("Truncating existing tables (reverse FK order)...")
        for table_name in TRUNCATE_ORDER:
            session.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
        session.commit()

        # 2. INSERT data
        print(f"\nLoading Dataset {dataset_name} from {csv_dir}...")
        
        for table_name, model in INSERT_ORDER:
            csv_path = csv_dir / f"{table_name}.csv"
            if not csv_path.exists():
                print(f"  Skipping {table_name} (no CSV)")
                continue

            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                mappings = []
                for row in reader:
                    # Clean empty strings to None
                    clean_row = {k: clean_value(v) for k, v in row.items()}
                    
                    if table_name == "departments":
                        # Remove hod_id if present in CSV (column no longer exists)
                        clean_row.pop("hod_id", None)
                        
                    mappings.append(clean_row)
                
                if mappings:
                    session.bulk_insert_mappings(model, mappings)
                    print(f"  Inserted {len(mappings)} rows into {table_name}")
        
        session.commit()
        
        # 4. SUMMARY
        print("\n=== LOAD SUMMARY ===")
        for table_name in TRUNCATE_ORDER[::-1]: # regular order
            count = session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            if count is not None and count > 0:
                print(f"  {table_name:25s} : {count}")
                
        print("\nSeed successful!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed database from CSVs")
    parser.add_argument("--dataset", choices=["A", "B", "C"], required=True, help="Dataset size (A=small, B=medium, C=large)")
    args = parser.parse_args()
    seed_database(args.dataset)
