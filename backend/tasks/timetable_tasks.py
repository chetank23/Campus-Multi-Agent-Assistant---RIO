"""
backend/tasks/timetable_tasks.py
--------------------------------
Celery background task for asynchronous CP-SAT timetable generation.
Reports detailed progress states:
QUEUED -> PROCESSING (Input loading -> CP-SAT Solving -> Validation -> Persistence) -> SUCCESS / FAILURE
"""

import logging
from typing import Any, Dict, Optional

from backend.celery_app import celery_app
from backend.config import SessionLocal
from backend.models.identity import User
from backend.schemas.timetable_generation import GenerationScope
from backend.services.timetable_service import execute_timetable_generation

logger = logging.getLogger("campus_ai.tasks.timetable")


def _safe_update_state(task: Any, state: str, meta: Dict[str, Any]) -> None:
    """Safely updates Celery task state only if valid Celery request context exists."""
    if task is not None and getattr(task, "request", None) and getattr(task.request, "id", None):
        try:
            task.update_state(state=state, meta=meta)
        except Exception as exc:
            logger.debug("Failed to update Celery state: %s", exc)


def _execute_timetable_generation(
    task: Any,
    scope_dict: Dict[str, Any],
    user_id: int,
    strategy: str = "BALANCED",
    time_limit: int = 60,
) -> Dict[str, Any]:
    """
    Core executor for CP-SAT timetable generation in Celery background task.
    """
    _safe_update_state(
        task,
        state="PROGRESS",
        meta={
            "progress": 10,
            "stage": "QUEUED",
            "message": "Task queued for timetable optimization worker.",
        },
    )

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            error_msg = f"User #{user_id} not found."
            logger.error(error_msg)
            _safe_update_state(
                task,
                state="FAILURE",
                meta={"progress": 100, "stage": "FAILURE", "error": error_msg},
            )
            raise ValueError(error_msg)

        try:
            scope = GenerationScope(**scope_dict)
        except Exception as exc:
            error_msg = f"Invalid GenerationScope: {exc}"
            logger.error(error_msg)
            _safe_update_state(
                task,
                state="FAILURE",
                meta={"progress": 100, "stage": "FAILURE", "error": error_msg},
            )
            raise ValueError(error_msg) from exc

        _safe_update_state(
            task,
            state="PROGRESS",
            meta={
                "progress": 25,
                "stage": "LOADING_INPUT",
                "message": "Validating academic scope and loading candidate space-time variables.",
            },
        )

        try:
            _safe_update_state(
                task,
                state="PROGRESS",
                meta={
                    "progress": 45,
                    "stage": "SOLVING",
                    "message": "Executing Google OR-Tools CP-SAT constraint optimization solver.",
                },
            )

            gen_res = execute_timetable_generation(
                db=db,
                scope=scope,
                current_user=user,
                strategy=strategy,
                time_limit=time_limit,
            )

            if not gen_res.success:
                error_msg = gen_res.message
                logger.warning("Timetable generation unsuccessful: %s (diagnostics: %s)", error_msg, gen_res.diagnostics)
                _safe_update_state(
                    task,
                    state="FAILURE",
                    meta={
                        "progress": 100,
                        "stage": "FAILURE",
                        "status": gen_res.status,
                        "error": error_msg,
                        "diagnostics": gen_res.diagnostics,
                    },
                )
                raise RuntimeError(f"Timetable generation failed ({gen_res.status}): {error_msg}")

            result_payload = {
                "status": gen_res.status,
                "message": gen_res.message,
                "version_id": gen_res.version_id,
                "score": gen_res.score.model_dump() if gen_res.score else None,
                "solve_time_seconds": gen_res.solve_time_seconds,
                "loaded_sections": gen_res.loaded_sections,
                "loaded_courses": gen_res.loaded_courses,
                "loaded_faculty": gen_res.loaded_faculty,
                "loaded_rooms": gen_res.loaded_rooms,
                "loaded_time_slots": gen_res.loaded_time_slots,
                "diagnostics": gen_res.diagnostics,
            }

            _safe_update_state(
                task,
                state="SUCCESS",
                meta={
                    "progress": 100,
                    "stage": "COMPLETED",
                    "message": gen_res.message,
                    "result": result_payload,
                },
            )
            return result_payload

        except Exception as exc:
            logger.exception("Unexpected error in execute_timetable_generation: %s", exc)
            _safe_update_state(
                task,
                state="FAILURE",
                meta={
                    "progress": 100,
                    "stage": "FAILURE",
                    "error": str(exc),
                },
            )
            if (
                task is not None
                and hasattr(task, "request")
                and hasattr(task, "max_retries")
                and getattr(task.request, "retries", 0) < task.max_retries
            ):
                raise task.retry(exc=exc, countdown=5)
            raise


@celery_app.task(bind=True, name="tasks.generate_timetable", max_retries=1)
def generate_timetable_task(
    self,
    scope_dict: Dict[str, Any],
    user_id: int,
    strategy: str = "BALANCED",
    time_limit: int = 60,
) -> Dict[str, Any]:
    """
    Executes CP-SAT timetable optimization asynchronously in Celery worker.
    Reports progress percentages and stage metadata throughout execution.
    """
    return _execute_timetable_generation(
        task=self,
        scope_dict=scope_dict,
        user_id=user_id,
        strategy=strategy,
        time_limit=time_limit,
    )


@celery_app.task(bind=True, name="tasks.batch_generate_timetable", max_retries=1)
def batch_generate_timetable_task(
    self,
    scope_dict: Dict[str, Any],
    user_id: int,
    strategy: str = "BALANCED",
    time_limit: int = 120,
) -> Dict[str, Any]:
    """
    Executes department-level multi-section CP-SAT timetable generation asynchronously.
    """
    return _execute_timetable_generation(
        task=self,
        scope_dict=scope_dict,
        user_id=user_id,
        strategy=strategy,
        time_limit=time_limit,
    )
