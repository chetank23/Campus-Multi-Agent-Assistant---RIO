"""
tests/agents/test_realtime_operations.py
----------------------------------------
Comprehensive test suite for Real-Time AI Operations Capability in RIO Campus Assistant:
1. Authoritative Action Registry:
   - Discoverable, typed action definitions for READ and WRITE operations.
   - Strict role boundaries (ADMIN, FACULTY, STUDENT).
   - Parameter validation and explicit confirmation rules.
2. Operation Proposal Store:
   - Single-use, high-entropy tokens (op_prop_<hex>).
   - Pending tracking, idempotency, discard, and expiration.
3. Conversational Modifications & Multi-turn Interactions:
   - "Change it to Thursday" / "Change to Friday" (Date mutation with live conflict validation).
   - "Use Room B204 instead" (Facility mutation with live availability validation).
   - "Show me another option" (Alternative resource shift).
   - "No, cancel that" (Proposal discard and acknowledgement).
   - "Yes, proceed" (Direct active proposal execution).
4. Administrative Operations & CRUD Lifecycle:
   - Resource booking approval and rejection (Prepare -> Review -> Confirm -> Execute -> Verify DB).
   - Room metadata updates (Prepare -> Review -> Confirm -> Execute -> Verify DB).
   - Timetable finalization and publication (Prepare -> Review -> Confirm -> Execute -> Verify DB).
   - Role enforcement (Students blocked from Admin operations).
5. Real-Time Data Integrity & Concurrency:
   - Stale proposal detection and rejection when live data changes before confirmation.
   - Global resource lock enforcement.
6. Honest Refusal of Unsupported Operations:
   - Refusal of grade modifications, fee refunds, and entity deletions without backend capabilities.
"""

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Room, Building
from backend.models.timetable import TimetableVersion
from agents.action_registry import action_registry
from agents.common.operation_proposal_store import operation_proposal_store
from agents.resource_agent.proposal_store import resource_proposal_store
from agents.supervisor.agent import execute_supervisor, classify_intent
from agents.common.formatter import sanitize_plain_english

client = TestClient(app)


def assert_plain_english(text: str):
    assert text is not None and len(text.strip()) > 0
    # Prohibit markdown headings
    for line in text.split("\n"):
        assert not line.strip().startswith(("#", "##", "###")), f"Heading found: {line}"
    # Prohibit raw markdown bold/italic asterisks
    assert "**" not in text, f"Markdown bold found: {text}"


# ── Auth Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_token():
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]


# ── 1. Action Registry Tests ──────────────────────────────────────────────────

def test_action_registry_discovery_and_categorization():
    """Verifies that all supported actions are registered with complete schemas and separated into READ vs WRITE."""
    all_actions = action_registry.get_actions()
    assert len(all_actions) >= 20

    read_actions = action_registry.list_actions(category="READ")
    write_actions = action_registry.list_actions(category="WRITE")

    assert len(read_actions) >= 12
    assert len(write_actions) >= 8

    # Verify write actions mandate confirmation and designate authoritative services
    for action in write_actions:
        assert action.requires_confirmation is True
        assert action.authoritative_service != ""
        assert len(action.permitted_roles) > 0
        assert action.purpose != ""


def test_action_registry_role_filtering():
    """Verifies that actions are correctly restricted by role."""
    admin_actions = action_registry.list_actions(role="ADMIN")
    faculty_actions = action_registry.list_actions(role="FACULTY")
    student_actions = action_registry.list_actions(role="STUDENT")

    admin_names = {a.name for a in admin_actions}
    faculty_names = {a.name for a in faculty_actions}
    student_names = {a.name for a in student_actions}

    # Admin should have administrative write actions
    assert "APPROVE_RESOURCE_BOOKING" in admin_names
    assert "REJECT_RESOURCE_BOOKING" in admin_names
    assert "UPDATE_ROOM" in admin_names
    assert "FINALIZE_TIMETABLE" in admin_names
    assert "PUBLISH_TIMETABLE" in admin_names

    # Faculty should NOT have administrative write actions
    assert "APPROVE_RESOURCE_BOOKING" not in faculty_names
    assert "UPDATE_ROOM" not in faculty_names
    assert "FINALIZE_TIMETABLE" not in faculty_names

    # Student should NOT have administrative write actions
    assert "APPROVE_RESOURCE_BOOKING" not in student_names
    assert "UPDATE_ROOM" not in student_names
    assert "FINALIZE_TIMETABLE" not in student_names


