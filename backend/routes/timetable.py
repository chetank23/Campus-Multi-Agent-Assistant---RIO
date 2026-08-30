from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.identity import User
from backend.dependencies import get_current_user, require_role
from backend.schemas.timetable_generation import GenerationScope, GenerationSummary
from backend.services.timetable_input_loader import validate_and_load_input

router = APIRouter(prefix="/timetable", tags=["timetable"])

@router.post("/generate", response_model=GenerationSummary)
def generate_timetable(
    scope: GenerationScope,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("HOD", "TIMETABLE_COORDINATOR", "ADMIN"))
):
    """
    Stage 4 Part 1: Validates the generation scope and loads all required input data
    from the database to build the OptimizerInput.
    Does NOT invoke the CP-SAT solver yet.
    """
    # Load and validate input
    optimizer_input = validate_and_load_input(db, scope)

    # In Stage 4 Part 2, this will be passed to the CP-SAT solver (e.g. via Celery).
    # For now, we return a summary of the validated input.
    return GenerationSummary(
        status="VALID",
        message="Generation scope validated and data loaded successfully. Ready for solver.",
        loaded_sections=len(optimizer_input.sections),
        loaded_courses=len(optimizer_input.courses),
        loaded_faculty=len(optimizer_input.faculty),
        loaded_rooms=len(optimizer_input.rooms),
        loaded_time_slots=len(optimizer_input.time_slots)
    )
