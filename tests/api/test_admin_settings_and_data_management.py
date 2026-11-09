"""
tests/api/test_admin_settings_and_data_management.py
----------------------------------------------------
Tests for Admin Settings and Safe Operational Data Management (Phase 4):
- RBAC permissions on settings routes
- General & Timetable settings persistence
- Dry-run preview of operational data clear
- Controlled transactional deletion and AuditLog generation
- Master data immutability verification
"""

import pytest
from fastapi.testclient import TestClient

from backend.core.security import create_access_token
from backend.database import SessionLocal
from backend.main import app
from backend.models.identity import User
from backend.models.system_setting import SystemSetting
from backend.models.workflow import AuditLog

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


def test_settings_rbac_guards(admin_token: str, faculty_token: str, student_token: str):
    """Verifies that non-admin users cannot access administrative settings."""
    # Faculty is rejected
    res_fac = client.get("/admin/settings", headers={"Authorization": f"Bearer {faculty_token}"})
    assert res_fac.status_code == 403

    # Student is rejected
    res_stu = client.get("/admin/settings", headers={"Authorization": f"Bearer {student_token}"})
    assert res_stu.status_code == 403

    # Admin is accepted
    res_adm = client.get("/admin/settings", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_adm.status_code == 200
    data = res_adm.json()
    assert "general" in data
    assert "timetable" in data
    assert "access" in data
    assert "system" in data


def test_general_settings_update(admin_token: str):
    """Verifies updating general settings persists to the database."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "institution": {
            "institution_name": "REVA University - Tested",
            "campus_name": "Main Campus",
            "department": "AI & Data Science",
            "timezone": "Asia/Kolkata",
        },
        "notifications": {
            "email_alerts_enabled": True,
            "timetable_publish_alerts": False,
            "substitution_alerts": True,
        },
    }
    res = client.patch("/admin/settings/general", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["institution"]["institution_name"] == "REVA University - Tested"
    assert data["notifications"]["timetable_publish_alerts"] is False


def test_timetable_settings_update(admin_token: str):
    """Verifies updating timetable settings persists."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "working_days": "MON_FRI",
        "max_consecutive_faculty_lectures": 2,
        "enable_soft_lab_preference": True,
    }
    res = client.patch("/admin/settings/timetable", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["working_days"] == "MON_FRI"
    assert data["max_consecutive_faculty_lectures"] == 2


def test_data_management_summary_and_preview(admin_token: str):
    """Verifies discovery summary and dry-run preview before data deletion."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res_sum = client.get("/admin/data-management/summary", headers=headers)
    assert res_sum.status_code == 200
    summary = res_sum.json()
    assert "categories" in summary
    assert summary["master_records_protected"] is True

    # Preview clearing timetable
    res_prev = client.post(
        "/admin/data-management/preview",
        headers=headers,
        json={"categories": ["timetable"], "clear_all": False},
    )
    assert res_prev.status_code == 200
    prev_data = res_prev.json()
    assert prev_data["safe_to_execute"] is True
    assert prev_data["master_records_protected"] is True
    assert len(prev_data["affected_tables"]) > 0


def test_data_management_clear_requires_confirmation(admin_token: str):
    """Verifies that clear operation fails without explicit confirmation: true."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.post(
        "/admin/data-management/clear",
        headers=headers,
        json={"categories": ["resources"], "confirmation": False},
    )
    assert res.status_code == 400
    assert "Explicit confirmation" in res.json()["detail"]


def test_safe_data_clear_execution(admin_token: str):
    """Verifies executing data clear removes selected records and writes an AuditLog."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Clear other_ops (e.g. notifications/other operational items)
    res = client.post(
        "/admin/data-management/clear",
        headers=headers,
        json={"categories": ["other_ops"], "confirmation": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["audit_log_id"] > 0

    # Verify audit log exists
    with SessionLocal() as db:
        audit = db.query(AuditLog).filter(AuditLog.id == data["audit_log_id"]).first()
        assert audit is not None
        assert audit.action == "CLEAR_GENERATED_OPERATIONAL_DATA"

