"""
scripts/audit_database_state.py
Read-only database integrity and workbook alignment audit.
"""
import json
from sqlalchemy import create_engine, text

def main():
    db_url = "postgresql+psycopg://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path%3Dtest_schema"
    engine = create_engine(db_url)
    with engine.connect() as conn:
        current_rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        
        tables = [
            r[0] for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'test_schema' ORDER BY table_name")
            ).fetchall()
        ]
        
        counts = {}
        for t in [
            'users', 'departments', 'programs', 'academic_years', 'semesters',
            'sections', 'faculty', 'students', 'courses', 'course_assignments',
            'rooms', 'buildings', 'timetable_entries', 'timetable_versions',
            'resources', 'resource_bookings', 'curriculum_versions', 'regulations'
        ]:
            if t in tables:
                counts[t] = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            else:
                counts[t] = "TABLE_MISSING"

        # FK integrity checks
        fk_errors = []
        bad_user_dept = int(conn.execute(text(
            "SELECT count(*) FROM users u LEFT JOIN departments d ON u.department_id = d.id "
            "WHERE u.department_id IS NOT NULL AND d.id IS NULL"
        )).scalar() or 0)
        if bad_user_dept > 0:
            fk_errors.append(f"users.department_id broken: {bad_user_dept}")

        bad_student_user = int(conn.execute(text(
            "SELECT count(*) FROM students s LEFT JOIN users u ON s.user_id = u.id WHERE u.id IS NULL"
        )).scalar() or 0)
        if bad_student_user > 0:
            fk_errors.append(f"students.user_id broken: {bad_student_user}")

        bad_fac_user = int(conn.execute(text(
            "SELECT count(*) FROM faculty f LEFT JOIN users u ON f.user_id = u.id WHERE u.id IS NULL"
        )).scalar() or 0)
        if bad_fac_user > 0:
            fk_errors.append(f"faculty.user_id broken: {bad_fac_user}")

        bad_entry_version = int(conn.execute(text(
            "SELECT count(*) FROM timetable_entries te LEFT JOIN timetable_versions tv ON te.version_id = tv.id "
            "WHERE tv.id IS NULL"
        )).scalar() or 0)
        if bad_entry_version > 0:
            fk_errors.append(f"timetable_entries.version_id broken: {bad_entry_version}")

        # Duplicates checks
        dups = {
            "duplicate_emails": int(conn.execute(text("SELECT count(*) - count(distinct email) FROM users")).scalar() or 0),
            "duplicate_student_id": int(conn.execute(text("SELECT count(*) - count(distinct student_id) FROM students WHERE student_id IS NOT NULL")).scalar() or 0) if 'students' in tables else 0,
            "duplicate_faculty_id": int(conn.execute(text("SELECT count(*) - count(distinct faculty_id) FROM faculty WHERE faculty_id IS NOT NULL")).scalar() or 0) if 'faculty' in tables else 0,
        }

        # Role breakdown
        roles = {str(r[0]): int(r[1]) for r in conn.execute(text("SELECT role, count(*) FROM users GROUP BY role")).fetchall()}

        output = {
            "database_target": "127.0.0.1:5433/campus_ai_test (test_schema)",
            "alembic_head": current_rev,
            "total_tables": len(tables),
            "tables": tables,
            "entity_counts": counts,
            "role_breakdown": roles,
            "fk_integrity_errors": fk_errors,
            "duplicate_records": dups,
        }
        print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
