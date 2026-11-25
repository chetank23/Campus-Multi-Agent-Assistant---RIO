"""
tests/api/test_users_pagination_remediation.py
----------------------------------------------
Regression and validation suite for Phase 1.1:
Admin Users & Roles API pagination boundaries, filtering, and input constraints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.core.security import create_access_token
from backend.models.identity import User

client = TestClient(app)


def get_admin_token() -> str:
    with Session(engine) as db:
        admin = db.query(User).filter(User.role.in_(["ADMIN", "SUPER_ADMIN"]), User.is_active == True).first()
        if admin:
            return create_access_token({"sub": str(admin.id), "role": admin.role})
    res = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    if res.status_code != 200:
        res = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Admin#RioLocal26"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return res.json()["access_token"]


def test_users_api_rejects_limit_exceeding_200():
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Requesting limit=1000 must be rejected with HTTP 422 by backend validation
    res = client.get("/users?limit=1000", headers=headers)
    assert res.status_code == 422, f"Expected 422 for limit=1000, got {res.status_code}"
    detail = res.json()["detail"]
    assert any("less than or equal to 200" in str(d) for d in detail)


def test_users_api_accepts_bounded_limits():
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Valid limits: 1, 50, 200
    for lim in (1, 50, 200):
        res = client.get(f"/users?limit={lim}", headers=headers)
        assert res.status_code == 200, f"Expected 200 for limit={lim}, got {res.status_code}: {res.text}"
        data = res.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) <= lim
        assert data["limit"] == lim


def test_users_api_rejects_invalid_pagination():
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Negative limit or zero limit
    res_zero = client.get("/users?limit=0", headers=headers)
    assert res_zero.status_code == 422

    res_neg = client.get("/users?limit=-1", headers=headers)
    assert res_neg.status_code == 422

    res_neg_skip = client.get("/users?skip=-5", headers=headers)
    assert res_neg_skip.status_code == 422


def test_users_api_role_and_department_filters():
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    for role in ("ADMIN", "FACULTY", "STUDENT"):
        res = client.get(f"/users?role={role}&limit=50", headers=headers)
        assert res.status_code == 200
        data = res.json()
        for u in data["items"]:
            assert u["role"] == role


def test_users_api_search_and_empty_results():
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Empty string search should not crash
    res_empty_search = client.get("/users?search=", headers=headers)
    assert res_empty_search.status_code == 200

    # Search for non-existent user
    res_none = client.get("/users?search=non_existent_xyz_user_99999", headers=headers)
    assert res_none.status_code == 200
    data = res_none.json()
    assert data["items"] == []
    assert data["total"] == 0