def test_action_registry_validation():
    """Verifies action call validation with valid, invalid, and unauthorized inputs."""
    valid, err = action_registry.validate_action_call("UPDATE_ROOM", "ADMIN", {"room_id": 1, "capacity": 50})
    assert valid is True
    assert err is None

    # Student cannot call UPDATE_ROOM
    valid, err = action_registry.validate_action_call("UPDATE_ROOM", "STUDENT", {"room_id": 1, "capacity": 50})
    assert valid is False
    assert err is not None and ("denied" in err.lower() or "requires privilege" in err.lower())

    # Non-existent action
    valid, err = action_registry.validate_action_call("CHANGE_STUDENT_GRADE", "ADMIN", {})
    assert valid is False
    assert err is not None and "not recognized" in err.lower()


def test_action_registry_help_intent(student_token, admin_token):
    """Verifies action registry help returns role-specific supported actions in plain English."""
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": "What actions can you perform?"},
    )
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    assert_plain_english(reply)
    assert "STUDENT" in reply
    assert "Query and Read Operations:" in reply

    resp_admin = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "What operations can you do?"},
    )
    assert resp_admin.status_code == 200
    admin_reply = resp_admin.json()["reply"]
    assert "ADMIN" in admin_reply
    assert "APPROVE_RESOURCE_BOOKING" in admin_reply or "Approve" in admin_reply


# ── 2. Operation Proposal Store Tests ─────────────────────────────────────────

def test_operation_proposal_store_lifecycle():
    """Verifies proposal creation, retrieval, single-use idempotency, and discard."""
    prop = operation_proposal_store.create_proposal(
        user_id=1,
        role="ADMIN",
        action_name="UPDATE_ROOM",
        entity_type="Room",
        entity_id=101,
        entity_name="Room 101",
        changes={"capacity": 55},
        consequences="Updates Room 101 capacity to 55 seats.",
    )
    assert prop.proposal_id.startswith("op_prop_")
    assert prop.consumed is False

    # Check latest pending
    latest = operation_proposal_store.get_latest_pending_proposal(1)
    assert latest is not None
    assert latest.proposal_id == prop.proposal_id

    # Consume proposal
    ok, c_prop, c_err = operation_proposal_store.consume_proposal(prop.proposal_id, 1)
    assert ok is True
    assert c_prop is not None and c_prop.consumed is True

    # Cannot consume again (single-use idempotency)
    ok2, _, _ = operation_proposal_store.consume_proposal(prop.proposal_id, 1)
    assert ok2 is False

    # Discard test
    prop2 = operation_proposal_store.create_proposal(
        user_id=1,
        role="ADMIN",
        action_name="UPDATE_ROOM",
        entity_type="Room",
        entity_id=102,
        entity_name="Room 102",
        changes={"capacity": 60},
        consequences="Updates Room 102 capacity to 60 seats.",
    )
    assert operation_proposal_store.discard_proposal(prop2.proposal_id, 1) is True
    assert operation_proposal_store.get_proposal(prop2.proposal_id) is None


# ── 3. Conversational Modifications & Multi-turn Interactions ─────────────────

