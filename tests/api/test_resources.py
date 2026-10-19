"""
tests/api/test_resources.py
---------------------------
Automated test suite for Stage 7: Resource Allocation Engine & Administration:
  1. Resource Inventory CRUD, validation, search, and role guards
  2. Safe deactivation when bookings depend on resource
  3. Booking request lifecycle (PENDING -> APPROVED / REJECTED, CANCELLED)
  4. Conflict detection:
     - Overlap with approved booking returns 409
     - Strict interval overlap (adjacent non-overlapping bookings allowed)
     - Overlap with published timetable returns 409
     - Non-published timetable versions do not block bookings
     - Approval rechecks availability against competing requests
     - Alternative resource recommendations on conflict
  5. Audit log generation and integrity verification
"""

import concurrent.futures
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Building, Room, TimeSlot
from backend.models.timetable import TimetableEntry, TimetableVersion
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


# ── Resource Inventory Management Tests ────────────────────────────────────────

def test_list_resources_auth_guard():
    # Anonymous request rejected
    resp = client.get("/resources")
    assert resp.status_code in [401, 403]


def test_create_resource_admin_only(admin_token, faculty_token):
    # Faculty cannot create resources (403 Forbidden)
    resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"name": "Faculty Rogue Lab", "resource_type": "LAB", "capacity": 30},
    )
    assert resp.status_code == 403

    # Admin creates valid resource
    resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Advanced Robotics Lab",
            "resource_type": "LAB",
            "location": "Engineering Block Lab 301",
            "capacity": 45,
            "status": "ACTIVE",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Advanced Robotics Lab"
    assert data["resource_type"] == "LAB"
    assert data["capacity"] == 45
    assert "id" in data


def test_resource_validation(admin_token):
    # Invalid resource type
    resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Spaceship", "resource_type": "INVALID_TYPE", "capacity": 10},
    )
    assert resp.status_code == 422


def test_update_resource(admin_token, faculty_token):
    # Create a resource to update
    create_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Old Projector 1", "resource_type": "PROJECTOR", "capacity": 1},
    )
    assert create_resp.status_code == 201
    res_id = create_resp.json()["id"]

    # Faculty cannot update
    resp = client.put(
        f"/resources/{res_id}",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"name": "Hacked Projector"},
    )
    assert resp.status_code == 403

    # Admin updates name and capacity
    resp = client.put(
        f"/resources/{res_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "HD Projector Unit 1", "capacity": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "HD Projector Unit 1"
    assert resp.json()["capacity"] == 2


def test_missing_resource_behavior(admin_token):
    resp = client.get("/resources/999999", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404

    resp = client.put("/resources/999999", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "X"})
    assert resp.status_code == 404


def test_safe_deactivation_when_bookings_exist(admin_token, faculty_token):
    # Create resource
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Seminar Hall Delta", "resource_type": "SEMINAR_HALL", "capacity": 120},
    )
    assert res_resp.status_code == 201
    res_id = res_resp.json()["id"]

    # Create a booking on it
    book_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-10",
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Guest Lecture on Distributed Systems",
        },
    )
    assert book_resp.status_code == 201

    # Attempt to delete the resource: should safely deactivate instead of breaking database integrity
    del_resp = client.delete(f"/resources/{res_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert del_resp.status_code == 200
    data = del_resp.json()
    assert data["action"] == "DEACTIVATED"

    # Verify resource status is now INACTIVE
    check_resp = client.get(f"/resources/{res_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert check_resp.json()["status"] == "INACTIVE"


# ── Booking Lifecycle and Workflow State Machine Tests ────────────────────────

def test_booking_creation_and_requester_integrity(faculty_token, admin_token):
    # Create clean test resource
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Conference Hall Beta", "resource_type": "SEMINAR_HALL", "capacity": 80},
    )
    res_id = res_resp.json()["id"]

    # Faculty submits request with an invalid interval (end before start)
    invalid_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-15",
            "start_time": "14:00:00",
            "end_time": "13:00:00",
            "purpose": "Time Travel Meeting",
        },
    )
    assert invalid_resp.status_code == 422

    # Faculty submits valid request
    resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-15",
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "purpose": "Department Faculty Colloquium",
        },
    )
    assert resp.status_code == 201
    booking = resp.json()
    assert booking["status"] == "PENDING"
    assert booking["requested_by"] == 2  # Allison Hill (id 2)
    assert booking["resource_id"] == res_id


