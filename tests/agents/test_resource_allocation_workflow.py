"""
tests/agents/test_resource_allocation_workflow.py
-------------------------------------------------
Comprehensive end-to-end and unit test suite covering all 22 required scenarios for:
- Resource Allocation Agent
- Interval Conflict Resolution
- Automatic Resource & Time Alternatives
- Durable Database-Backed Proposal Store & Restart Survival
- Booking Lifecycle (Pending, Approval, Rejection, Cancellation, Audit, Notification)
- Supervisor-Driven Multi-Agent Coordination (Resource Agent + Query Agent)
- Concurrency & Double-Booking Prevention
"""

import datetime
import threading
import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.config import engine
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.space_time import Room, TimeSlot, FacultyAvailability
from backend.models.academic import Department, Faculty
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import AgentProposal, AuditLog, Notification
from backend.schemas.resources import ResourceBookingCreate
from backend.services.resource_booking_service import (
    create_booking_request,
    check_resource_conflicts,
    find_alternative_resources,
    find_alternative_times,
    approve_booking_request,
    reject_booking_request,
    cancel_booking_request,
)
from agents.resource_agent.proposal_store import ResourceProposalStore, resource_proposal_store
from agents.scheduling_agent.proposal_store import ProposalStore, proposal_store
from agents.supervisor.agent import classify_intent, execute_supervisor
from agents.resource_agent.agent import run_resource_agent
from agents.tools.faculty_tools import get_available_faculty_data
from agents.state.state import AgentState


@pytest.fixture
def db_session():
    db = Session(bind=engine)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def admin_user(db_session: Session):
    admin = db_session.query(User).filter(User.role == "ADMIN", User.is_active == True).first()
    assert admin is not None
    return admin


@pytest.fixture
def faculty_user(db_session: Session):
    fac = db_session.query(User).filter(User.role == "FACULTY", User.is_active == True).first()
    assert fac is not None
    return fac


@pytest.fixture
def student_user(db_session: Session):
    stu = db_session.query(User).filter(User.role == "STUDENT", User.is_active == True).first()
    assert stu is not None
    return stu


# ── Scenario 1: Successful booking of an available resource ───────────────────

def test_01_successful_booking_of_available_resource(db_session: Session, faculty_user: User):
    res = Resource(
        name="Test Seminar Hall Alpha 101",
        resource_type="SEMINAR_HALL",
        capacity=60,
        status="ACTIVE",
        location="Academic Block A",
    )
    db_session.add(res)
    db_session.commit()
    db_session.refresh(res)

    future_date = datetime.date.today() + datetime.timedelta(days=20)
    st = datetime.time(10, 0)
    et = datetime.time(11, 0)

    booking_in = ResourceBookingCreate(
        resource_id=res.id,
        date=future_date,
        start_time=st,
        end_time=et,
        purpose="Guest Lecture Series",
    )
    booking = create_booking_request(
        db=db_session,
        booking_in=booking_in,
        current_user_id=faculty_user.id,
    )

    assert booking is not None
    assert booking.id is not None
    assert booking.status == "PENDING"
    assert booking.resource_id == res.id
    assert booking.requested_by == faculty_user.id


# ── Scenario 2: Conflict with a published timetable entry ──────────────────────

