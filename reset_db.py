import os
import sys

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from backend.models.base import Base
from backend.models import academic, identity, courses, space_time, resources, timetable, workflow

def reset_db():
    print("Connecting to database...")
    engine = create_engine('postgresql://campus_user:campus_secure_2026@localhost/campus_ai')
    
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()