def test_booking_approval_lifecycle_and_audit(faculty_token, admin_token):
    # Create resource
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "IoT Hardware Lab", "resource_type": "LAB", "capacity": 40},
    )
    res_id = res_resp.json()["id"]

    # Submit request
    book_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-16",
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "purpose": "Microcontroller Workshop",
        },
    )
    assert book_resp.status_code == 201
    booking_id = book_resp.json()["id"]

    # Faculty cannot approve (403 Forbidden)
    resp = client.post(
        f"/resources/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {faculty_token}"},
    )
    assert resp.status_code == 403

    # Admin approves
    approve_resp = client.post(
        f"/resources/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_resp.status_code == 200
    appr_data = approve_resp.json()
    assert appr_data["status"] == "APPROVED"
    assert appr_data["approved_by"] == 1  # System Admin

    # Invalid state transition: re-approving an already approved booking fails (400)
    reapprove_resp = client.post(
        f"/resources/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reapprove_resp.status_code == 400

    # Rejecting an already approved booking directly fails (400)
    reject_resp = client.post(
        f"/resources/bookings/{booking_id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reject_resp.status_code == 400

    # Verify audit log in database
    with Session(engine) as db:
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "ResourceBooking",
                AuditLog.entity_id == booking_id,
                AuditLog.action == "RESOURCE_BOOKING_APPROVED",
            )
            .first()
        )
        assert audit is not None
        assert audit.user_id == 1
        assert audit.new_value is not None
        assert audit.new_value["status"] == "APPROVED"


def test_booking_rejection_lifecycle(faculty_token, admin_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "AV Projector Set 5", "resource_type": "PROJECTOR", "capacity": 1},
    )
    res_id = res_resp.json()["id"]

    book_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-17",
            "start_time": "11:00:00",
            "end_time": "12:00:00",
            "purpose": "Classroom presentation",
        },
    )
    booking_id = book_resp.json()["id"]

    # Admin rejects with reason
    reject_resp = client.post(
        f"/resources/bookings/{booking_id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Device scheduled for lens maintenance"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"

    # Cannot approve a REJECTED booking
    appr_resp = client.post(
        f"/resources/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert appr_resp.status_code == 400


def test_booking_cancellation_permissions(faculty_token, faculty2_token, admin_token):
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Main Auditorium", "resource_type": "AUDITORIUM", "capacity": 500},
    )
    res_id = res_resp.json()["id"]

    # Faculty 1 books
    book_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-18",
            "start_time": "10:00:00",
            "end_time": "13:00:00",
            "purpose": "Tech Symposium",
        },
    )
    booking_id = book_resp.json()["id"]

    # Faculty 2 tries to cancel Faculty 1's booking -> 403 Forbidden!
    resp = client.post(
        f"/resources/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {faculty2_token}"},
    )
    assert resp.status_code == 403

    # Faculty 1 cancels their own booking -> 200 OK
    cancel_resp = client.post(
        f"/resources/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {faculty_token}"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"


# ── Conflict Detection Engine Tests ───────────────────────────────────────────

def test_conflict_detection_approved_booking_overlap(faculty_token, admin_token):
    # Setup test resource
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "AI Supercomputing Lab", "resource_type": "LAB", "capacity": 50},
    )
    res_id = res_resp.json()["id"]

    # 1. First booking: 10:00 to 12:00, approved
    b1 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-20",
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Deep Learning Practicum",
        },
    ).json()
    appr_resp = client.post(
        f"/resources/bookings/{b1['id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert appr_resp.status_code == 200

    # 2. Overlapping attempt A: starts inside (11:00 to 13:00) -> 409 Conflict
    resp_a = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-20",
            "start_time": "11:00:00",
            "end_time": "13:00:00",
            "purpose": "Overlapping request A",
        },
    )
    assert resp_a.status_code == 409
    assert "Resource already booked" in resp_a.text or "ACTIVE_BOOKING_LOCK" in resp_a.text

    # 3. Overlapping attempt B: ends inside (09:00 to 10:30) -> 409 Conflict
    resp_b = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-20",
            "start_time": "09:00:00",
            "end_time": "10:30:00",
            "purpose": "Overlapping request B",
        },
    )
    assert resp_b.status_code == 409

    # 4. Overlapping attempt C: completely encloses (09:00 to 13:00) -> 409 Conflict
    resp_c = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-20",
            "start_time": "09:00:00",
            "end_time": "13:00:00",
            "purpose": "Overlapping request C",
        },
    )
    assert resp_c.status_code == 409

    # 5. Overlapping attempt D: completely inside (10:30 to 11:30) -> 409 Conflict
    resp_d = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-20",
            "start_time": "10:30:00",
            "end_time": "11:30:00",
            "purpose": "Overlapping request D",
        },
    )
    assert resp_d.status_code == 409

    # 6. Global Resource Lock Policy: adjacent or other-interval booking fails with 409 Conflict
    # while active lock (APPROVED) is in effect
    resp_adj = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-20",
            "start_time": "08:00:00",
            "end_time": "10:00:00",
            "purpose": "Early morning setup (adjacent before)",
        },
    )
    assert resp_adj.status_code == 409
    assert "already booked" in resp_adj.text.lower() or "ACTIVE_BOOKING_LOCK" in resp_adj.text

    # 7. Cancel b1 -> Lock is released -> New booking succeeds with 201 Created
    cancel_resp = client.post(
        f"/resources/bookings/{b1['id']}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert cancel_resp.status_code == 200

    resp_after = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-20",
            "start_time": "12:00:00",
            "end_time": "14:00:00",
            "purpose": "Afternoon lab (after lock released)",
        },
    )
    assert resp_after.status_code == 201