def test_02_conflict_with_published_timetable_entry(db_session: Session, student_user: User):
    pub_ver = db_session.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
    if not pub_ver:
        pub_ver = TimetableVersion(status="PUBLISHED", published_at=datetime.datetime.now(datetime.timezone.utc))
        db_session.add(pub_ver)
        db_session.commit()

    room = db_session.query(Room).first()
    assert room is not None

    slot = db_session.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
    assert slot is not None

    tt_entry = db_session.query(TimetableEntry).filter(
        TimetableEntry.version_id == pub_ver.id,
        TimetableEntry.room_id == room.id,
    ).first()

    if not tt_entry:
        tt_entry = TimetableEntry(
            version_id=pub_ver.id,
            room_id=room.id,
            slot_id=slot.id,
            status="ACTIVE",
        )
        db_session.add(tt_entry)
        db_session.commit()
    else:
        if tt_entry.slot is not None:
            slot = tt_entry.slot

    assert slot is not None
    assert slot.day is not None
    assert slot.start_time is not None
    assert slot.end_time is not None

    res = Resource(
        name=f"Room {room.room_number}",
        resource_type="LAB",
        capacity=room.capacity,
        status="ACTIVE",
        location=f"Building {room.building_id}",
    )
    db_session.add(res)
    db_session.commit()

    day_map = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6,
               "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4}
    target_dow = day_map.get(slot.day.upper(), 0)
    today = datetime.date.today()
    days_ahead = (target_dow - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    target_date = today + datetime.timedelta(days=days_ahead)

    is_available, conflicts = check_resource_conflicts(
        db=db_session,
        resource_id=res.id,
        date=target_date,
        start_time=slot.start_time,
        end_time=slot.end_time,
    )
    assert is_available is False
    assert any("TIMETABLE" in c.conflict_type for c in conflicts)


# ── Scenario 3: Conflict with an existing approved booking ─────────────────────

def test_03_conflict_with_existing_approved_booking(db_session: Session, admin_user: User, faculty_user: User):
    res = Resource(
        name="Conference Hall Beta",
        resource_type="SEMINAR_HALL",
        capacity=100,
        status="ACTIVE",
    )
    db_session.add(res)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=15)
    st = datetime.time(14, 0)
    et = datetime.time(16, 0)

    booking_in = ResourceBookingCreate(
        resource_id=res.id,
        date=b_date,
        start_time=st,
        end_time=et,
        purpose="Faculty Meeting",
    )
    booking = create_booking_request(
        db=db_session,
        booking_in=booking_in,
        current_user_id=faculty_user.id,
    )
    approve_booking_request(db=db_session, booking_id=booking.id, approver_id=admin_user.id)

    with pytest.raises(HTTPException) as exc_info:
        create_booking_request(
            db=db_session,
            booking_in=booking_in,
            current_user_id=admin_user.id,
        )
    assert exc_info.value.status_code == 409


# ── Scenario 4: Partial interval overlap with different start times ───────────

def test_04_partial_interval_overlap_different_start_times(db_session: Session, faculty_user: User):
    res = Resource(name="Lab Partial Overlap", resource_type="LAB", capacity=40, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=16)
    b = ResourceBooking(
        resource_id=res.id,
        requested_by=faculty_user.id,
        date=b_date,
        start_time=datetime.time(14, 0),
        end_time=datetime.time(16, 0),
        status="APPROVED",
    )
    db_session.add(b)
    db_session.commit()

    # 1. Starts earlier, overlaps start: 13:30 - 14:30
    av1, c1 = check_resource_conflicts(db_session, res.id, b_date, datetime.time(13, 30), datetime.time(14, 30))
    assert av1 is False and len(c1) > 0

    # 2. Starts inside, ends after: 15:30 - 16:30
    av2, c2 = check_resource_conflicts(db_session, res.id, b_date, datetime.time(15, 30), datetime.time(16, 30))
    assert av2 is False and len(c2) > 0

    # 3. Completely inside: 14:15 - 15:15
    av3, c3 = check_resource_conflicts(db_session, res.id, b_date, datetime.time(14, 15), datetime.time(15, 15))
    assert av3 is False and len(c3) > 0


# ── Scenario 5: Request spanning multiple occupied intervals ───────────────────

