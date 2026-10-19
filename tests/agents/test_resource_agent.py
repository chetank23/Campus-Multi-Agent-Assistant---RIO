"""
tests/agents/test_resource_agent.py
-----------------------------------
Comprehensive test suite for Stage 9C: Advanced Intelligent Resource Agent.
Validates:
1. ResourceProposalStore lifecycle (token isolation, TTL expiry, single-use, cross-user denial).
2. Entity parsing (dates, relative days, intervals, capacity, purpose).
3. Authorization & role guards (non-admin approval blocking, admin guidance).
4. Targeted clarification prompts for incomplete requests.
5. Resource discovery and search without inventing inventory.
6. Real-time availability checks and conflict explanations with grounded alternatives.
7. End-to-end proposal creation, validation, and single-use confirmation.
8. Stale proposal rejection and replay protection.
9. User booking inspection and status tracking with privacy guards.
10. Authorized booking cancellation.
"""

import datetime
import pytest
from sqlalchemy.orm import Session
from backend.config import engine
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from agents.state.state import AgentState
from agents.resource_agent.proposal_store import (
    ResourceProposalStore,
    resource_proposal_store,
)
from agents.resource_agent.parser import (
    parse_date,
    parse_time_str,
    parse_time_interval,
    extract_resource_details,
)
from agents.resource_agent.agent import run_resource_agent
from agents.tools.resource_tools import (
    discover_resources_data,
    check_resource_availability_data,
    get_user_bookings_data,
    get_booking_details_data,
    execute_create_booking_data,
    execute_cancel_booking_data,
)


# ── 1. Proposal Store Lifecycle Tests ──────────────────────────────────────────

def test_resource_proposal_store_lifecycle_and_idempotency():
    store = ResourceProposalStore(ttl_seconds=900)
    prop = store.create_proposal(
        user_id=10,
        role="FACULTY",
        resource_id=1,
        resource_name="Seminar Hall A",
        resource_type="SEMINAR_HALL",
        location="Science Block",
        capacity=120,
        date="2026-11-15",
        start_time="14:00:00",
        end_time="16:00:00",
        purpose="Guest Lecture on Cloud Systems",
    )

    # 1. Format verification
    assert prop.proposal_id.startswith("res_prop_")
    assert len(prop.proposal_id) > 20

    # 2. Retrieval
    fetched = store.get_proposal(prop.proposal_id)
    assert fetched is not None
    assert fetched.resource_name == "Seminar Hall A"

    # 3. Cross-user access denial
    ok, _, err = store.consume_proposal(prop.proposal_id, user_id=999)
    assert ok is False
    assert "belongs to another user" in err

    # 4. Successful first-time consumption
    ok, consumed, err = store.consume_proposal(prop.proposal_id, user_id=10)
    assert ok is True
    assert consumed is not None
    assert consumed.consumed is True

    # 5. Duplicate submission blocked (Replay protection)
    ok_retry, _, err_retry = store.consume_proposal(prop.proposal_id, user_id=10)
    assert ok_retry is False
    assert "already been confirmed" in err_retry


def test_resource_proposal_store_expiry():
    store = ResourceProposalStore(ttl_seconds=-10)  # Expired upon creation
    prop = store.create_proposal(
        user_id=1,
        role="STUDENT",
        resource_id=2,
        resource_name="CSE Lab 1",
        resource_type="LAB",
        date="2026-11-20",
        start_time="10:00:00",
        end_time="12:00:00",
        purpose="Hackathon prep",
    )

    assert store.get_proposal(prop.proposal_id) is None
    ok, _, err = store.consume_proposal(prop.proposal_id, user_id=1)
    assert ok is False
    assert "expired" in err.lower() or "not found" in err.lower()


# ── 2. Entity Parsing Tests ───────────────────────────────────────────────────