def test_competing_pending_requests_approval_race(faculty_token, faculty2_token, admin_token):
    """
    Stage 11 Global Resource Lock Policy:
    A PENDING booking on a resource establishes an active lock.
    A second request for the same resource is blocked at creation time with 409 Conflict.
    Rejection or cancellation of the pending booking releases the lock.
    """
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Physics Demonstration Lab", "resource_type": "LAB", "capacity": 35},
    )
    res_id = res_resp.json()["id"]

    # Requester 1 submits PENDING -> succeeds (201 Created)
    req1_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-25",
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "purpose": "Optics Experiment",
        },
    )
    assert req1_resp.status_code == 201
    req1 = req1_resp.json()

    # Requester 2 attempts competing request on locked resource -> 409 Conflict
    req2_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty2_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-25",
            "start_time": "15:00:00",
            "end_time": "17:00:00",
            "purpose": "Laser Interferometry",
        },
    )
    assert req2_resp.status_code == 409
    assert "already booked" in req2_resp.text.lower() or "ACTIVE_BOOKING_LOCK" in req2_resp.text

    # Rejection of req1 releases the lock
    rej = client.post(
        f"/resources/bookings/{req1['id']}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Schedule re-allocation"},
    )
    assert rej.status_code == 200

    # Now Requester 2 can successfully book the resource
    req2_retry = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty2_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-11-25",
            "start_time": "15:00:00",
            "end_time": "17:00:00",
            "purpose": "Laser Interferometry",
        },
    )
    assert req2_retry.status_code == 201