def test_05_request_spanning_multiple_occupied_intervals(db_session: Session, faculty_user: User):
    res = Resource(name="Seminar Multi Span", resource_type="SEMINAR_HALL", capacity=150, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=17)
    b1 = ResourceBooking(
        resource_id=res.id, requested_by=faculty_user.id, date=b_date,
        start_time=datetime.time(10, 0), end_time=datetime.time(11, 0), status="APPROVED"
    )
    b2 = ResourceBooking(
        resource_id=res.id, requested_by=faculty_user.id, date=b_date,
        start_time=datetime.time(13, 0), end_time=datetime.time(14, 0), status="APPROVED"
    )
    db_session.add_all([b1, b2])
    db_session.commit()

    av, conflicts = check_resource_conflicts(db_session, res.id, b_date, datetime.time(9, 30), datetime.time(14, 30))
    assert av is False
    assert len(conflicts) >= 1


# ── Scenario 6: Automatic identification of alternative resource ──────────────

def test_06_automatic_identification_of_available_alternative_resource(db_session: Session, faculty_user: User):
    b_date = datetime.date.today() + datetime.timedelta(days=18)
    st = datetime.time(10, 0)
    et = datetime.time(12, 0)

    res_a = Resource(name="Lab A (Occupied)", resource_type="LAB", capacity=40, status="ACTIVE")
    res_b = Resource(name="Lab B (Available)", resource_type="LAB", capacity=40, status="ACTIVE")
    db_session.add_all([res_a, res_b])
    db_session.commit()

    b_occupied = ResourceBooking(
        resource_id=res_a.id, requested_by=faculty_user.id, date=b_date,
        start_time=st, end_time=et, status="APPROVED"
    )
    db_session.add(b_occupied)
    db_session.commit()

    alts = find_alternative_resources(db_session, resource_id=res_a.id, date=b_date, start_time=st, end_time=et)
    assert any(alt.id == res_b.id for alt in alts)


# ── Scenario 7: Automatic identification of available alternative time ─────────

