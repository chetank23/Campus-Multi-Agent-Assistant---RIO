"""
backend/routes/tasks.py
-----------------------
Task status, progress tracking, and result retrieval endpoint for asynchronous Celery jobs.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.celery_app import get_task_status

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskStatusResponse(BaseModel):
    task_id: str = Field(..., description="Unique Celery task identifier")
    status: str = Field(..., description="QUEUED | PROCESSING | SUCCESS | FAILURE")
    progress: int = Field(0, description="Execution progress percentage (0 to 100)")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Progress stage and runtime metadata")
    result: Optional[Any] = Field(None, description="Task output payload when status is SUCCESS")
    error: Optional[str] = Field(None, description="Error details and diagnostics when status is FAILURE")


@router.get("/{task_id}", response_model=TaskStatusResponse)
def get_task_status_endpoint(task_id: str) -> TaskStatusResponse:
    """
    Retrieve execution state, percentage progress, output results, or error diagnostics
    for an asynchronous Celery task.
    """
    status_data = get_task_status(task_id)
    return TaskStatusResponse(**status_data)
