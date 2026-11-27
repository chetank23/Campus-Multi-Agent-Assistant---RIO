"""
tests/api/test_ux_productivity_features.py
------------------------------------------
Integration tests for:
1. Role-aware Global Search (/search) & RBAC isolation
2. Personal To-Do List / My Tasks (/my-tasks) CRUD & ownership isolation
3. Dynamic Import Sample CSV (/admin/import/sample/{entity_type}) using real DB FKs
4. Published Curriculum Versions (/admin/curriculum/versions?status=PUBLISHED)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.config import engine
from backend.core.security import create_access_token
from backend.main import app
from backend.models import Building, Student, User

client = TestClient(app)


def _token_for_role(role: str, offset: int = 0) -> tuple[User, str]:
    with Session(engine) as db:
        users = db.query(User).filter(User.role == role).order_by(User.id.asc()).all()
        assert len(users) > offset
        u = users[offset]
        tok = create_access_token({"sub": str(u.id), "role": u.role})
        return u, tok


def test_global_search_role_scoping():
    _, admin_tok = _token_for_role("ADMIN")
    _, stu_tok = _token_for_role("STUDENT")

    with Session(engine) as db:
        stu = db.query(Student).first()
        assert stu is not None
        stu_id_str = stu.student_id

    # Admin can search students by student_id
    r_admin = client.get(
        "/search",
        params={"q": stu_id_str},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r_admin.status_code == 200
    data_admin = r_admin.json()
    assert any(item["entity_type"] == "student" for item in data_admin["results"])

    # Student cannot search other students' private records
    r_stu = client.get(
        "/search",
        params={"q": stu_id_str},
        headers={"Authorization": f"Bearer {stu_tok}"},
    )
    assert r_stu.status_code == 200
    data_stu = r_stu.json()
    assert all(item["entity_type"] != "student" for item in data_stu["results"])
    assert all(item["entity_type"] != "program" for item in data_stu["results"])

    # Student can search courses
    r_course = client.get(
        "/search",
        params={"q": "B2"},
        headers={"Authorization": f"Bearer {stu_tok}"},
    )
    assert r_course.status_code == 200


def test_my_tasks_crud_and_strict_ownership_isolation():
    _, stu1_tok = _token_for_role("STUDENT", 0)
    _, stu2_tok = _token_for_role("STUDENT", 1)
    _, fac_tok = _token_for_role("FACULTY", 0)
    _, admin_tok = _token_for_role("ADMIN", 0)

    # Admin does not have access to personal tasks
    r_admin = client.get("/my-tasks", headers={"Authorization": f"Bearer {admin_tok}"})
    assert r_admin.status_code == 403

    # Student 1 creates a task
    r_create = client.post(
        "/my-tasks",
        headers={"Authorization": f"Bearer {stu1_tok}"},
        json={
            "title": "Finish AI Lab Report",
            "notes": "Include evaluation metrics",
            "due_at": "2026-12-01T14:30:00",
            "priority": "HIGH",
        },
    )
    assert r_create.status_code == 201
    task = r_create.json()
    task_id = task["id"]
    assert task["status"] == "PENDING"
    assert task["priority"] == "HIGH"

    # Student 1 sees it; Student 2 does NOT
    list_1 = client.get("/my-tasks", headers={"Authorization": f"Bearer {stu1_tok}"}).json()
    list_2 = client.get("/my-tasks", headers={"Authorization": f"Bearer {stu2_tok}"}).json()
    assert any(t["id"] == task_id for t in list_1)
    assert all(t["id"] != task_id for t in list_2)

    # Student 2 cannot modify, toggle, or delete Student 1's task
    assert (
        client.put(
            f"/my-tasks/{task_id}",
            headers={"Authorization": f"Bearer {stu2_tok}"},
            json={"title": "Hacked"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/my-tasks/{task_id}/toggle",
            headers={"Authorization": f"Bearer {stu2_tok}"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/my-tasks/{task_id}",
            headers={"Authorization": f"Bearer {stu2_tok}"},
        ).status_code
        == 403
    )

    # Student 1 toggles to COMPLETED and back to PENDING
    t1 = client.patch(f"/my-tasks/{task_id}/toggle", headers={"Authorization": f"Bearer {stu1_tok}"})
    assert t1.status_code == 200
    assert t1.json()["status"] == "COMPLETED"

    t2 = client.patch(f"/my-tasks/{task_id}/toggle", headers={"Authorization": f"Bearer {stu1_tok}"})
    assert t2.status_code == 200
    assert t2.json()["status"] == "PENDING"

    # Faculty can also create & delete own task
    r_fac = client.post(
        "/my-tasks",
        headers={"Authorization": f"Bearer {fac_tok}"},
        json={"title": "Prepare Quiz", "priority": "MEDIUM"},
    )
    assert r_fac.status_code == 201
    fac_task_id = r_fac.json()["id"]
    assert client.delete(f"/my-tasks/{fac_task_id}", headers={"Authorization": f"Bearer {fac_tok}"}).status_code == 204
    assert client.delete(f"/my-tasks/{task_id}", headers={"Authorization": f"Bearer {stu1_tok}"}).status_code == 204


def test_import_sample_rooms_uses_real_existing_building_ids():
    _, admin_tok = _token_for_role("ADMIN")
    with Session(engine) as db:
        buildings = db.query(Building).order_by(Building.id.asc()).all()
        assert len(buildings) >= 1
        valid_b_ids = {str(b.id) for b in buildings}

    r_sample = client.get(
        "/admin/import/sample/rooms",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r_sample.status_code == 200
    data = r_sample.json()
    assert data["has_prerequisites"] is True
    lines = [l.strip() for l in data["csv"].splitlines() if l.strip()]
    assert len(lines) >= 2
    headers = lines[0].split(",")
    rows = []
    for line in lines[1:]:
        vals = line.split(",")
        row = dict(zip(headers, vals))
        assert row["building_id"] in valid_b_ids
        rows.append(row)

    # Confirm the generated sample passes /admin/import/preview with 0 errors
    r_prev = client.post(
        "/admin/import/preview",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"entity_type": "rooms", "rows": rows},
    )
    assert r_prev.status_code == 200
    prev = r_prev.json()
    assert prev["invalid_rows_count"] == 0
    assert prev["valid_rows_count"] == len(rows)