def test_follow_up_date_mutation(faculty_token):
    """
    Tests:
    1. User books facility on Monday -> proposal created.
    2. User says 'Change it to Thursday' (or specific date) -> old proposal discarded, new proposal created on new date.
    """
    with Session(engine) as db:
        res = Resource(name="Ops Test Hall Alpha", resource_type="SEMINAR_HALL", capacity=80, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        r_name = res.name

    future_base = datetime.date.today() + datetime.timedelta(days=20)
    initial_date = future_base.isoformat()
    new_date = (future_base + datetime.timedelta(days=3)).isoformat()

    # Step 1: Initial booking proposal
    r1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {r_name} on {initial_date} from 10:00 to 12:00 for AI Workshop"},
    )
    assert r1.status_code == 200
    p1 = r1.json().get("proposal")
    assert p1 is not None
    old_id = p1["proposal_id"]

    # Step 2: Follow-up date modification: "Change date to <new_date>"
    r2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Change date to {new_date}"},
    )
    assert r2.status_code == 200
    p2 = r2.json().get("proposal")
    assert p2 is not None
    assert p2["proposal_id"] != old_id
    assert p2["date"] == new_date
    assert "Reservation date updated" in r2.json()["reply"]

    # Old proposal should be discarded
    assert resource_proposal_store.get_proposal(old_id) is None


def test_follow_up_facility_mutation(faculty_token):
    """
    Tests:
    1. User books Hall 1 -> proposal created.
    2. User says 'Use Hall 2 instead' -> old proposal discarded, new proposal created for Hall 2.
    """
    with Session(engine) as db:
        res1 = Resource(name="Ops Facility One", resource_type="SEMINAR_HALL", capacity=50, status="ACTIVE")
        res2 = Resource(name="Ops Facility Two", resource_type="SEMINAR_HALL", capacity=70, status="ACTIVE")
        db.add_all([res1, res2])
        db.commit()
        db.refresh(res1)
        db.refresh(res2)
        r1_name = res1.name
        r2_name = res2.name

    target_date = (datetime.date.today() + datetime.timedelta(days=22)).isoformat()

    # Step 1: Initial proposal for res1
    r1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {r1_name} on {target_date} from 14:00 to 16:00 for Seminar"},
    )
    assert r1.status_code == 200
    p1 = r1.json().get("proposal")
    assert p1 is not None
    old_id = p1["proposal_id"]

    # Step 2: Follow-up switch: "Use Ops Facility Two instead"
    r2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Use {r2_name} instead"},
    )
    assert r2.status_code == 200
    p2 = r2.json().get("proposal")
    assert p2 is not None
    assert p2["proposal_id"] != old_id
    assert p2["resource_name"] == r2_name
    assert "Facility changed" in r2.json()["reply"]


def test_follow_up_alternative_shift(faculty_token):
    """Tests 'Show me another option' shifts to an alternative available resource."""
    with Session(engine) as db:
        res1 = Resource(name="Ops Shift Lab A", resource_type="LAB", capacity=40, status="ACTIVE")
        res2 = Resource(name="Ops Shift Lab B", resource_type="LAB", capacity=45, status="ACTIVE")
        db.add_all([res1, res2])
        db.commit()
        db.refresh(res1)
        db.refresh(res2)
        r1_name = res1.name

    target_date = (datetime.date.today() + datetime.timedelta(days=24)).isoformat()

    # Step 1: Request initial proposal
    r1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {r1_name} on {target_date} from 09:00 to 11:00 for Lab Exam"},
    )
    assert r1.status_code == 200
    p1 = r1.json().get("proposal")
    assert p1 is not None

    # Step 2: Say "Show me another option"
    r2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": "Show me another option"},
    )
    assert r2.status_code == 200
    p2 = r2.json().get("proposal")
    assert p2 is not None
    assert p2["proposal_id"] != p1["proposal_id"]
    assert "Switched facility to recommended alternative" in r2.json()["reply"]


