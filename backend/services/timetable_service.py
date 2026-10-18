"""
backend/services/timetable_service.py
-------------------------------------
Authoritative domain service for timetable generation, validation, scoring,
and persistence. Shared by both the REST API route (/timetable/generate)
and the conversational Scheduling Agent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.models.identity import User
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.workflow import AuditLog
from backend.schemas.timetable_generation import (
    GenerationScope,
    GenerationSummary,
    TimetableScore,
)
from backend.services.timetable_input_loader import validate_and_load_input
from backend.optimizer.timetable_solver import TimetableSolver
from backend.optimizer.validator import validate_timetable
from backend.optimizer.scorer import compute_score


class TimetableGenerationResult(BaseModel):
    success: bool
    status: str
    message: str
    version_id: Optional[int] = None
    solve_time_seconds: Optional[float] = None
    loaded_sections: int = 0
    loaded_courses: int = 0
    loaded_faculty: int = 0
    loaded_rooms: int = 0
    loaded_time_slots: int = 0
    score: Optional[TimetableScore] = None
    diagnostics: List[str] = []
    error: Optional[str] = None


def execute_timetable_generation(
    db: Session,
    scope: GenerationScope,
    current_user: User,
    strategy: str = "BALANCED",
    time_limit: int = 60,
) -> TimetableGenerationResult:
    """
    Executes the authoritative timetable generation pipeline:
    1. Scope validation & input loading
    2. Google OR-Tools CP-SAT solving
    3. Deterministic independent validation
    4. Deterministic scoring
    5. Persistence of draft TimetableVersion and TimetableEntry rows
    6. Audit log writing within the same transaction

    Must be called only by authorized administrators.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to generate timetables.",
        )

    # 1. Load and validate input
    optimizer_input = validate_and_load_input(db, scope)

    # 2. Run solver with selected strategy profile
    solver = TimetableSolver(opt_input=optimizer_input, time_limit=time_limit, strategy=strategy)
    solver_res = solver.solve()

    score_data: Optional[TimetableScore] = None
    version_id: Optional[int] = None

    if solver_res.feasible:
        # 3. Independent validation
        val_result = validate_timetable(solver_res.entries, optimizer_input)
        hard_violations = [v for v in val_result.violations if v.severity == "HARD"]
        if hard_violations:
            violation_msgs = ", ".join(v.message for v in hard_violations)
            return TimetableGenerationResult(
                success=False,
                status="VALIDATION_FAILED",
                message=f"Solver produced invalid timetable: {violation_msgs}",
                diagnostics=[v.message for v in val_result.violations],
                error=violation_msgs,
                loaded_sections=len(optimizer_input.sections),
                loaded_courses=len(optimizer_input.courses),
                loaded_faculty=len(optimizer_input.faculty),
                loaded_rooms=len(optimizer_input.rooms),
                loaded_time_slots=len(optimizer_input.time_slots),
            )

        # 4. Deterministic scoring
        score_dict = compute_score(val_result, solver_res.entries, optimizer_input)
        score_data = TimetableScore(**score_dict)

        # 5. Persist as GENERATED version with DRAFT entries
        try:
            new_version = TimetableVersion(
                academic_year_id=scope.academic_year_id,
                status="GENERATED",
                created_by=current_user.id,
            )
            db.add(new_version)
            db.flush()
            version_id = new_version.id

            assignments = {a.id: a for a in optimizer_input.course_assignments}
            for entry_res in solver_res.entries:
                a = assignments[entry_res.course_assignment_id]
                new_entry = TimetableEntry(
                    version_id=version_id,
                    department_id=scope.department_id,
                    program_id=scope.program_id,
                    semester_id=scope.semester_id,
                    section_id=a.section_id,
                    batch_id=a.batch_id,
                    course_id=a.course_id,
                    faculty_id=a.faculty_id,
                    room_id=entry_res.room_id,
                    slot_id=entry_res.slot_id,
                    status="DRAFT",
                )
                db.add(new_entry)

            # 6. Audit log
            audit = AuditLog(
                user_id=current_user.id,
                action="TIMETABLE_GENERATED",
                entity_type="TimetableVersion",
                entity_id=version_id,
                new_value={
                    "status": "GENERATED",
                    "strategy": strategy,
                    "scope": scope.model_dump(),
                    "score": score_dict.get("total_score"),
                },
            )
            db.add(audit)
            db.commit()

        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database persistence failed: {str(exc)}",
            )

        return TimetableGenerationResult(
            success=True,
            status=solver_res.status,
            message=solver_res.message,
            version_id=version_id,
            solve_time_seconds=solver_res.solve_time_seconds,
            loaded_sections=len(optimizer_input.sections),
            loaded_courses=len(optimizer_input.courses),
            loaded_faculty=len(optimizer_input.faculty),
            loaded_rooms=len(optimizer_input.rooms),
            loaded_time_slots=len(optimizer_input.time_slots),
            score=score_data,
            diagnostics=getattr(solver_res, "diagnostics", []),
        )

    else:
        # Infeasible or Timed out
        diagnostics = getattr(solver_res, "diagnostics", [])
        return TimetableGenerationResult(
            success=False,
            status=solver_res.status,
            message=solver_res.message,
            solve_time_seconds=solver_res.solve_time_seconds,
            loaded_sections=len(optimizer_input.sections),
            loaded_courses=len(optimizer_input.courses),
            loaded_faculty=len(optimizer_input.faculty),
            loaded_rooms=len(optimizer_input.rooms),
            loaded_time_slots=len(optimizer_input.time_slots),
            diagnostics=diagnostics,
            error=solver_res.message,
        )