def test_parser_dates_and_times():
    today = datetime.date(2026, 10, 18)

    # Relative dates
    assert parse_date("today", base_date=today) == today
    assert parse_date("tomorrow", base_date=today) == today + datetime.timedelta(days=1)
    assert parse_date("Book for tomorrow morning", base_date=today) == today + datetime.timedelta(days=1)

    # ISO date
    assert parse_date("2026-11-25") == datetime.date(2026, 11, 25)

    # Time token parsing
    assert parse_time_str("2pm") == datetime.time(14, 0)
    assert parse_time_str("10:30am") == datetime.time(10, 30)
    assert parse_time_str("14:00") == datetime.time(14, 0)

    # Interval parsing
    st, et = parse_time_interval("from 2pm to 4pm")
    assert st == datetime.time(14, 0)
    assert et == datetime.time(16, 0)

    st2, et2 = parse_time_interval("10:00 - 12:00")
    assert st2 == datetime.time(10, 0)
    assert et2 == datetime.time(12, 0)

    st3, et3 = parse_time_interval("at 2pm for 2 hours")
    assert st3 == datetime.time(14, 0)
    assert et3 == datetime.time(16, 0)

    # Resource details extraction
    details = extract_resource_details("Book Seminar Hall A with capacity of 100 for AI Workshop")
    assert details["resource_name"] == "Seminar Hall A"
    assert details["resource_type"] == "SEMINAR_HALL"
    assert details["min_capacity"] == 100
    assert "AI Workshop" in (details["purpose"] or "")


# ── 3. Administrative Authorization Guard ─────────────────────────────────────

def test_resource_agent_rejects_non_admin_approval():
    student_user = User(id=3, email="student@reva.edu.in", name="Student User", role="STUDENT")
    state: AgentState = {
        "user_id": 3,
        "role": "STUDENT",
        "message": "Approve booking #12",
    }
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=student_user)

    assert res["action_type"] == "ACCESS_DENIED"
    assert "Administrators" in res["final_response"]


def test_resource_agent_admin_approval_guidance():
    admin_user = User(id=1, email="admin@reva.edu.in", name="Admin User", role="ADMIN")
    state: AgentState = {
        "user_id": 1,
        "role": "ADMIN",
        "message": "Approve booking #12",
    }
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=admin_user)

    assert res["action_type"] == "ADMIN_GUIDANCE"
    assert "/admin/resources" in res["final_response"]


# ── 4. Clarification Prompts for Incomplete Requests ──────────────────────────

def test_resource_agent_asks_clarification():
    user = User(id=2, email="faculty@reva.edu.in", name="Faculty User", role="FACULTY")

    # Missing date and time
    state: AgentState = {"user_id": 2, "role": "FACULTY", "message": "Book Seminar Hall A"}
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=user)

    assert res["action_type"] == "CLARIFICATION_NEEDED"
    assert "booking date" in res["final_response"].lower()
    assert "time interval" in res["final_response"].lower()

    # Invalid time interval (end <= start)
    state_invalid: AgentState = {"user_id": 2, "role": "FACULTY", "message": "Book Seminar Hall A tomorrow from 4pm to 2pm"}
    with Session(engine) as db:
        res2 = run_resource_agent(state=state_invalid, db=db, user=user)

    assert res2["action_type"] == "CLARIFICATION_NEEDED"
    assert "end time must be after the start time" in res2["final_response"].lower()


# ── 5. Resource Discovery Queries ─────────────────────────────────────────────

def test_resource_discovery():
    user = User(id=2, email="faculty@reva.edu.in", name="Faculty User", role="FACULTY")
    state: AgentState = {"user_id": 2, "role": "FACULTY", "message": "Find seminar halls"}
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=user)

    assert res["action_type"] == "DISCOVERY_RESULTS"
    assert "Matching Campus Facilities" in res["final_response"] or "No Matching Resources" in res["final_response"]


# ── 6. Proposal Creation & Single-Use Confirmation ────────────────────────────