def test_follow_up_cancellation_and_proceed(faculty_token):
    """
    Tests:
    1. 'No, cancel that' discards proposal.
    2. Request new proposal, then 'Yes, proceed' executes it without token.
    """
    with Session(engine) as db:
        res = Resource(name="Ops Cancel Room", resource_type="SEMINAR_HALL", capacity=30, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        r_name = res.name

    target_date = (datetime.date.today() + datetime.timedelta(days=26)).isoformat()

    # Turn 1: Request booking
    r1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {r_name} on {target_date} from 10:00 to 12:00 for Review"},
    )
    assert r1.status_code == 200
    p1 = r1.json().get("proposal")
    assert p1 is not None
    prop_id = p1["proposal_id"]

    # Turn 2: Cancel it
    r2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": "No, cancel that"},
    )
    assert r2.status_code == 200
    assert "discarded" in r2.json()["reply"].lower()
    assert resource_proposal_store.get_proposal(prop_id) is None

    # Turn 3: Request again
    r3 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {r_name} on {target_date} from 10:00 to 12:00 for Review"},
    )
    assert r3.status_code == 200
    p3 = r3.json().get("proposal")
    assert p3 is not None

    # Turn 4: Confirm with "Yes, proceed"
    r4 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": "Yes, proceed"},
    )
    assert r4.status_code == 200
    assert "submitted successfully" in r4.json()["reply"].lower()


# ── 4. Administrative Operations & CRUD Lifecycle ─────────────────────────────

def test_admin_booking_approval_lifecycle(admin_token, faculty_token):
    """
    Tests:
    1. Faculty requests booking.
    2. Admin asks to approve booking #ID -> Operation Proposal (op_prop_).
    3. Admin says 'Yes, proceed' -> executes approval, verifies status == APPROVED in DB.
    """
    with Session(engine) as db:
        res = Resource(name="Ops Approval Hall", resource_type="SEMINAR_HALL", capacity=100, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        res_id = res.id

    b_date = (datetime.date.today() + datetime.timedelta(days=28)).isoformat()

    # Step 1: Create pending booking via API
    b_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": b_date,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "purpose": "Annual Department Meeting",
        },
    )
    assert b_resp.status_code == 201
    booking_id = b_resp.json()["id"]

    # Step 2: Admin prepares approval
    appr_prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"Approve booking #{booking_id}"},
    )
    assert appr_prep.status_code == 200
    prep_data = appr_prep.json()
    assert prep_data["proposal"] is not None
    assert prep_data["proposal"]["proposal_id"].startswith("op_prop_")
    assert prep_data["proposal"]["action_name"] == "APPROVE_RESOURCE_BOOKING"
    assert "Approval Proposal" in prep_data["reply"]

    # Step 3: Admin confirms: "Yes, proceed"
    appr_exec = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Yes, proceed"},
    )
    assert appr_exec.status_code == 200
    exec_data = appr_exec.json()
    assert "approved successfully" in exec_data["reply"].lower()

    # Step 4: Verify persistence directly in database
    with Session(engine) as db:
        db_b = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
        assert db_b is not None
        assert db_b.status == "APPROVED"


def test_admin_booking_rejection_lifecycle(admin_token, faculty_token):
    """
    Tests:
    1. Faculty requests booking.
    2. Admin asks to reject booking #ID -> Operation Proposal.
    3. Admin confirms -> executes rejection, verifies status == REJECTED in DB.
    """
    with Session(engine) as db:
        res = Resource(name="Ops Rejection Hall", resource_type="SEMINAR_HALL", capacity=100, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        res_id = res.id

    b_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    b_resp = client.post(
        "/resources/bookings",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={
            "resource_id": res_id,
            "date": b_date,
            "start_time": "13:00:00",
            "end_time": "15:00:00",
            "purpose": "Faculty Orientation",
        },
    )
    assert b_resp.status_code == 201
    booking_id = b_resp.json()["id"]

    # Admin prepares rejection
    rej_prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"Reject booking #{booking_id}"},
    )
    assert rej_prep.status_code == 200
    assert rej_prep.json()["proposal"] is not None
    assert rej_prep.json()["proposal"]["action_name"] == "REJECT_RESOURCE_BOOKING"

    # Admin confirms
    rej_exec = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Yes, proceed"},
    )
    assert rej_exec.status_code == 200
    assert "rejected" in rej_exec.json()["reply"].lower()

    # Verify DB
    with Session(engine) as db:
        db_b = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
        assert db_b is not None
        assert db_b.status == "REJECTED"