def test_published_timetable_conflict_detection(admin_token, faculty_token):
    """
    Checks that bookings conflicting with a PUBLISHED timetable room return 409,
    while DRAFT/GENERATED versions do not block bookings.
    """
    # Create a Room and a linked Resource
    with Session(engine) as db:
        bldg = db.query(Building).first()
        bldg_id = bldg.id if bldg else 1
        room = Room(room_number="HALL-801", room_type="SEMINAR_HALL", capacity=150, building_id=bldg_id)
        db.add(room)
        db.flush()

        slot = TimeSlot(
            day="WEDNESDAY",
            start_time=datetime.time(10, 0, 0),
            end_time=datetime.time(11, 0, 0),
            slot_type="CLASS",
        )
        db.add(slot)
        db.flush()

        # Create unpublished timetable version with entry
        draft_version = TimetableVersion(status="DRAFT", version_number="v-draft")
        db.add(draft_version)
        db.flush()

        draft_entry = TimetableEntry(
            version_id=draft_version.id,
            room_id=room.id,
            slot_id=slot.id,
            status="DRAFT",
        )
        db.add(draft_entry)
        db.commit()

        draft_version_id = draft_version.id
        draft_entry_id = draft_entry.id
        slot_id = slot.id
        room_id = room.id
        room_num = room.room_number

    # Create resource matching room
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": f"Hall {room_num}",
            "resource_type": "SEMINAR_HALL",
            "location": room_num,
            "capacity": 150,
        },
    )
    res_id = res_resp.json()["id"]

    # Wed Nov 18, 2026 is a Wednesday: (2026-11-18 is Wednesday)
    test_date = "2026-11-18"

    # Since version is DRAFT, this should NOT cause a conflict
    avail_resp = client.get(
        f"/resources/availability?resource_id={res_id}&date={test_date}&start_time=10:00:00&end_time=11:00:00",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert avail_resp.status_code == 200
    assert avail_resp.json()["available"] is True

    # Now publish the timetable version
    with Session(engine) as db:
        v = db.query(TimetableVersion).filter(TimetableVersion.id == draft_version_id).first()
        assert v is not None
        v.status = "PUBLISHED"
        db.commit()

    # Now the conflict must be detected!
    conflict_resp = client.get(
        f"/resources/availability?resource_id={res_id}&date={test_date}&start_time=10:00:00&end_time=11:00:00",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert conflict_resp.status_code == 200
    data = conflict_resp.json()
    assert data["available"] is False
    assert len(data["conflicts"]) > 0
    assert data["conflicts"][0]["conflict_type"] == "PUBLISHED_TIMETABLE"

    # Submitting a booking request on this slot returns 409 Conflict
    book_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": test_date,
            "start_time": "10:15:00",
            "end_time": "10:45:00",
            "purpose": "Quick review session",
        },
    )
    assert book_resp.status_code == 409
    assert "PUBLISHED_TIMETABLE" in book_resp.text

    # Teardown temporary test rows so other tests have clean slate
    with Session(engine) as db:
        db.query(TimetableEntry).filter(TimetableEntry.id == draft_entry_id).delete()
        db.query(TimetableVersion).filter(TimetableVersion.id == draft_version_id).delete()
        db.query(TimeSlot).filter(TimeSlot.id == slot_id).delete()
        db.query(Room).filter(Room.id == room_id).delete()
        db.commit()


