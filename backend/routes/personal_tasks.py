"""
backend/routes/personal_tasks.py
--------------------------------
Private Personal To-Do List / Notepad CRUD endpoints for STUDENT and FACULTY.
Ownership is strictly derived from the authenticated JWT user_id; Admins cannot
access other users' private tasks.
"""

from __future__ import annotations

import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import require_role
from backend.models.identity import User
from backend.models.personal_task import PersonalTask

router = APIRouter(prefix="/my-tasks", tags=["My Tasks"])

TaskPriority = Literal["LOW", "MEDIUM", "HIGH"]
TaskStatus = Literal["PENDING", "COMPLETED"]


class PersonalTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=4000)
    due_at: Optional[datetime.datetime] = None
    priority: TaskPriority = "MEDIUM"

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Task title cannot be empty.")
        return cleaned


class PersonalTaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=4000)
    due_at: Optional[datetime.datetime] = None
    clear_due_at: bool = False
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Task title cannot be empty.")
        return cleaned


class PersonalTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    notes: Optional[str] = None
    due_at: Optional[datetime.datetime] = None
    priority: TaskPriority
    status: TaskStatus
    completed_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


def _get_owned_task_or_404(db: Session, task_id: int, user_id: int) -> PersonalTask:
    task = db.query(PersonalTask).filter(PersonalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    if task.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only manage your own personal tasks.",
        )
    return task


@router.get("", response_model=List[PersonalTaskResponse], summary="List my personal tasks")
def list_my_tasks(
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    priority: Optional[TaskPriority] = Query(None),
    q: Optional[str] = Query(None, max_length=100),
    sort_by: Literal["due_at", "priority", "created_at"] = Query("created_at"),
    current_user: User = Depends(require_role("STUDENT", "FACULTY")),
    db: Session = Depends(get_db),
) -> List[PersonalTask]:
    query = db.query(PersonalTask).filter(PersonalTask.user_id == current_user.id)
    if status_filter:
        query = query.filter(PersonalTask.status == status_filter)
    if priority:
        query = query.filter(PersonalTask.priority == priority)
    if q and q.strip():
        pat = f"%{q.strip()}%"
        query = query.filter((PersonalTask.title.ilike(pat)) | (PersonalTask.notes.ilike(pat)))

    if sort_by == "due_at":
        query = query.order_by(PersonalTask.due_at.is_(None), PersonalTask.due_at.asc(), PersonalTask.created_at.desc())
    elif sort_by == "priority":
        prio_order = case(
            (PersonalTask.priority == "HIGH", 1),
            (PersonalTask.priority == "MEDIUM", 2),
            else_=3,
        )
        query = query.order_by(prio_order.asc(), PersonalTask.due_at.is_(None), PersonalTask.due_at.asc())
    else:
        query = query.order_by(PersonalTask.created_at.desc())

    return query.all()


@router.post("", response_model=PersonalTaskResponse, status_code=status.HTTP_201_CREATED, summary="Create a personal task")
def create_my_task(
    payload: PersonalTaskCreate,
    current_user: User = Depends(require_role("STUDENT", "FACULTY")),
    db: Session = Depends(get_db),
) -> PersonalTask:
    due_val = payload.due_at.replace(tzinfo=None) if payload.due_at else None
    task = PersonalTask(
        user_id=current_user.id,
        title=payload.title,
        notes=payload.notes.strip() if payload.notes else None,
        due_at=due_val,
        priority=payload.priority,
        status="PENDING",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}", response_model=PersonalTaskResponse, summary="Update a personal task")
def update_my_task(
    task_id: int,
    payload: PersonalTaskUpdate,
    current_user: User = Depends(require_role("STUDENT", "FACULTY")),
    db: Session = Depends(get_db),
) -> PersonalTask:
    task = _get_owned_task_or_404(db, task_id, current_user.id)

    if payload.title is not None:
        task.title = payload.title
    if payload.notes is not None:
        task.notes = payload.notes.strip() or None
    if payload.clear_due_at:
        task.due_at = None
    elif payload.due_at is not None:
        task.due_at = payload.due_at.replace(tzinfo=None)
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.status is not None:
        task.status = payload.status
        task.completed_at = (
            datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            if payload.status == "COMPLETED"
            else None
        )

    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}/toggle", response_model=PersonalTaskResponse, summary="Toggle task completion")
def toggle_my_task(
    task_id: int,
    current_user: User = Depends(require_role("STUDENT", "FACULTY")),
    db: Session = Depends(get_db),
) -> PersonalTask:
    task = _get_owned_task_or_404(db, task_id, current_user.id)
    if task.status == "COMPLETED":
        task.status = "PENDING"
        task.completed_at = None
    else:
        task.status = "COMPLETED"
        task.completed_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a personal task")
def delete_my_task(
    task_id: int,
    current_user: User = Depends(require_role("STUDENT", "FACULTY")),
    db: Session = Depends(get_db),
) -> None:
    task = _get_owned_task_or_404(db, task_id, current_user.id)
    db.delete(task)
    db.commit()
