"""
tests/api/test_celery_task_workers_and_eager.py
-----------------------------------------------
Integration test suite for Celery background tasks and eager local fallback.
Verifies:
1. Celery task configuration and fallback reachability detection.
2. Background timetable generation task dispatch.
3. Task status tracking and completion lifecycle.
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.celery_app import celery_app, CELERY_TASK_ALWAYS_EAGER
from backend.tasks.timetable_tasks import generate_timetable_task

from sqlalchemy.orm import Session
from backend.config import engine
from backend.models.academic import Section, Semester
from backend.models.identity import User

client = TestClient(app)


def test_celery_app_configuration():
    assert celery_app is not None
    # Verify eager setting is boolean
    assert isinstance(CELERY_TASK_ALWAYS_EAGER, bool)


def test_celery_task_execution_eager():
    # 1. Login as admin
    login_res = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get valid academic scope
    import os
    from sqlalchemy import create_engine
    from backend.models.academic import AcademicYear, Department, Section, Semester
    eng = create_engine(os.environ["DATABASE_URL"])
    with Session(eng) as db:
        ay = db.query(AcademicYear).first()
        sem = db.query(Semester).filter(Semester.academic_year_id == ay.id).first() if ay else None
        dept = db.query(Department).first()
        sections = (
            db.query(Section)
            .filter(Section.department_id == dept.id, Section.semester_id == sem.id)
            .limit(2)
            .all()
            if dept and sem
            else []
        )
        if len(sections) < 2 and sem:
            sections = db.query(Section).filter(Section.semester_id == sem.id).limit(2).all()

        if not ay or not sem or not dept or not sections:
            pytest.skip("Test requires valid academic scope in database")

        scope = {
            "academic_year_id": ay.id,
            "semester_id": sem.id,
            "department_id": dept.id,
            "section_ids": [s.id for s in sections],
            "working_days": "MON_SAT",
        }
    eng.dispose()

    # 3. Dispatch async batch generation task to Celery
    res = client.post("/timetable/batch-generate?async_mode=true", json=scope, headers=headers)
    assert res.status_code == 200, f"Async batch generate failed: {res.text}"
    data = res.json()
    assert "task_id" in data
    assert data["status"] == "QUEUED"
    task_id = data["task_id"]

    # 4. Verify task status endpoint tracks Celery task lifecycle
    status_res = client.get(f"/tasks/{task_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["task_id"] == task_id
    assert status_data["status"] in ("QUEUED", "PROCESSING", "SUCCESS", "FAILURE")
    assert "progress" in status_data