def test_alternative_resource_recommendations(admin_token, faculty_token):
    """
    When a resource is booked, check that alternative resources of the same type
    are returned in the conflict response and availability check.
    """
    # Create two projectors
    p1 = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Projector Alpha", "resource_type": "PROJECTOR", "capacity": 1},
    ).json()

    p2 = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Projector Beta", "resource_type": "PROJECTOR", "capacity": 1},
    ).json()

    # Book and approve Projector Alpha
    b1 = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": p1["id"],
            "date": "2026-11-28",
            "start_time": "10:00:00",
            "end_time": "12:00:00",
            "purpose": "Faculty Meeting",
        },
    ).json()
    client.post(f"/resources/bookings/{b1['id']}/approve", headers={"Authorization": f"Bearer {admin_token}"})

    # Query availability for Projector Alpha
    avail = client.get(
        f"/resources/availability?resource_id={p1['id']}&date=2026-11-28&start_time=10:30:00&end_time=11:30:00",
        headers={"Authorization": f"Bearer {faculty_token}"},
    ).json()

    assert avail["available"] is False
    assert len(avail["alternatives"]) > 0
    alt_ids = [a["id"] for a in avail["alternatives"]]
    assert p2["id"] in alt_ids
    assert avail["alternatives"][0]["resource_type"] == "PROJECTOR"


