import os
import sys

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def reset_db():
    confirm = os.environ.get("CONFIRM_DB_RESET", "").strip().lower()
    if confirm != "yes":
        print("=" * 70, file=sys.stderr)
        print("ERROR: DESTRUCTIVE OPERATION GUARD ACTIVATED", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print("reset_db.py drops and recreates all database tables via Base.metadata.drop_all.", file=sys.stderr)
        print("This is a destructive action that permanently erases existing database data.", file=sys.stderr)
        print("", file=sys.stderr)
        print("To authorize this destructive operation, set CONFIRM_DB_RESET=yes:", file=sys.stderr)
        print("  CONFIRM_DB_RESET=yes", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)

    from backend.config import engine
    from backend.models.base import Base
    # Ensure all models are registered in Base.metadata
    from backend.models import academic, identity, courses, space_time, resources, timetable, workflow

    db_name = getattr(engine.url, "database", "unknown")
    host = getattr(engine.url, "host", "localhost")
    port = getattr(engine.url, "port", 5432)
    print(f"Connecting to database '{db_name}' on host '{host}:{port}'...")
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Database reset complete.")


if __name__ == "__main__":
    reset_db()
