import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def reset_database():
    load_dotenv(".env")
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is required.", file=sys.stderr)
        sys.exit(1)

    try:
        parsed = make_url(db_url)
    except Exception:
        print("ERROR: DATABASE_URL could not be parsed as a valid database URL.", file=sys.stderr)
        sys.exit(1)

    db_name = (parsed.database or "").strip()
    is_test_run = os.environ.get("IS_TEST_RUN") == "true"
    is_test_db = "test" in db_name.lower()

    if not (is_test_run or is_test_db):
        confirm = os.environ.get("CONFIRM_DB_RESET", "").strip().lower()
        if confirm != "yes":
            print("=" * 70, file=sys.stderr)
            print("ERROR: DESTRUCTIVE OPERATION GUARD ACTIVATED", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(f"scripts/reset_database.py targets non-test database: '{db_name}'", file=sys.stderr)
            print(f"on host '{parsed.host or 'localhost'}:{parsed.port or 5432}'.", file=sys.stderr)
            print("This command executes TRUNCATE TABLE ... CASCADE across all application tables,", file=sys.stderr)
            print("permanently deleting all existing data.", file=sys.stderr)
            print("", file=sys.stderr)
            print("To authorize this destructive operation on development data, set:", file=sys.stderr)
            print("  CONFIRM_DB_RESET=yes", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            sys.exit(1)
        print(f"[reset_database] Target database: '{db_name}' (CONFIRM_DB_RESET=yes authorized).")
    else:
        print(f"[reset_database] Target test database: '{db_name}'.")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        print("Resetting database (Truncating all tables in reverse FK order)...")
        for table_name in TRUNCATE_ORDER:
            session.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
        session.commit()
        print("Database has been cleanly reset.")


if __name__ == "__main__":
    reset_database()