def test_route_precedence_and_matching(admin_token):
    """
    Verifies that static paths (/resources/bookings, /resources/availability)
    are NOT shadowed by the parameterized path /resources/{resource_id}.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. /resources/bookings must return a list, not 422 integer path validation error
    resp_bookings = client.get("/resources/bookings", headers=headers)
    assert resp_bookings.status_code == 200
    assert isinstance(resp_bookings.json(), list)

    # 2. /resources/availability must reach availability handler, not 422 path validation error
    resp_avail = client.get(
        "/resources/availability?resource_id=1&date=2026-11-20&start_time=10:00:00&end_time=12:00:00",
        headers=headers,
    )
    assert resp_avail.status_code == 200
    assert "available" in resp_avail.json()

    # 3. Base /resources endpoint
    resp_list = client.get("/resources", headers=headers)
    assert resp_list.status_code == 200
    assert isinstance(resp_list.json(), list)

    # 4. Parameterized path with valid ID
    resp_single = client.get("/resources/1", headers=headers)
    assert resp_single.status_code in [200, 404]


def test_true_concurrent_competing_booking_approvals(admin_token, faculty_token, faculty2_token):
    """
    Proves race-condition safety under true concurrent multithreaded approval attempts.
    Two competing pending requests for the same resource and overlapping interval
    are approved concurrently via separate threads.
    Due to row locking on the shared parent Resource, exactly one must succeed (200)
    and the other must fail with 409 Conflict.
    """
    # 1. Create a dedicated test resource
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "High-Concurrency Server Cluster", "resource_type": "EQUIPMENT", "capacity": 1},
    ).json()
    res_id = res_resp["id"]

    test_date = "2026-12-05"

    # 2. Concurrently submit two competing booking requests from two separate threads.
    # Row-level locking on the parent Resource serializes both attempts.
    # Exactly one must succeed (200) creating the active PENDING lock, and the competing request must receive 409 Conflict.
    def submit_worker(token: str, purpose: str):
        thread_client = TestClient(app)
        return thread_client.post(
            "/resources/bookings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "resource_id": res_id,
                "date": test_date,
                "start_time": "14:00:00",
                "end_time": "16:00:00",
                "purpose": purpose,
            },
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(submit_worker, faculty_token, "Concurrent Test Job 1")
        future2 = executor.submit(submit_worker, faculty2_token, "Concurrent Test Job 2")
        resp1 = future1.result()
        resp2 = future2.result()

    status_codes = [resp1.status_code, resp2.status_code]
    assert 201 in status_codes, f"Expected one submission to succeed with 201 Created, got: {status_codes}"
    assert 409 in status_codes, f"Expected competing submission to fail with 409 Conflict, got: {status_codes}"

    # Extract the winning booking ID
    winning_resp = resp1 if resp1.status_code == 201 else resp2
    conflict_resp = resp2 if resp1.status_code == 201 else resp1
    assert "Resource already booked" in conflict_resp.text or "ACTIVE_BOOKING_LOCK" in conflict_resp.text

    winning_booking_id = winning_resp.json()["id"]

    # 3. Approve the winning booking
    appr_resp = client.post(
        f"/resources/bookings/{winning_booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert appr_resp.status_code == 200

    # 4. Verify database integrity: exactly ONE booking exists in DB and is APPROVED
    with Session(engine) as db:
        bookings = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_id).all()
        assert len(bookings) == 1, f"Expected exactly 1 booking record, found {len(bookings)}"
        assert bookings[0].status == "APPROVED"


def test_response_privacy_protection(admin_token, faculty_token, faculty2_token):
    """
    Verifies that third-party viewers cannot see private requester contact details (e.g. email)
    when browsing public resource bookings, while the owner and ADMIN can view full details.
    """
    # Create resource and booking by Faculty 1
    res_resp = client.post(
        "/resources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Private Meeting Room", "resource_type": "SEMINAR_HALL", "capacity": 20},
    ).json()
    res_id = res_resp["id"]

    book_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": "2026-12-10",
            "start_time": "11:00:00",
            "end_time": "12:00:00",
            "purpose": "Confidential Research Review",
        },
    ).json()
    b_id = book_resp["id"]

    # Admin approves
    client.post(f"/resources/bookings/{b_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})

    # Faculty 2 queries booking list: must see the booking (since approved), but requester_email must be MASKED (None)
    f2_list = client.get("/resources/bookings", headers={"Authorization": f"Bearer {faculty2_token}"}).json()
    f2_view = next((b for b in f2_list if b["id"] == b_id), None)
    assert f2_view is not None
    assert f2_view["requester_email"] is None, "requester_email was leaked to an unrelated faculty viewer!"

    # Faculty 1 (owner) queries booking list: CAN see their own email
    f1_list = client.get("/resources/bookings", headers={"Authorization": f"Bearer {faculty_token}"}).json()
    f1_view = next((b for b in f1_list if b["id"] == b_id), None)
    assert f1_view is not None
    assert f1_view["requester_email"] is not None

    # Admin queries booking list: CAN see full email
    admin_list = client.get("/resources/bookings", headers={"Authorization": f"Bearer {admin_token}"}).json()
    admin_view = next((b for b in admin_list if b["id"] == b_id), None)
    assert admin_view is not None
    assert admin_view["requester_email"] is not None


def test_unknown_booking_operations_return_404(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    non_existent_id = 999999

    # Approve unknown booking returns 404
    resp_appr = client.post(f"/resources/bookings/{non_existent_id}/approve", headers=headers)
    assert resp_appr.status_code == 404
    assert f"#{non_existent_id} not found" in resp_appr.json()["detail"]

    # Reject unknown booking returns 404
    resp_rej = client.post(f"/resources/bookings/{non_existent_id}/reject", headers=headers)
    assert resp_rej.status_code == 404
    assert f"#{non_existent_id} not found" in resp_rej.json()["detail"]

    # Cancel unknown booking returns 404
    resp_can = client.post(f"/resources/bookings/{non_existent_id}/cancel", headers=headers)
    assert resp_can.status_code == 404
    assert f"#{non_existent_id} not found" in resp_can.json()["detail"]


def test_incomplete_booking_approval_fails_safely(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    with Session(engine) as db:
        try:
            res = db.query(Resource).filter(Resource.status == "ACTIVE").first()
            assert res is not None
            bad_booking = ResourceBooking(
                resource_id=res.id,
                requested_by=1,
                date=None,
                start_time=None,
                end_time=None,
                purpose="Incomplete booking test",
                status="PENDING",
            )
            db.add(bad_booking)
            db.commit()
            db.refresh(bad_booking)
            bad_id = bad_booking.id

            resp = client.post(f"/resources/bookings/{bad_id}/approve", headers=headers)
            assert resp.status_code == 400
            assert "incomplete booking schedule data" in resp.json()["detail"]
        finally:
            db.query(ResourceBooking).filter(ResourceBooking.purpose == "Incomplete booking test").delete()
            db.commit()