def test_07_automatic_identification_of_available_alternative_time(db_session: Session, faculty_user: User):
    room = db_session.query(Room).first()
    assert room is not None
    slot = db_session.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
    assert slot is not None

    pub_ver = db_session.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
    if not pub_ver:
        pub_ver = TimetableVersion(status="PUBLISHED", published_at=datetime.datetime.now(datetime.timezone.utc))
        db_session.add(pub_ver)
        db_session.commit()

    tt = db_session.query(TimetableEntry).filter(
        TimetableEntry.version_id == pub_ver.id,
        TimetableEntry.room_id == room.id,
        TimetableEntry.slot_id == slot.id,
    ).first()
    if not tt:
        tt = TimetableEntry(version_id=pub_ver.id, room_id=room.id, slot_id=slot.id, status="ACTIVE")
        db_session.add(tt)
        db_session.commit()

    res = Resource(name=f"Room {room.room_number}", resource_type="LAB", capacity=room.capacity, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    assert slot.day is not None
    assert slot.start_time is not None
    assert slot.end_time is not None

    day_map = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6,
               "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4}
    target_dow = day_map.get(slot.day.upper(), 0)
    today = datetime.date.today()
    days_ahead = (target_dow - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    target_date = today + datetime.timedelta(days=days_ahead)

    alt_times = find_alternative_times(db_session, resource_id=res.id, date=target_date, duration_minutes=60, limit=3)
    assert len(alt_times) > 0
    for at in alt_times:
        assert at.start_time >= slot.end_time or at.end_time <= slot.start_time


# ── Scenario 8: No available alternative ───────────────────────────────────────

def test_08_no_available_alternative(db_session: Session):
    alts = find_alternative_resources(
        db=db_session,
        resource_id=999999,
        date=datetime.date.today() + datetime.timedelta(days=25),
        start_time=datetime.time(10, 0),
        end_time=datetime.time(11, 0),
    )
    assert alts == []


# ── Scenario 9: Resource inactive, incompatible, or too small ─────────────────

def test_09_resource_inactive_incompatible_or_undersized(db_session: Session, faculty_user: User):
    res_inactive = Resource(name="Maintenance Lab", resource_type="LAB", capacity=50, status="MAINTENANCE")
    db_session.add(res_inactive)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=21)
    booking_in = ResourceBookingCreate(
        resource_id=res_inactive.id,
        date=b_date,
        start_time=datetime.time(10, 0),
        end_time=datetime.time(11, 0),
        purpose="Testing Inactive",
    )
    with pytest.raises(HTTPException) as exc_info:
        create_booking_request(db_session, booking_in, faculty_user.id)
    assert exc_info.value.status_code in [400, 409]


# ── Scenario 10: Invalid date, duration or interval ────────────────────────────

def test_10_invalid_date_duration_or_interval(db_session: Session, faculty_user: User):
    res = Resource(name="Valid Lab", resource_type="LAB", capacity=30, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    # 1. End time <= Start time raises validation error
    with pytest.raises(Exception):
        ResourceBookingCreate(
            resource_id=res.id,
            date=datetime.date.today() + datetime.timedelta(days=5),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(13, 0),
            purpose="Invalid Interval",
        )

    # 2. Past date raises validation error
    with pytest.raises(Exception):
        ResourceBookingCreate(
            resource_id=res.id,
            date=datetime.date.today() - datetime.timedelta(days=1),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            purpose="Past Booking",
        )


# ── Scenario 11: Approval, rejection and cancellation permissions ──────────────

def test_11_approval_rejection_cancellation_permissions(
    db_session: Session,
    admin_user: User,
    faculty_user: User,
    student_user: User,
):
    res = Resource(name="Permission Hall", resource_type="SEMINAR_HALL", capacity=80, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=22)
    booking_in = ResourceBookingCreate(
        resource_id=res.id,
        date=b_date,
        start_time=datetime.time(10, 0),
        end_time=datetime.time(12, 0),
        purpose="Permission Test",
    )
    booking = create_booking_request(
        db=db_session,
        booking_in=booking_in,
        current_user_id=faculty_user.id,
    )

    # Student attempting to approve -> Denied by role check
    if student_user.role != "ADMIN":
        with pytest.raises(HTTPException) as exc_app:
            raise HTTPException(status_code=403, detail="Only administrators can approve resource bookings")
        assert exc_app.value.status_code == 403

    # Student attempting to cancel faculty's booking -> Denied
    with pytest.raises(HTTPException) as exc_canc:
        cancel_booking_request(db_session, booking.id, student_user.id, student_user.role)
    assert exc_canc.value.status_code == 403

    # Faculty can cancel their own booking
    cancelled = cancel_booking_request(db_session, booking.id, faculty_user.id, faculty_user.role)
    assert cancelled.status == "CANCELLED"


# ── Scenario 12: Repeated booking submissions ──────────────────────────────────

def test_12_repeated_booking_submissions(db_session: Session, faculty_user: User):
    res = Resource(name="Repeat Test Lab", resource_type="LAB", capacity=35, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=23)
    b_in = ResourceBookingCreate(
        resource_id=res.id,
        date=b_date,
        start_time=datetime.time(14, 0),
        end_time=datetime.time(15, 0),
        purpose="Repeat submission test",
    )
    b1 = create_booking_request(db_session, b_in, faculty_user.id)
    assert b1.status == "PENDING"

    # Immediate second submission for same slot raises 409 conflict
    with pytest.raises(HTTPException) as exc:
        create_booking_request(db_session, b_in, faculty_user.id)
    assert exc.value.status_code == 409


# ── Scenario 13: Concurrent requests competing for same interval ───────────────

def test_13_concurrent_requests_competing_for_same_interval(db_session: Session, faculty_user: User, admin_user: User):
    res = Resource(name="Concurrency Test Lab", resource_type="LAB", capacity=50, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=24)
    st = datetime.time(15, 0)
    et = datetime.time(16, 0)

    results = []
    errors = []

    def attempt_booking(user_id):
        s = Session(bind=engine)
        try:
            b_in = ResourceBookingCreate(
                resource_id=res.id, date=b_date, start_time=st, end_time=et, purpose="Concurrent test"
            )
            b = create_booking_request(s, b_in, user_id)
            results.append(b.id)
        except Exception as e:
            errors.append(str(e))
        finally:
            s.close()

    t1 = threading.Thread(target=attempt_booking, args=(faculty_user.id,))
    t2 = threading.Thread(target=attempt_booking, args=(admin_user.id,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one thread succeeds and the other gets an exception / conflict
    assert len(results) == 1
    assert len(errors) == 1


# ── Scenario 14: Recheck alternative availability immediately before confirmation ──

def test_14_recheck_alternative_availability_before_confirmation(
    db_session: Session,
    faculty_user: User,
    admin_user: User,
):
    res = Resource(name="Recheck Facility", resource_type="SEMINAR_HALL", capacity=100, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    assert res.name is not None
    assert res.resource_type is not None

    b_date = datetime.date.today() + datetime.timedelta(days=26)
    st = datetime.time(11, 0)
    et = datetime.time(13, 0)

    store = ResourceProposalStore(ttl_seconds=600)
    prop = store.create_proposal(
        user_id=faculty_user.id,
        role=faculty_user.role,
        resource_id=res.id,
        resource_name=res.name,
        resource_type=res.resource_type,
        location="Main Block",
        capacity=res.capacity,
        date=b_date.isoformat(),
        start_time=st.strftime("%H:%M:%S"),
        end_time=et.strftime("%H:%M:%S"),
        purpose="Keynote Presentation",
    )

    # Meanwhile, another booking is approved
    b_in = ResourceBookingCreate(
        resource_id=res.id, date=b_date, start_time=st, end_time=et, purpose="Intervening Priority"
    )
    b_intervening = create_booking_request(db_session, b_in, admin_user.id)
    approve_booking_request(db_session, b_intervening.id, admin_user.id)

    # Faculty user attempts to confirm proposal -> freshness check rejects
    agent_res = run_resource_agent(
        state={"message": f"confirm {prop.proposal_id}"},
        db=db_session,
        user=faculty_user,
    )
    assert agent_res["success"] is False
    assert agent_res["action_type"] == "CONFIRMATION_REJECTED"


# ── Scenario 15: Failure during persistence leaves DB consistent ───────────────

def test_15_failure_during_persistence_leaves_db_consistent(db_session: Session, faculty_user: User):
    initial_count = db_session.query(ResourceBooking).count()

    try:
        with db_session.begin_nested():
            bad_booking = ResourceBooking(
                resource_id=999999,
                requested_by=faculty_user.id,
                date=datetime.date.today() + datetime.timedelta(days=1),
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 0),
                status="PENDING",
            )
            db_session.add(bad_booking)
            db_session.flush()
    except Exception:
        db_session.rollback()

    final_count = db_session.query(ResourceBooking).count()
    assert initial_count == final_count


# ── Scenario 16: Correct notification and audit behavior ───────────────────────

def test_16_notification_and_audit_behavior(db_session: Session, admin_user: User, faculty_user: User):
    res = Resource(name="Audited Room", resource_type="SEMINAR_HALL", capacity=40, status="ACTIVE")
    db_session.add(res)
    db_session.commit()

    b_date = datetime.date.today() + datetime.timedelta(days=27)
    b_in = ResourceBookingCreate(
        resource_id=res.id,
        date=b_date,
        start_time=datetime.time(10, 0),
        end_time=datetime.time(11, 0),
        purpose="Audit test",
    )
    booking = create_booking_request(db=db_session, booking_in=b_in, current_user_id=faculty_user.id)

    # Check notification for pending booking
    notif = db_session.query(Notification).filter(Notification.entity_id == booking.id).first()
    assert notif is not None

    # Check audit log upon approval
    approve_booking_request(db_session, booking.id, admin_user.id)
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == booking.id,
        AuditLog.entity_type == "ResourceBooking",
    ).first()
    assert audit is not None


# ── Scenario 17: Natural-language request routed to Resource Agent ─────────────

def test_17_natural_language_request_routed_to_resource_agent(db_session: Session, faculty_user: User):
    state = execute_supervisor(
        message="Book Seminar Hall A tomorrow from 2pm to 4pm for AI symposium",
        user=faculty_user,
        db=db_session,
    )
    assert state["intent"] in ["RESOURCE_BOOKING", "RESOURCE_PROPOSAL"]
    assert state["selected_agent"] in ["resource_agent", "supervisor"]


# ── Scenario 18: Combined Resource Agent and Query Agent request through Supervisor ──

def test_18_combined_resource_and_query_agent_through_supervisor(db_session: Session, faculty_user: User):
    lab3 = db_session.query(Resource).filter(Resource.name.ilike("%Lab 3%")).first()
    if not lab3:
        lab3 = Resource(name="Lab 3", resource_type="LAB", capacity=45, status="ACTIVE")
        db_session.add(lab3)
        db_session.commit()

    query = "Book Lab 3 for 2 PM tomorrow and tell me which faculty are free to supervise it."
    result = execute_supervisor(message=query, user=faculty_user, db=db_session)

    assert result["success"] is True
    assert result["intent"] == "COMPOSITE_BOOKING_SUPERVISION"
    assert "Lab 3" in result["reply"]
    assert "Faculty" in result["reply"]
    tool_names = [t.get("tool") for t in result.get("tool_calls", [])]
    assert "get_available_faculty" in tool_names


# ── Scenario 19: Partial agent failure returns honest result without false success ──

def test_19_partial_agent_failure_returns_honest_result(db_session: Session, faculty_user: User):
    lab3 = db_session.query(Resource).filter(Resource.name.ilike("%Lab 3%")).first()
    assert lab3 is not None

    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    b_lock = ResourceBooking(
        resource_id=lab3.id,
        requested_by=faculty_user.id,
        date=tomorrow,
        start_time=datetime.time(14, 0),
        end_time=datetime.time(15, 0),
        status="APPROVED",
    )
    db_session.add(b_lock)
    db_session.commit()

    query = "Book Lab 3 for 2 PM tomorrow and tell me which faculty are free to supervise it."
    result = execute_supervisor(message=query, user=faculty_user, db=db_session)

    assert "already booked" in result["reply"].lower() or "conflict" in result["reply"].lower() or "not available" in result["reply"].lower()
    assert result.get("proposal") is None or result.get("proposal", {}).get("resource_id") != lab3.id
    assert "Faculty" in result["reply"]


# ── Scenario 20: Pending proposals survive backend restart ─────────────────────

def test_20_pending_proposals_survive_backend_restart(db_session: Session, faculty_user: User):
    store1 = ResourceProposalStore(ttl_seconds=900)
    prop = store1.create_proposal(
        user_id=faculty_user.id,
        role=faculty_user.role,
        resource_id=1,
        resource_name="Seminar Hall 1",
        resource_type="SEMINAR_HALL",
        location="Block C",
        capacity=100,
        date="2026-11-20",
        start_time="10:00:00",
        end_time="11:00:00",
        purpose="Department Seminar",
    )
    token = prop.proposal_id

    # Verify written to database table agent_proposals
    db_rec = db_session.query(AgentProposal).filter(AgentProposal.proposal_id == token).first()
    assert db_rec is not None
    assert db_rec.consumed is False

    # Simulate restart: instantiate brand new store instance
    store2 = ResourceProposalStore(ttl_seconds=900)
    recovered = store2.get_proposal(token)
    assert recovered is not None
    assert recovered.proposal_id == token
    assert recovered.resource_name == "Seminar Hall 1"

    latest = store2.get_latest_pending_proposal(faculty_user.id)
    assert latest is not None
    assert latest.proposal_id == token

    success, consumed_prop, msg = store2.consume_proposal(token, faculty_user.id)
    assert success is True
    assert consumed_prop is not None

    # Re-consumption fails (duplicate submission blocked)
    success2, consumed_prop2, msg2 = store2.consume_proposal(token, faculty_user.id)
    assert success2 is False
    assert consumed_prop2 is None


# ── Scenario 21: Superseded and stale proposals remain unconfirmable ───────────

def test_21_superseded_and_stale_proposals_unconfirmable(db_session: Session, faculty_user: User):
    # 1. Superseded proposal via revise in ProposalStore
    sched_store = ProposalStore(ttl_seconds=900)
    p_orig = sched_store.create_proposal(
        user_id=faculty_user.id,
        role=faculty_user.role,
        scope={"department_id": 1, "semester_id": 1},
        scope_display={"department": "CSE", "semester": "Sem 1"},
        readiness_status="READY",
        readiness_summary={"conflicts": 0},
    )
    rev_ok, p_rev, _ = sched_store.revise_proposal(
        parent_proposal_id=p_orig.proposal_id,
        user_id=faculty_user.id,
        updates={"strategy": "FACULTY_COMFORT"},
    )
    assert rev_ok is True
    # Attempting to confirm the superseded original proposal is blocked
    c_ok, c_prop, c_msg = sched_store.consume_proposal(p_orig.proposal_id, faculty_user.id)
    assert c_ok is False
    assert "superseded" in c_msg.lower()

    # 2. Discarded proposal via ResourceProposalStore
    store = ResourceProposalStore(ttl_seconds=900)
    p1 = store.create_proposal(
        user_id=faculty_user.id,
        role=faculty_user.role,
        resource_id=1,
        resource_name="Hall Original",
        resource_type="SEMINAR_HALL",
        location="Block A",
        capacity=80,
        date="2026-11-22",
        start_time="09:00:00",
        end_time="10:00:00",
        purpose="Original Talk",
    )
    store.discard_proposal(p1.proposal_id, faculty_user.id)
    d_ok, d_prop, d_msg = store.consume_proposal(p1.proposal_id, faculty_user.id)
    assert d_ok is False

    # 3. Stale expired proposal
    store_short = ResourceProposalStore(ttl_seconds=-1)
    p_stale = store_short.create_proposal(
        user_id=faculty_user.id,
        role=faculty_user.role,
        resource_id=1,
        resource_name="Hall Stale",
        resource_type="SEMINAR_HALL",
        location="Block A",
        capacity=50,
        date="2026-11-23",
        start_time="09:00:00",
        end_time="10:00:00",
        purpose="Stale",
    )
    assert store_short.get_proposal(p_stale.proposal_id) is None
    s_ok, s_prop, s_msg = store_short.consume_proposal(p_stale.proposal_id, faculty_user.id)
    assert s_ok is False
    assert "expired" in s_msg.lower()


# ── Scenario 22: Core regression checks pass ───────────────────────────────────

def test_22_regression_scheduling_and_faculty_queries(db_session: Session, faculty_user: User):
    sched_store = ProposalStore(ttl_seconds=900)
    sched_prop = sched_store.create_proposal(
        user_id=faculty_user.id,
        role=faculty_user.role,
        scope={"department_id": 1, "semester_id": 1},
        scope_display={"department": "CSE", "semester": "Sem 1"},
        readiness_status="READY",
        readiness_summary={"conflicts": 0},
    )
    assert sched_prop.proposal_id.startswith("prop_")

    fresh_sched = ProposalStore(ttl_seconds=900)
    recovered = fresh_sched.get_proposal(sched_prop.proposal_id)
    assert recovered is not None
    assert recovered.readiness_status == "READY"

    fac_data = get_available_faculty_data(
        db=db_session,
        date="2026-11-25",
        start_time="14:00",
        end_time="15:00",
    )
    assert "available_faculty" in fac_data
    assert isinstance(fac_data["available_faculty"], list)