def test_booking_proposal_creation_and_confirmation():
    with Session(engine) as db:
        # 1. Fetch an existing active resource from seeded database
        res_entity = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        assert res_entity is not None, "At least one active resource must exist in seeded DB"

        target_date = datetime.date.today() + datetime.timedelta(days=7)
        faculty_user = db.query(User).filter(User.role == "FACULTY").first()
        if not faculty_user:
            faculty_user = User(id=99, email="test_faculty@reva.edu.in", name="Test Faculty", role="FACULTY")

        # 2. Ask to book facility
        msg = f"Book {res_entity.name} on {target_date.isoformat()} from 15:00 to 17:00 for Research Workshop"
        state: AgentState = {"user_id": faculty_user.id, "role": faculty_user.role, "message": msg}

        res = run_resource_agent(state=state, db=db, user=faculty_user)
        assert res["success"] is True
        assert res["action_type"] == "PROPOSAL_CREATED"
        proposal_dict = res.get("proposal")
        assert proposal_dict is not None
        proposal_id = proposal_dict["proposal_id"]
        assert proposal_id.startswith("res_prop_")

        # 3. Confirm proposal
        confirm_state: AgentState = {
            "user_id": faculty_user.id,
            "role": faculty_user.role,
            "message": f"confirm {proposal_id}",
        }
        confirm_res = run_resource_agent(state=confirm_state, db=db, user=faculty_user)
        assert confirm_res["success"] is True
        assert confirm_res["action_type"] == "BOOKING_CREATED"
        assert "Submitted Successfully" in confirm_res["final_response"]
        assert "PENDING" in confirm_res["final_response"]

        # 4. Attempting replay with the same proposal should fail
        replay_res = run_resource_agent(state=confirm_state, db=db, user=faculty_user)
        assert replay_res["success"] is False
        assert replay_res["action_type"] == "CONFIRMATION_REJECTED"
        assert "already been confirmed" in replay_res["final_response"]


# ── 7. Conflict Detection & Alternative Suggestions ───────────────────────────

def test_resource_conflict_detection_and_alternatives():
    with Session(engine) as db:
        # Find active resource
        res_entity = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        assert res_entity is not None

        test_date = datetime.date.today() + datetime.timedelta(days=14)
        user = db.query(User).filter(User.role == "FACULTY").first()
        assert user is not None

        # Create an APPROVED booking directly to simulate existing occupancy
        existing_booking = ResourceBooking(
            resource_id=res_entity.id,
            requested_by=user.id,
            date=test_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(12, 0),
            status="APPROVED",
            purpose="Existing Approved Conference",
        )
        db.add(existing_booking)
        db.commit()

        # Now ask availability for an overlapping interval: 11:00 to 13:00
        state: AgentState = {
            "user_id": user.id,
            "role": "FACULTY",
            "message": f"Check availability for {res_entity.name} on {test_date.isoformat()} from 11:00 to 13:00",
        }
        res = run_resource_agent(state=state, db=db, user=user)

        assert res["action_type"] == "RESOURCE_UNAVAILABLE"
        assert "Conflict Detected" in res["final_response"]
        assert "Overlaps with approved reservation" in res["final_response"]


# ── 8. User Bookings & Cancellation ───────────────────────────────────────────

def test_user_booking_history_and_cancellation():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "FACULTY").first()
        assert user is not None
        res_entity = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        assert res_entity is not None

        # Create a pending booking for this user
        booking = ResourceBooking(
            resource_id=res_entity.id,
            requested_by=user.id,
            date=datetime.date.today() + datetime.timedelta(days=21),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(16, 0),
            status="PENDING",
            purpose="Project Review Session",
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        # 1. Inspect "my bookings"
        state_list: AgentState = {"user_id": user.id, "role": user.role, "message": "show my bookings"}
        list_res = run_resource_agent(state=state_list, db=db, user=user)
        assert list_res["action_type"] == "BOOKINGS_LIST"
        assert f"#{booking.id}" in list_res["final_response"]

        # 2. Inspect specific booking details
        state_detail: AgentState = {"user_id": user.id, "role": user.role, "message": f"status of booking #{booking.id}"}
        detail_res = run_resource_agent(state=state_detail, db=db, user=user)
        assert detail_res["action_type"] == "BOOKING_DETAILS"
        assert "PENDING" in detail_res["final_response"]

        # 3. Cancel the booking
        state_cancel: AgentState = {"user_id": user.id, "role": user.role, "message": f"cancel booking #{booking.id}"}
        cancel_res = run_resource_agent(state=state_cancel, db=db, user=user)
        assert cancel_res["action_type"] == "BOOKING_CANCELLED"
        assert "CANCELLED" in cancel_res["final_response"]

        # Verify DB state
        db.refresh(booking)
        assert booking.status == "CANCELLED"


# ── 9. Dedicated Nullability & Incomplete Interval Regression Tests ───────────

def test_resource_agent_missing_date_only():
    user = User(id=2, email="faculty@reva.edu.in", name="Faculty User", role="FACULTY")
    # Date missing, interval provided
    state: AgentState = {"user_id": 2, "role": "FACULTY", "message": "Book Seminar Hall A from 2:00 PM to 4:00 PM"}
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=user)

    assert res["action_type"] == "CLARIFICATION_NEEDED"
    assert "booking date" in res["final_response"].lower()
    assert res.get("proposal") is None