def test_admin_room_metadata_update_lifecycle(admin_token, student_token):
    """
    Tests:
    1. Admin asks to update room capacity -> Operation Proposal.
    2. Admin confirms -> room capacity updated and verified in DB.
    3. Student attempts room update -> rejected by authorization.
    """
    with Session(engine) as db:
        b = db.query(Building).first()
        if not b:
            b = Building(name="Main Tech Block", code="MTB")
            db.add(b)
            db.commit()
            db.refresh(b)
        room = Room(room_number="R-999", building_id=b.id, capacity=35, room_type="CLASSROOM")
        db.add(room)
        db.commit()
        db.refresh(room)
        room_id = room.id
        room_num = room.room_number

    # Step 1: Admin prepares room update
    r_prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"Update room {room_num} capacity to 65"},
    )
    assert r_prep.status_code == 200
    assert r_prep.json()["proposal"] is not None
    assert r_prep.json()["proposal"]["action_name"] == "UPDATE_ROOM"
    assert "Room Metadata Update Proposal" in r_prep.json()["reply"]

    # Step 2: Admin confirms
    r_exec = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Yes, proceed"},
    )
    assert r_exec.status_code == 200
    assert "updated successfully" in r_exec.json()["reply"].lower()

    # Verify DB persistence
    with Session(engine) as db:
        db_r = db.query(Room).filter(Room.id == room_id).first()
        assert db_r is not None
        assert db_r.capacity == 65

    # Step 3: Student attempts update -> authorization error
    stu_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": f"Update room {room_num} capacity to 80"},
    )
    assert stu_resp.status_code == 200
    assert "only university administrators" in stu_resp.json()["reply"].lower()


def test_admin_timetable_finalization_lifecycle(admin_token, student_token):
    """
    Tests:
    1. Timetable version in DRAFT state.
    2. Admin says 'Finalize timetable version {id}' -> Operation Proposal.
    3. Admin confirms -> status becomes DRAFT_FINALIZED, verified in DB.
    4. Student attempts finalization -> blocked by authorization.
    """
    with Session(engine) as db:
        tv = TimetableVersion(
            version_number="1.0",
            academic_year_id=1,
            status="VALIDATED",
            created_by=1,
        )
        db.add(tv)
        db.commit()
        db.refresh(tv)
        tv_id = tv.id

    # Step 1: Student attempt -> blocked
    stu_res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": f"Finalize timetable version {tv_id}"},
    )
    assert stu_res.status_code == 200
    assert "only university administrators" in stu_res.json()["reply"].lower()

    # Step 2: Admin prepares finalization
    adm_prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"Finalize timetable version {tv_id}"},
    )
    assert adm_prep.status_code == 200
    assert adm_prep.json()["proposal"] is not None
    assert adm_prep.json()["proposal"]["action_name"] == "FINALIZE_TIMETABLE"

    # Step 3: Admin confirms
    adm_exec = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Yes, proceed"},
    )
    assert adm_exec.status_code == 200
    assert "finalized successfully" in adm_exec.json()["reply"].lower()

    # Step 4: Verify persistence in DB
    with Session(engine) as db:
        db_tv = db.query(TimetableVersion).filter(TimetableVersion.id == tv_id).first()
        assert db_tv is not None
        assert db_tv.status == "FINALIZED"


