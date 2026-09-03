import os
import sys

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.config import engine
from backend.models.base import Base
from backend.models import academic, identity, courses, space_time, resources, timetable, workflow

def reset_db():
    if os.environ.get("CONFIRM_DB_RESET") != "yes":
        print("ERROR: Database reset is a destructive action.")
        print("Please set the CONFIRM_DB_RESET=yes environment variable to proceed.")
        sys.exit(1)

    print("Connecting to database...")
    
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()