def test_resource_agent_missing_time_interval_only():
    user = User(id=2, email="faculty@reva.edu.in", name="Faculty User", role="FACULTY")
    # Date provided, interval missing
    state: AgentState = {"user_id": 2, "role": "FACULTY", "message": "Book Seminar Hall A tomorrow for Research Meeting"}
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=user)

    assert res["action_type"] == "CLARIFICATION_NEEDED"
    assert "time interval" in res["final_response"].lower()
    assert res.get("proposal") is None


def test_resource_agent_missing_resource_only():
    user = User(id=2, email="faculty@reva.edu.in", name="Faculty User", role="FACULTY")
    # Date and interval provided, resource missing
    state: AgentState = {"user_id": 2, "role": "FACULTY", "message": "Book tomorrow from 2:00 PM to 4:00 PM for Team Sync"}
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=user)

    assert res["action_type"] == "CLARIFICATION_NEEDED"
    assert "specific facility" in res["final_response"].lower()
    assert res.get("proposal") is None


def test_resource_agent_equal_start_and_end_interval_rejected():
    user = User(id=2, email="faculty@reva.edu.in", name="Faculty User", role="FACULTY")
    state: AgentState = {"user_id": 2, "role": "FACULTY", "message": "Book Seminar Hall A tomorrow from 14:00 to 14:00"}
    with Session(engine) as db:
        res = run_resource_agent(state=state, db=db, user=user)

    assert res["action_type"] == "CLARIFICATION_NEEDED"
    assert "end time must be after the start time" in res["final_response"].lower()
    assert res.get("proposal") is None


def test_resource_agent_no_booking_write_on_informational_query():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "FACULTY").first()
        assert user is not None
        res_entity = db.query(Resource).filter(Resource.status == "ACTIVE").first()
        assert res_entity is not None

        initial_count = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_entity.id).count()

        check_date = datetime.date.today() + datetime.timedelta(days=30)
        state: AgentState = {
            "user_id": user.id,
            "role": "FACULTY",
            "message": f"Is {res_entity.name} available on {check_date.isoformat()} from 10:00 to 12:00?",
        }
        res = run_resource_agent(state=state, db=db, user=user)

        assert res["action_type"] == "AVAILABILITY_CONFIRMED"
        assert res.get("proposal") is None

        # Verify DB writes did NOT happen
        current_count = db.query(ResourceBooking).filter(ResourceBooking.resource_id == res_entity.id).count()
        assert current_count == initial_count


def test_resource_agent_confirmation_with_corrupted_interval():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "FACULTY").first()
        assert user is not None

        # Create proposal with invalid end_time <= start_time
        prop = resource_proposal_store.create_proposal(
            user_id=user.id,
            role=user.role,
            resource_id=1,
            resource_name="Seminar Hall A",
            resource_type="SEMINAR_HALL",
            date="2026-11-20",
            start_time="16:00:00",
            end_time="14:00:00",  # Reversed!
            purpose="Invalid Session",
        )

        state: AgentState = {
            "user_id": user.id,
            "role": user.role,
            "message": f"confirm {prop.proposal_id}",
        }
        res = run_resource_agent(state=state, db=db, user=user)

        assert res["success"] is False
        assert res["action_type"] == "CONFIRMATION_REJECTED"
        assert "invalid" in res["final_response"].lower()


def test_resource_agent_confirmation_with_corrupted_date_format():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "FACULTY").first()
        assert user is not None

        # Create proposal with non-ISO date string
        prop = resource_proposal_store.create_proposal(
            user_id=user.id,
            role=user.role,
            resource_id=1,
            resource_name="Seminar Hall A",
            resource_type="SEMINAR_HALL",
            date="not-an-iso-date",
            start_time="14:00:00",
            end_time="16:00:00",
            purpose="Corrupted Date Session",
        )

        state: AgentState = {
            "user_id": user.id,
            "role": user.role,
            "message": f"confirm {prop.proposal_id}",
        }
        res = run_resource_agent(state=state, db=db, user=user)

        assert res["success"] is False
        assert res["action_type"] == "CONFIRMATION_REJECTED"
        assert "invalid date or time format" in res["final_response"].lower()