def test_admin_timetable_publication_lifecycle(admin_token):
    """
    Tests:
    1. Timetable version in FINALIZED state.
    2. Admin says 'Publish timetable version {id}' -> Operation Proposal.
    3. Admin confirms -> status becomes PUBLISHED, verified in DB.
    """
    with Session(engine) as db:
        tv = TimetableVersion(
            version_number="2.0",
            academic_year_id=1,
            status="FINALIZED",
            created_by=1,
        )
        db.add(tv)
        db.commit()
        db.refresh(tv)
        tv_id = tv.id

    # Step 1: Admin prepares publication
    adm_prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"Publish timetable version {tv_id}"},
    )
    assert adm_prep.status_code == 200
    assert adm_prep.json()["proposal"] is not None
    assert adm_prep.json()["proposal"]["action_name"] == "PUBLISH_TIMETABLE"

    # Step 2: Admin confirms
    adm_exec = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Yes, proceed"},
    )
    assert adm_exec.status_code == 200
    assert "published" in adm_exec.json()["reply"].lower() and "active campus-wide" in adm_exec.json()["reply"].lower()

    # Step 3: Verify persistence in DB
    with Session(engine) as db:
        db_tv = db.query(TimetableVersion).filter(TimetableVersion.id == tv_id).first()
        assert db_tv is not None
        assert db_tv.status == "PUBLISHED"


# ── 5. Real-Time Data Integrity & Concurrency ─────────────────────────────────

def test_stale_proposal_conflict_rejection(faculty_token, admin_token):
    """
    Verifies that if a resource becomes locked/unavailable AFTER a proposal is generated,
    attempting to confirm the proposal detects the conflict, rejects execution, and prevents double booking.
    """
    with Session(engine) as db:
        res = Resource(name="Ops Concurrency Hall", resource_type="SEMINAR_HALL", capacity=120, status="ACTIVE")
        db.add(res)
        db.commit()
        db.refresh(res)
        res_id = res.id
        res_name = res.name

    test_date = (datetime.date.today() + datetime.timedelta(days=35)).isoformat()

    # Step 1: Faculty creates proposal for test_date
    prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"Book {res_name} on {test_date} from 10:00 to 12:00 for Symposium"},
    )
    assert prep.status_code == 200
    prop_data = prep.json()["proposal"]
    assert prop_data is not None
    prop_id = prop_data["proposal_id"]

    # Step 2: Simultaneously, another user books and approves that facility in DB
    with Session(engine) as db:
        conflict_booking = ResourceBooking(
            resource_id=res_id,
            requested_by=1,
            date=datetime.date.fromisoformat(test_date),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            purpose="Urgent Executive Meeting",
            status="APPROVED",
        )
        db.add(conflict_booking)
        db.commit()

    # Step 3: Faculty now tries to confirm their stale proposal
    confirm_resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {faculty_token}"},
        json={"message": f"confirm {prop_id}"},
    )
    assert confirm_resp.status_code == 200
    reply = confirm_resp.json()["reply"]
    assert "no longer available" in reply.lower() or "conflict detected" in reply.lower() or "unable to confirm" in reply.lower()


# ── 6. Honest Refusal of Unsupported Operations ───────────────────────────────

def test_unsupported_operations_honest_refusal(student_token):
    """
    Verifies that out-of-scope domain operations (grades, fees, entity deletions)
    are politely and honestly refused without simulating database modifications.
    """
    unsupported_prompts = [
        ("Change my grade in CS101 to an A", "grade management"),
        ("Please refund my tuition fees", "fee payment and refund processing"),
        ("Delete the Computer Science department", "department deletion"),
        ("Drop all courses from catalog", "course deletion"),
        ("Reset password for user 12", "password management"),
    ]

    for msg, keyword in unsupported_prompts:
        resp = client.post(
            "/agents/chat",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"message": msg},
        )
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert_plain_english(reply)
        assert "cannot perform" in reply.lower()
        assert "no backend service" in reply.lower() or "no backend capability" in reply.lower()
        assert keyword.lower() in reply.lower()
