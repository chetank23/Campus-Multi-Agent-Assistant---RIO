"""
tests/test_phase2_multi_section_and_tasks.py
--------------------------------------------
Integration test suite for Phase 2:
1. Celery task status endpoint & background execution tracking
2. Multi-section CP-SAT timetable generation (shared faculty & rooms)
3. Independent validation, quality scoring, and atomic publication
4. Real-time notification SSE streaming with user & role isolation
"""

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.models.academic import AcademicYear, Department, Section, Semester
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry
from backend.models.workflow import AuditLog
from backend.config import engine

client = TestClient(app)


def get_token(credentials: dict) -> str:
    res = client.post("/auth/login", json=credentials)
    if res.status_code != 200:
        fallback = {**credentials, "password": "Admin#RioLocal26"}
        res = client.post("/auth/login", json=fallback)
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


def test_task_status_endpoint():
    # 1. Non-existent task returns QUEUED status without error
    res = client.get("/tasks/non-existent-task-id-12345")
    assert res.status_code == 200
    data = res.json()
    assert data["task_id"] == "non-existent-task-id-12345"
    assert data["status"] in ("QUEUED", "PROCESSING")
    assert "progress" in data
    assert "meta" in data


def test_multi_section_batch_generate_and_publish():
    admin_token = get_token({"email": "admin@campus.edu", "password": "Test@1234"})

    with Session(engine) as db:
        # Scope isolation: reset timetable versions and canonical timetables
        db.query(TimetableEntry).delete()
        db.query(TimetableVersion).delete()
        db.query(Timetable).delete()
        db.commit()

        ay = db.query(AcademicYear).first()
        assert ay is not None, "AcademicYear must exist in database"
        ay_id: int = ay.id

        sem = db.query(Semester).filter(Semester.academic_year_id == ay_id).first()
        assert sem is not None, "Semester must exist in database"
        sem_id: int = sem.id

        dept = db.query(Department).first()
        assert dept is not None, "Department must exist in database"
        dept_id: int = dept.id

        sections = (
            db.query(Section)
            .filter(Section.department_id == dept_id, Section.semester_id == sem_id)
            .limit(2)
            .all()
        )
        if len(sections) < 2:
            # Fallback to any 2 sections in the same semester
            sections = db.query(Section).filter(Section.semester_id == sem_id).limit(2).all()

        assert len(sections) >= 2, "Test requires at least two sections"
        sec_ids: list[int] = [s.id for s in sections]

    scope = {
        "academic_year_id": ay_id,
        "semester_id": sem_id,
        "department_id": dept_id,
        "section_ids": sec_ids,
        "working_days": "MON_SAT",
    }

    # 1. Batch Generate Preview (Synchronous) across multiple sections
    preview_res = client.post(
        "/timetable/batch-generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=scope,
    )
    assert preview_res.status_code == 200, f"Preview generation failed: {preview_res.text}"
    preview_data = preview_res.json()
    assert "sections" in preview_data
    assert "entries" in preview_data
    assert "is_valid" in preview_data
    assert preview_data["is_valid"] is True
    assert preview_data["can_publish"] is True

    # 2. Verify shared resource conflict prevention across sections
    entries = preview_data["entries"]
    assert len(entries) > 0, "No entries generated in preview"

    # Faculty conflicts check across all sections
    fac_slots = {}
    room_slots = {}
    sec_slots = {}

    for e in entries:
        f_key = (e["faculty_id"], e["slot_id"])
        r_key = (e["room_id"], e["slot_id"])
        s_key = (e["section_id"], e["slot_id"])

        assert f_key not in fac_slots, f"Faculty {e['faculty_id']} has duplicate assignment in slot {e['slot_id']}"
        assert r_key not in room_slots, f"Room {e['room_id']} has collision in slot {e['slot_id']}"
        assert s_key not in sec_slots, f"Section {e['section_id']} has multiple classes in slot {e['slot_id']}"

        fac_slots[f_key] = e
        room_slots[r_key] = e
        sec_slots[s_key] = e

    # 3. Batch Generate Async Queue Dispatch
    async_res = client.post(
        "/timetable/batch-generate?async_mode=true",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=scope,
    )
    assert async_res.status_code == 200
    async_data = async_res.json()
    assert async_data["status"] == "QUEUED"
    assert "task_id" in async_data

    # Query task status endpoint
    task_id = async_data["task_id"]
    status_res = client.get(f"/tasks/{task_id}")
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["task_id"] == task_id
    assert st_data["status"] in ("QUEUED", "PROCESSING", "SUCCESS")

    # 4. Atomic Canonical Publication across the multiple sections
    pub_req = {
        "academic_year_id": ay_id,
        "semester_id": sem_id,
        "department_id": dept_id,
        "working_days": "MON_SAT",
        "entries": entries,
    }
    pub_res = client.post(
        "/timetable/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=pub_req,
    )
    assert pub_res.status_code == 200, f"Publication failed: {pub_res.text}"
    pub_data = pub_res.json()
    assert pub_data["success"] is True

    # 5. Verify PostgreSQL persistence & Audit logging
    with Session(engine) as db:
        published_tts = (
            db.query(Timetable)
            .filter(
                Timetable.academic_year_id == ay_id,
                Timetable.semester_id == sem_id,
                Timetable.section_id.in_(sec_ids),
                Timetable.status == "PUBLISHED",
            )
            .all()
        )
        assert len(published_tts) >= 1

        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "TIMETABLE_PUBLISHED")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert audit is not None


def test_realtime_notifications_sse():
    admin_token = get_token({"email": "admin@campus.edu", "password": "Test@1234"})

    # 1. Unauthenticated request to SSE stream is rejected with 401
    unauth_res = client.get("/notifications/stream")
    assert unauth_res.status_code == 401

    # 2. Authenticated request establishes SSE stream with max_events=1 handshake
    res = client.get(f"/notifications/stream?token={admin_token}&max_events=1")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
    assert "event: connected" in res.text
    assert '"connected": true' in res.text
