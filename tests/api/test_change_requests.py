from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.config import engine
from backend.main import app

client = TestClient(app)


def _email_for_role(role: str) -> str:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT email FROM users WHERE role = :role AND is_active = TRUE LIMIT 1"),
            {"role": role},
        ).fetchone()
    assert row, f"No active seeded {role} user found"
    return row[0]


def _login(email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "Test@1234"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_change_request_submission_listing_and_admin_review():
    student_token = _login(_email_for_role("STUDENT"))
    admin_token = _login(_email_for_role("ADMIN"))

    created = client.post(
        "/change-requests",
        headers={"Authorization": f"Bearer {student_token}"},
        json={
            "request_type": "TIMETABLE_CHANGE",
            "related_entity_id": None,
            "reason": "Request a timetable adjustment due to a timetable conflict.",
        },
    )
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    own_list = client.get(
        "/change-requests",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert own_list.status_code == 200
    assert any(item["id"] == request_id for item in own_list.json())

    pending = client.get(
        "/change-requests/pending",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pending.status_code == 200
    assert any(item["id"] == request_id for item in pending.json())

    reviewed = client.patch(
        f"/change-requests/{request_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "APPROVED", "review_note": "Approved after review."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "APPROVED"
    assert reviewed.json()["review_note"] == "Approved after review."

    replay_review = client.patch(
        f"/change-requests/{request_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "REJECTED"},
    )
    assert replay_review.status_code == 409
