import os
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv(".env")
engine = create_engine(os.environ["DATABASE_URL"])
Session = sessionmaker(bind=engine)

TRUNCATE_ORDER = [
    "audit_logs", "notifications", "change_requests", "resource_bookings",
    "timetable_entries", "timetable_versions", 
    "resources", "academic_calendar", "faculty_availability", "time_slots",
    "labs", "rooms", "buildings",
    "elective_group_courses", "elective_groups",
    "course_assignments", "courses",
    "students", "faculty", "users",
    "batches", "sections", "semesters", "academic_years", "programs", "departments"
]

def reset_database():
    with Session() as session:
        print("Resetting database (Truncating all tables)...")
        for table_name in TRUNCATE_ORDER:
            # We use CASCADE just to be doubly safe, even though order is mostly reverse FK
            session.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
        session.commit()
        print("Database has been cleanly reset.")

if __name__ == "__main__":
    reset_database()
