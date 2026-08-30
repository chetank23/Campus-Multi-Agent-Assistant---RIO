from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.identity import User
from backend.dependencies import get_current_user, require_role
from backend.schemas.timetable_generation import GenerationScope, GenerationSummary
from backend.services.timetable_input_loader import validate_and_load_input
from backend.optimizer.timetable_solver import TimetableSolver
from backend.optimizer.validator import validate_timetable

router = APIRouter(prefix="/timetable", tags=["timetable"])

@router.post("/generate", response_model=GenerationSummary)
def generate_timetable(
    scope: GenerationScope,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("HOD", "TIMETABLE_COORDINATOR", "ADMIN"))
):
    """
    Stage 4 Part 2: Validates the generation scope, loads input data,
    and invokes the CP-SAT timetable solver.
    """
    # 1. Load and validate input
    optimizer_input = validate_and_load_input(db, scope)

    # 2. Initialize Solver
    solver = TimetableSolver(opt_input=optimizer_input, time_limit=60)
    
    # 3. Solve
    result = solver.solve()
    
    # 4. Optional: Validate result independently if feasible
    if result.feasible:
        val_result = validate_timetable(result.entries, optimizer_input)
        if not val_result.is_valid:
            # We found a feasible solution in solver, but independent validation failed!
            # This indicates a bug in the solver constraints.
            violations = ", ".join([v.message for v in val_result.violations])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Solver produced invalid timetable: {violations}"
            )
            
    if not result.feasible:
        # We can either return 422 or a 200 with status=INFEASIBLE. 
        # Returning 422 for infeasible is a common API design.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail={
                "message": result.message,
                "diagnostics": getattr(result, 'diagnostics', [])
            }
        )

    return GenerationSummary(
        status=result.status,
        message=result.message,
        loaded_sections=len(optimizer_input.sections),
        loaded_courses=len(optimizer_input.courses),
        loaded_faculty=len(optimizer_input.faculty),
        loaded_rooms=len(optimizer_input.rooms),
        loaded_time_slots=len(optimizer_input.time_slots),
        solve_time_seconds=result.solve_time_seconds,
        generated_entries=result.entries
    )
