import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import SessionLocal
from backend.schemas.timetable_generation import GenerationScope
from backend.services.timetable_input_loader import validate_and_load_input
from backend.optimizer.timetable_solver import TimetableSolver
from backend.optimizer.validator import validate_timetable

def test_optimizer():
    db = SessionLocal()
    try:
        scope = GenerationScope(
            academic_year_id=1,
            semester_id=1,
            department_id=1,
            program_id=1
        )
        print("Loading input...")
        opt_input = validate_and_load_input(db, scope)
        print(f"Loaded {len(opt_input.courses)} courses, {len(opt_input.sections)} sections, {len(opt_input.course_assignments)} assignments")
        
        print("Building model...")
        solver = TimetableSolver(opt_input, time_limit=60)
        
        print("Solving...")
        result = solver.solve()
        print(f"Status: {result.status}, Message: {result.message}, Time: {result.solve_time_seconds:.2f}s")
        
        if result.feasible:
            print(f"Generated {len(result.entries)} entries.")
            for i, e in enumerate(result.entries[:5]):
                print(f"  Assignment {e.course_assignment_id} -> Room {e.room_id} Slot {e.slot_id} ({e.hour_type})")
                
            print("Validating independently...")
            val_result = validate_timetable(result.entries, opt_input)
            print(f"Validation Result: {val_result.is_valid}")
            if not val_result.is_valid:
                for v in val_result.violations:
                    print(f"  [{v.severity}] {v.message}")
        else:
            print("Infeasible! No entries generated.")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_optimizer()
