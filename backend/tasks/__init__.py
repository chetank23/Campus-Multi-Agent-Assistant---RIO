"""
backend/tasks/__init__.py
-------------------------
Celery background task modules for curriculum extraction and timetable generation.
"""

from backend.tasks.curriculum_tasks import extract_curriculum_task
from backend.tasks.timetable_tasks import generate_timetable_task, batch_generate_timetable_task

__all__ = [
    "extract_curriculum_task",
    "generate_timetable_task",
    "batch_generate_timetable_task",
]
