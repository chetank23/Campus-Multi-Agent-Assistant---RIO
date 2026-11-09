"""
tests/api/test_data_clear_dashboard_consistency.py
---------------------------------------------------
Verifies complete operational data reset, cross-role notification broadcast,
dashboard KPI consistency, and zero stale operational artifacts.
"""

import pytest
from fastapi.testclient import TestClient

from backend.core.security import create_access_token
from backend.database import SessionLocal
from backend.main import app
from backend.models.academic import Department, Faculty, Section, Student
from backend.models.courses import Course
from backend.models.identity import User
from backend.models.space_time import Room
from backend.models.timetable import Timetable, TimetableEntry, TimetableVersion
from backend.models.workflow import AuditLog, Notification

client = TestClient(app)


@pytest.fixture
def admin_token():
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        assert admin_user is not None
        return create_access_token(data={"sub": str(admin_user.id), "role": "ADMIN", "token_type": "access"})


@pytest.fixture
def faculty_token():
    with SessionLocal() as db:
        fac = db.query(User).filter(User.role == "FACULTY").first()
        assert fac is not None
        return create_access_token(data={"sub": str(fac.id), "role": "FACULTY", "token_type": "access"})


@pytest.fixture
def student_token():
    with SessionLocal() as db:
        stu = db.query(User).filter(User.role == "STUDENT").first()
        assert stu is not None
        return create_access_token(data={"sub": str(stu.id), "role": "STUDENT", "token_type": "access"})


