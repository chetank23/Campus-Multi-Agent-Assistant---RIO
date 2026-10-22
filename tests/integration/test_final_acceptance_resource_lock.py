"""
tests/integration/test_final_acceptance_resource_lock.py
---------------------------------------------------------
Authoritative End-to-End Acceptance Test Suite for Resource Booking & Locking Policy:
Fulfills all 10 mandatory acceptance cases defined in the RIO-MJP master specification:
  1. Book an unbooked resource and verify the resulting state.
  2. Attempt another booking for the same resource with a different purpose.
  3. Ask whether the already-locked resource is available (API & Agent).
  4. Attempt to book it for a different date, time, or user.
  5. Attempt concurrent bookings from separate requests (row locking verification).
  6. Test pending, approved, rejected, cancelled, and failed booking transitions.
  7. Verify that only permitted, successfully committed state transitions release the lock.
  8. Verify that failed transactions never leave a false success message or an inconsistent lock.
  9. Test direct API calls that bypass the AI assistant.
  10. Verify that unauthorized users cannot bypass the policy.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.resources import Resource, ResourceBooking
from backend.models.workflow import AuditLog

client = TestClient(app)


# ── Auth Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_token():
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def faculty2_token():
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty 2 login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]


# ── Case 1: Book an unbooked resource and verify the resulting state ───────────

def test_case_1_book_unbooked_resource_verify_state(admin_token, faculty_token):
    # 1. Create a dedicated active resource
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Lab 101", "resource_type": "LAB", "capacity": 30, "location": "Academic Block A"},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    # Verify initially available
    date_str = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    avail = client.get(
        "/resources/availability",
        headers={"Authorization": f"Bearer {faculty_token}"},
        params={"resource_id": res_id, "date": date_str, "start_time": "09:00:00", "end_time": "11:00:00"},
    )
    assert avail.status_code == 200
    assert avail.json()["available"] is True

    # 2. Book resource
    booking_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_str,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "purpose": "Hardware Architecture Lab Session",
        },
    )
    assert booking_resp.status_code == 201
    b_data = booking_resp.json()
    assert b_data["status"] == "PENDING"
    assert b_data["resource_id"] == res_id
    booking_id = b_data["id"]

    # 3. Verify PostgreSQL database state and audit record
    with Session(engine) as db:
        bk = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
        assert bk is not None
        assert bk.status == "PENDING"
        assert str(bk.date) == date_str

        audit = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "ResourceBooking", AuditLog.entity_id == booking_id)
            .first()
        )
        assert audit is not None
        assert audit.action == "RESOURCE_BOOKING_CREATED"

    # Clean up
    client.post(f"/resources/bookings/{booking_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})


# ── Case 2: Attempt another booking for same resource with different purpose ──

def test_case_2_attempt_another_booking_different_purpose(admin_token, faculty_token, faculty2_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Seminar 201", "resource_type": "SEMINAR_HALL", "capacity": 100},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    date_str = (datetime.date.today() + datetime.timedelta(days=12)).isoformat()
    b1_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_str,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Faculty Colloquium",
        },
    )
    assert b1_resp.status_code == 201
    b1_id = b1_resp.json()["id"]

    # Second booking attempt for same date/time with different purpose
    b2_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty2_token}"},
        json={
            "resource_id": res_id,
            "date": date_str,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Student Hackathon Briefing",
        },
    )
    assert b2_resp.status_code == 409
    err = b2_resp.json()
    assert "Resource already booked" in str(err)
    assert "active booking" in str(err)

    # Clean up
    client.post(f"/resources/bookings/{b1_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})


# ── Case 3: Ask whether the already-locked resource is available ───────────────

def test_case_3_ask_whether_locked_resource_available(admin_token, faculty_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Auditorium 301", "resource_type": "AUDITORIUM", "capacity": 250},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]
    res_name = res_resp.json()["name"]

    date_str = (datetime.date.today() + datetime.timedelta(days=15)).isoformat()
    b_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_str,
            "start_time": "14:00:00",
            "end_time": "17:00:00",
            "purpose": "Keynote Presentation",
        },
    )
    assert b_resp.status_code == 201
    b_id = b_resp.json()["id"]

    # Query 1: Direct API availability check
    avail_resp = client.get(
        "/resources/availability",
        headers={"Authorization": f"Bearer {faculty_token}"},
        params={"resource_id": res_id, "date": date_str, "start_time": "14:00:00", "end_time": "17:00:00"},
    )
    assert avail_resp.status_code == 200
    avail_data = avail_resp.json()
    assert avail_data["available"] is False
    assert len(avail_data["conflicts"]) > 0
    assert avail_data["conflicts"][0]["conflict_type"] == "ACTIVE_BOOKING_LOCK"

    # Query 2: Assistant conversational check
    chat_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Is {res_name} available on {date_str} from 14:00 to 17:00?"},
    )
    assert chat_resp.status_code == 200
    reply = chat_resp.json()["reply"]
    assert "Resource already booked" in reply
    assert "active booking" in reply
    assert "Please select another resource" in reply

    # Clean up
    client.post(f"/resources/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})


# ── Case 4: Attempt to book it for a different date, time, or user ─────────────

def test_case_4_attempt_book_different_date_time_user(admin_token, faculty_token, faculty2_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Projector 401", "resource_type": "PROJECTOR", "capacity": 1},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]
    res_name = res_resp.json()["name"]

    # Lock resource on Date 1
    date_1 = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    b_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": date_1,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "purpose": "Faculty 1 Lecture",
        },
    )
    assert b_resp.status_code == 201
    b_id = b_resp.json()["id"]

    # Attempt to book on Date 2 (40 days later), different time, different user (Faculty 2)
    date_2 = (datetime.date.today() + datetime.timedelta(days=40)).isoformat()
    diff_attempt = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty2_token}"},
        json={
            "resource_id": res_id,
            "date": date_2,
            "start_time": "15:00:00",
            "end_time": "17:00:00",
            "purpose": "Faculty 2 Workshop",
        },
    )
    assert diff_attempt.status_code == 409
    assert "Resource already booked" in diff_attempt.text

    # Conversational attempt for Date 2 via assistant
    chat_attempt = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty2_token}"},
        json={"message": f"Book {res_name} on {date_2} from 15:00 to 17:00 for Faculty 2 Workshop"},
    )
    assert chat_attempt.status_code == 200
    chat_reply = chat_attempt.json()["reply"]
    assert "Resource already booked" in chat_reply
    assert chat_attempt.json().get("proposal") is None

    # Clean up
    client.post(f"/resources/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})


# ── Case 5: Attempt concurrent bookings from separate requests ────────────────

def test_case_5_concurrent_bookings_separate_requests(admin_token, faculty_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Concurrency Hall", "resource_type": "SEMINAR_HALL", "capacity": 80},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    date_str = (datetime.date.today() + datetime.timedelta(days=18)).isoformat()

    def submit_req(idx: int):
        sub_client = TestClient(app)
        return sub_client.post(
            "/resources/bookings",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "resource_id": res_id,
                "date": date_str,
                "start_time": "10:00:00",
                "end_time": "12:00:00",
                "purpose": f"Concurrent Candidate {idx}",
            },
        )

    # Dispatch 5 simultaneous booking requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(submit_req, i) for i in range(5)]
        results = [f.result() for f in futures]

    status_codes = [r.status_code for r in results]
    assert status_codes.count(201) == 1, f"Expected exactly 1 success, got status codes: {status_codes}"
    assert status_codes.count(409) == 4, f"Expected 4 conflicts, got status codes: {status_codes}"

    # Verify database has exactly 1 booking
    with Session(engine) as db:
        count = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).count()
        assert count == 1
        winner = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).first()
        assert winner is not None
        client.post(f"/resources/bookings/{winner.id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})


# ── Case 6: Test pending, approved, rejected, cancelled transitions ───────────

def test_case_6_test_all_booking_status_transitions(admin_token, faculty_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Transition Lab", "resource_type": "LAB", "capacity": 20},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    date_str = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()

    # 1. PENDING -> APPROVED
    b1 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"resource_id": res_id, "date": date_str, "start_time": "09:00:00", "end_time": "11:00:00", "purpose": "Approve Path"},
    ).json()["id"]
    appr = client.post(f"/resources/bookings/{b1}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    assert appr.status_code == 200
    assert appr.json()["status"] == "APPROVED"

    # 2. APPROVED -> REJECTED (Forbidden transition: only PENDING can be rejected)
    bad_rej = client.post(f"/resources/bookings/{b1}/reject", headers={"Authorization": f"Bearer {admin_token}"})
    assert bad_rej.status_code == 400

    # 3. APPROVED -> CANCELLED
    cancel_appr = client.post(f"/resources/bookings/{b1}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})
    assert cancel_appr.status_code == 200
    assert cancel_appr.json()["status"] == "CANCELLED"

    # 4. CANCELLED -> APPROVED (Forbidden transition)
    bad_appr = client.post(f"/resources/bookings/{b1}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    assert bad_appr.status_code == 400

    # 5. PENDING -> REJECTED
    b2 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"resource_id": res_id, "date": date_str, "start_time": "13:00:00", "end_time": "15:00:00", "purpose": "Reject Path"},
    ).json()["id"]
    rej = client.post(f"/resources/bookings/{b2}/reject", headers={"Authorization": f"Bearer {admin_token}"})
    assert rej.status_code == 200
    assert rej.json()["status"] == "REJECTED"

    # 6. REJECTED -> APPROVED (Forbidden transition)
    bad_appr2 = client.post(f"/resources/bookings/{b2}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    assert bad_appr2.status_code == 400

    # 7. REJECTED -> CANCELLED (Forbidden transition)
    bad_cancel = client.post(f"/resources/bookings/{b2}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})
    assert bad_cancel.status_code == 400


# ── Case 7: Only permitted committed transitions release the lock ─────────────

def test_case_7_only_permitted_committed_transitions_release_lock(admin_token, faculty_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Release Hall", "resource_type": "SEMINAR_HALL", "capacity": 50},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    date_str = (datetime.date.today() + datetime.timedelta(days=22)).isoformat()

    # Step A: Create PENDING booking -> Resource is locked
    b = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00", "purpose": "Testing Release"},
    ).json()
    b_id = b["id"]

    # Verify locked
    chk1 = client.get("/resources/availability", headers={"Authorization": f"Bearer {faculty_token}"}, params={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00"})
    assert chk1.json()["available"] is False

    # Step B: Transition to APPROVED -> Resource is still locked!
    client.post(f"/resources/bookings/{b_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    chk2 = client.get("/resources/availability", headers={"Authorization": f"Bearer {faculty_token}"}, params={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00"})
    assert chk2.json()["available"] is False

    # Step C: Attempt invalid rejection on APPROVED booking -> Fails, lock preserved!
    fail_rej = client.post(f"/resources/bookings/{b_id}/reject", headers={"Authorization": f"Bearer {admin_token}"})
    assert fail_rej.status_code == 400
    chk3 = client.get("/resources/availability", headers={"Authorization": f"Bearer {faculty_token}"}, params={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00"})
    assert chk3.json()["available"] is False

    # Step D: Successfully CANCEL the approved booking -> Lock is released!
    cancel = client.post(f"/resources/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})
    assert cancel.status_code == 200
    chk4 = client.get("/resources/availability", headers={"Authorization": f"Bearer {faculty_token}"}, params={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00"})
    assert chk4.json()["available"] is True

    # Step E: Create new booking and REJECT it -> Lock is released!
    b2 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00", "purpose": "Testing Rejection Release"},
    ).json()
    b2_id = b2["id"]
    client.post(f"/resources/bookings/{b2_id}/reject", headers={"Authorization": f"Bearer {admin_token}"})
    chk5 = client.get("/resources/availability", headers={"Authorization": f"Bearer {faculty_token}"}, params={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00"})
    assert chk5.json()["available"] is True


# ── Case 8: Failed transactions leave no false success or inconsistent lock ───

def test_case_8_failed_transactions_leave_no_false_success_or_inconsistent_lock(admin_token, faculty_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Integrity Hall", "resource_type": "AUDITORIUM", "capacity": 300},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    # 1. Booking attempt with invalid interval (end_time before start_time)
    bad_req = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-25",
            "start_time": "15:00:00",
            "end_time": "14:00:00",
            "purpose": "Invalid Interval",
        },
    )
    assert bad_req.status_code == 422 or bad_req.status_code == 400

    # Verify no booking or audit log was created
    with Session(engine) as db:
        bks = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).all()
        assert len(bks) == 0
        audits = db.query(AuditLog).filter(AuditLog.action == "RESOURCE_BOOKING_CREATED", AuditLog.new_value["resource_id"].astext == str(res_id)).all()
        assert len(audits) == 0

    # Verify resource remains completely available and unlocked
    avail = client.get(
        "/resources/availability",
        headers={"Authorization": f"Bearer {faculty_token}"},
        params={"resource_id": res_id, "date": "2026-11-25", "start_time": "14:00:00", "end_time": "16:00:00"},
    )
    assert avail.json()["available"] is True


# ── Case 9: Direct API calls bypass assistant ─────────────────────────────────

def test_case_9_direct_api_calls_bypass_assistant(admin_token, faculty_token):
    """Confirm global lock enforcement works entirely at the REST/service layer without the agent."""
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance Direct API Room", "resource_type": "LAB", "capacity": 40},
    )
    res_id = res_resp.json()["id"]

    date_str = (datetime.date.today() + datetime.timedelta(days=25)).isoformat()

    # Create directly via REST
    r1 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"resource_id": res_id, "date": date_str, "start_time": "09:00:00", "end_time": "11:00:00", "purpose": "Direct REST Booking"},
    )
    assert r1.status_code == 201
    b_id = r1.json()["id"]

    # Direct REST attempt to book again -> 409
    r2 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"resource_id": res_id, "date": date_str, "start_time": "14:00:00", "end_time": "16:00:00", "purpose": "Second Direct REST Booking"},
    )
    assert r2.status_code == 409
    assert "Resource already booked" in r2.text

    # Direct REST cancel -> 200
    r3 = client.post(f"/resources/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {faculty_token}"})
    assert r3.status_code == 200


# ── Case 10: Unauthorized users cannot bypass policy ──────────────────────────

def test_case_10_unauthorized_users_cannot_bypass_policy(admin_token, faculty_token, faculty2_token, student_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Acceptance RBAC Room", "resource_type": "LAB", "capacity": 25},
    )
    res_id = res_resp.json()["id"]

    date_str = (datetime.date.today() + datetime.timedelta(days=28)).isoformat()
    b = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"resource_id": res_id, "date": date_str, "start_time": "10:00:00", "end_time": "12:00:00", "purpose": "Faculty 1 Booking"},
    ).json()
    b_id = b["id"]

    # 1. Student cannot approve
    st_appr = client.post(f"/resources/bookings/{b_id}/approve", headers={"Authorization": f"Bearer {student_token}"})
    assert st_appr.status_code == 403

    # 2. Student cannot reject
    st_rej = client.post(f"/resources/bookings/{b_id}/reject", headers={"Authorization": f"Bearer {student_token}"})
    assert st_rej.status_code == 403

    # 3. Faculty 2 cannot cancel Faculty 1's booking
    fac2_cancel = client.post(f"/resources/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {faculty2_token}"})
    assert fac2_cancel.status_code == 403

    # 4. Student cannot create new resource inventory items
    st_create = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"name": "Illegal Student Lab", "resource_type": "LAB", "capacity": 50},
    )
    assert st_create.status_code == 403

    # 5. Clean up via Admin
    client.post(f"/resources/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {admin_token}"})