def test_clear_operational_data_and_dashboard_consistency(admin_token: str, faculty_token: str, student_token: str):
    """
    Full workflow verification:
    1. Verify master academic data baseline.
    2. Execute data clear (clear_all=True) with explicit confirmation.
    3. Verify all timetable tables have 0 rows in DB.
    4. Verify GET /admin/analytics/overview returns 0 published timetables and Cache-Control headers.
    5. Verify GET /admin/analytics/department-progress returns 0 published sections and 0%.
    6. Verify GET /timetable/versions returns 0 items.
    7. Verify GET /admin/audit-logs returns CLEAR_GENERATED_OPERATIONAL_DATA as the top record and no orphan timetable logs.
    8. Verify cross-role broadcast notification was dispatched to all users (ADMIN, FACULTY, STUDENT).
    9. Verify faculty and student my-timetable endpoints return empty entries with 200 OK.
    10. Verify idempotency when running clear again.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Master academic data baseline check
    with SessionLocal() as db:
        baseline_users = db.query(User).count()
        baseline_students = db.query(Student).count()
        baseline_faculty = db.query(Faculty).count()
        baseline_courses = db.query(Course).count()
        baseline_rooms = db.query(Room).count()
        assert baseline_users > 0, "Must have users in database"
        assert baseline_students > 0, "Must have students in database"
        assert baseline_faculty > 0, "Must have faculty in database"

    # 2. Execute full clear
    clear_res = client.post(
        "/admin/data-management/clear",
        headers=headers,
        json={"categories": ["timetable", "resources", "faculty_ops", "other_ops", "notifications"], "confirmation": True},
    )
    assert clear_res.status_code == 200
    res_data = clear_res.json()
    assert res_data["success"] is True

    # 3. Direct DB state verification
    with SessionLocal() as db:
        assert db.query(Timetable).count() == 0, "timetables must be 0"
        assert db.query(TimetableVersion).count() == 0, "timetable_versions must be 0"
        assert db.query(TimetableEntry).count() == 0, "timetable_entries must be 0"
        # Master records strictly preserved
        assert db.query(User).count() == baseline_users
        assert db.query(Student).count() == baseline_students
        assert db.query(Faculty).count() == baseline_faculty
        assert db.query(Course).count() == baseline_courses
        assert db.query(Room).count() == baseline_rooms

    # 4. Analytics Overview API verification
    ov_res = client.get("/admin/analytics/overview", headers=headers)
    assert ov_res.status_code == 200
    assert "no-cache" in ov_res.headers.get("Cache-Control", "")
    ov_data = ov_res.json()
    assert ov_data["timetables"]["total_versions"] == 0
    assert ov_data["people"]["total_users"] == baseline_users
    assert ov_data["infrastructure"]["total_rooms"] == baseline_rooms

    # 5. Department Progress API verification
    dp_res = client.get("/admin/analytics/department-progress", headers=headers)
    assert dp_res.status_code == 200
    assert "no-cache" in dp_res.headers.get("Cache-Control", "")
    dp_data = dp_res.json()
    for item in dp_data:
        assert item["published_sections"] == 0
        assert item["completion_percentage"] == 0

    # 6. Timetable Versions API verification
    ver_res = client.get("/timetable/versions", headers=headers)
    assert ver_res.status_code == 200
    assert "no-cache" in ver_res.headers.get("Cache-Control", "")
    ver_data = ver_res.json()
    assert len(ver_data) == 0

    # 7. Audit Logs API verification
    al_res = client.get("/admin/audit-logs?limit=5", headers=headers)
    assert al_res.status_code == 200
    assert "no-cache" in al_res.headers.get("Cache-Control", "")
    al_data = al_res.json()
    items = al_data["items"]
    assert len(items) > 0
    assert items[0]["action"] == "CLEAR_GENERATED_OPERATIONAL_DATA"
    for log_item in items:
        assert log_item["entity_type"] not in ("Timetable", "TimetableVersion", "TimetableEntry")

    # 8. Cross-role notification delivery verification
    # Admin inbox
    adm_notifs_res = client.get("/notifications?limit=10", headers=headers)
    assert adm_notifs_res.status_code == 200
    adm_notifs = adm_notifs_res.json()
    assert len(adm_notifs) > 0
    assert any("Schedule Reset" in n["title"] for n in adm_notifs)

    # Faculty inbox
    fac_headers = {"Authorization": f"Bearer {faculty_token}"}
    fac_notifs_res = client.get("/notifications?limit=10", headers=fac_headers)
    assert fac_notifs_res.status_code == 200
    fac_notifs = fac_notifs_res.json()
    assert len(fac_notifs) > 0
    assert any("Schedule Reset" in n["title"] for n in fac_notifs)

    # Student inbox
    stu_headers = {"Authorization": f"Bearer {student_token}"}
    stu_notifs_res = client.get("/notifications?limit=10", headers=stu_headers)
    assert stu_notifs_res.status_code == 200
    stu_notifs = stu_notifs_res.json()
    assert len(stu_notifs) > 0
    assert any("Schedule Reset" in n["title"] for n in stu_notifs)

    # 9. Faculty & Student Timetable empty state verification
    fac_tt_res = client.get("/faculty/my-timetable", headers=fac_headers)
    assert fac_tt_res.status_code == 200
    assert "no-cache" in fac_tt_res.headers.get("Cache-Control", "")
    fac_tt_data = fac_tt_res.json()
    assert fac_tt_data["total_teaching_hours"] == 0
    assert len(fac_tt_data["entries"]) == 0

    stu_tt_res = client.get("/student/my-timetable", headers=stu_headers)
    assert stu_tt_res.status_code == 200
    assert "no-cache" in stu_tt_res.headers.get("Cache-Control", "")
    stu_tt_data = stu_tt_res.json()
    assert stu_tt_data["total_class_hours"] == 0
    assert len(stu_tt_data["entries"]) == 0

    # 10. Idempotency check: running clear again is completely safe
    clear_res_2 = client.post(
        "/admin/data-management/clear",
        headers=headers,
        json={"categories": ["timetable", "resources", "faculty_ops", "other_ops", "notifications"], "confirmation": True},
    )
    assert clear_res_2.status_code == 200
    assert clear_res_2.json()["success"] is True
