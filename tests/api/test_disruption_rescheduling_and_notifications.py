"""
tests/api/test_disruption_rescheduling_and_notifications.py
-----------------------------------------------------------
Comprehensive verification test suite for:
- Disruption intake & impact analysis against actual database records
- Minimal-perturbation rescheduling using Google OR-Tools CP-SAT
- Locking of unaffected entries and deviation penalties
- Before-and-after revision diff generation
- Proposal lifecycle, single-use idempotency, and TTL safeguards
- Atomic publication and source version archival
- Targeted notification dispatch and durable NotificationOutbox queue
- Non-admin authorization guardrails
- Scheduling agent natural language disruption and confirmation workflows
"""

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import AcademicYear, Semester, Department, Program, Faculty, Student
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.models.workflow import AgentProposal, AuditLog, Notification, NotificationOutbox
from backend.services.disruption_service import (
    DisruptionSpec,
    analyze_disruption_impact,
    create_rescheduling_proposal,
    execute_publish_rescheduled_proposal,
)
from backend.services.notification_service import process_notification_outbox
from backend.utils.datetime_utils import utc_now
from agents.scheduling_agent.agent import run_scheduling_agent
from agents.state.state import AgentState

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    res = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert res.status_code == 200, "Failed to login as admin"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def faculty_token():
    res = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert res.status_code == 200, "Failed to login as faculty"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    res = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert res.status_code == 200, "Failed to login as student"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def published_timetable(admin_token):
    """
    Sets up a published timetable in the database through the standard lifecycle:
    Generate -> Validate -> Finalize -> Publish.
    """
    with Session(engine) as db:
        ay = db.query(AcademicYear).first()
        sem = db.query(Semester).first()
        dept = db.query(Department).first()
        prog = db.query(Program).first()
        assert ay and sem and dept and prog, "Missing seed records for timetable generation"
        ay_id, sem_id, dept_id, prog_id = ay.id, sem.id, dept.id, prog.id

    # 1. Generate
    gen_res = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": ay_id,
            "semester_id": sem_id,
            "department_id": dept_id,
            "program_id": prog_id,
        },
    )
    assert gen_res.status_code == 200, f"Generate failed: {gen_res.text}"
    v_id = gen_res.json()["version_id"]

    # 2. Validate
    val_res = client.post(
        f"/timetable/versions/{v_id}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert val_res.status_code == 200

    # 3. Finalize
    fin_res = client.post(
        f"/timetable/versions/{v_id}/finalize",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert fin_res.status_code == 200

    # 4. Publish
    pub_res = client.post(
        f"/timetable/versions/{v_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "PUBLISHED"

    return v_id


def get_active_published_version_id() -> int:
    with Session(engine) as db:
        v = (
            db.query(TimetableVersion)
            .filter(TimetableVersion.status == "PUBLISHED")
            .order_by(TimetableVersion.id.desc())
            .first()
        )
        assert v is not None, "No active published timetable found"
        return v.id


# ── 1. Authorization Guardrails ───────────────────────────────────────────────

def test_disruption_endpoints_require_admin_role(faculty_token, student_token, published_timetable):
    """
    Enforces authorization: Faculty and Students are strictly blocked (HTTP 403)
    from initiating disruption analysis, creating rescheduling proposals, or publishing revisions.
    """
    spec_data = {
        "disruption_type": "FACULTY_LEAVE",
        "reason": "Unauthorized test",
        "day": "WED",
        "source_version_id": published_timetable,
    }

    # Faculty attempts
    res = client.post("/timetable/disruptions/analyze", headers={"Authorization": f"Bearer {faculty_token}"}, json=spec_data)
    assert res.status_code == 403
    res = client.post("/timetable/disruptions/propose", headers={"Authorization": f"Bearer {faculty_token}"}, json=spec_data)
    assert res.status_code == 403
    res = client.post("/timetable/disruptions/confirm", headers={"Authorization": f"Bearer {faculty_token}"}, json={"proposal_id": "disrupt_prop_dummy"})
    assert res.status_code == 403
    res = client.get("/notifications/outbox", headers={"Authorization": f"Bearer {faculty_token}"})
    assert res.status_code == 403

    # Student attempts
    res = client.post("/timetable/disruptions/analyze", headers={"Authorization": f"Bearer {student_token}"}, json=spec_data)
    assert res.status_code == 403
    res = client.post("/timetable/disruptions/propose", headers={"Authorization": f"Bearer {student_token}"}, json=spec_data)
    assert res.status_code == 403
    res = client.post("/timetable/disruptions/confirm", headers={"Authorization": f"Bearer {student_token}"}, json={"proposal_id": "disrupt_prop_dummy"})
    assert res.status_code == 403
    res = client.get("/notifications/outbox", headers={"Authorization": f"Bearer {student_token}"})
    assert res.status_code == 403


# ── 2. Impact Analysis ────────────────────────────────────────────────────────

def test_disruption_impact_analysis_faculty_leave(admin_token, published_timetable):
    """
    Impact analysis accurately isolates affected entries without modifying the published timetable.
    """
    with Session(engine) as db:
        entries = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(TimetableEntry.version_id == published_timetable)
            .all()
        )
        assert len(entries) > 0
        target_entry = entries[0]
        fac_id = target_entry.faculty_id
        target_day = target_entry.slot.day

    spec = {
        "disruption_type": "FACULTY_LEAVE",
        "reason": "Sudden medical leave",
        "faculty_id": fac_id,
        "day": target_day,
        "source_version_id": published_timetable,
    }

    res = client.post(
        "/timetable/disruptions/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=spec,
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["source_version_id"] == published_timetable
    assert data["affected_count"] >= 1
    assert data["unaffected_count"] >= 1
    assert data["affected_count"] + data["unaffected_count"] == data["total_entries_count"]
    assert fac_id in data["impacted_faculty_ids"]
    assert len(data["affected_entries"]) == data["affected_count"]
    assert any(e["entry_id"] == target_entry.id for e in data["affected_entries"])

    # Verify source timetable is completely unchanged
    with Session(engine) as db:
        v = db.query(TimetableVersion).filter(TimetableVersion.id == published_timetable).first()
        assert v.status == "PUBLISHED"


def test_disruption_impact_analysis_room_maintenance(admin_token, published_timetable):
    """
    Impact analysis correctly identifies classes scheduled in a room under maintenance.
    """
    with Session(engine) as db:
        entry = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(TimetableEntry.version_id == published_timetable)
            .first()
        )
        assert entry is not None
        room_id = entry.room_id
        day = entry.slot.day

    spec = {
        "disruption_type": "ROOM_MAINTENANCE",
        "reason": "Emergency AC maintenance",
        "room_id": room_id,
        "day": day,
        "source_version_id": published_timetable,
    }

    res = client.post(
        "/timetable/disruptions/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=spec,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["affected_count"] >= 1
    assert all(e["room_id"] == room_id for e in data["affected_entries"])


def test_disruption_impact_no_affect(admin_token, published_timetable):
    """
    Impact analysis reports 0 affected sessions when disruption window has no classes.
    """
    with Session(engine) as db:
        # Use Sunday where no classes are scheduled
        entry = db.query(TimetableEntry).filter(TimetableEntry.version_id == published_timetable).first()
        fac_id = entry.faculty_id

    spec = {
        "disruption_type": "FACULTY_LEAVE",
        "reason": "Leave on non-instructional day",
        "faculty_id": fac_id,
        "day": "SUN",
        "source_version_id": published_timetable,
    }

    res = client.post(
        "/timetable/disruptions/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=spec,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["affected_count"] == 0
    assert data["unaffected_count"] == data["total_entries_count"]


# ── 3. Minimal-Perturbation Rescheduling & Proposal Generation ────────────────

def test_minimal_perturbation_rescheduling_proposal(admin_token, published_timetable):
    """
    Generates a minimal-perturbation proposal:
    - Locks unaffected assignments in place.
    - Moves ONLY affected assignments.
    - Zero hard constraint violations.
    - Computes clear revision diff with before/after comparison.
    """
    with Session(engine) as db:
        entry = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(TimetableEntry.version_id == published_timetable)
            .first()
        )
        fac_id = entry.faculty_id
        target_slot_id = entry.slot_id
        target_day = entry.slot.day

    spec = {
        "disruption_type": "FACULTY_LEAVE",
        "reason": "Dr. on conference leave",
        "faculty_id": fac_id,
        "slot_ids": [target_slot_id],
        "day": target_day,
        "source_version_id": published_timetable,
    }

    res = client.post(
        "/timetable/disruptions/propose",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=spec,
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["success"] is True
    assert data["status"] == "PROPOSED"
    assert data["proposal_id"].startswith("disrupt_prop_")
    assert data["preserved_count"] > 0
    assert data["changed_count"] >= 1
    assert data["hard_violations"] == 0
    assert len(data["diff_items"]) == data["changed_count"]

    # Verify diff items contain full before-and-after comparison
    diff = data["diff_items"][0]
    assert "course_code" in diff
    assert "old_slot_label" in diff
    assert "new_slot_label" in diff
    assert "old_room_number" in diff
    assert "new_room_number" in diff
    assert diff["change_type"] in ("RESCHEDULED_TIME", "RESCHEDULED_ROOM", "RESCHEDULED_BOTH")

    # Verify source published timetable is untouched
    with Session(engine) as db:
        v = db.query(TimetableVersion).filter(TimetableVersion.id == published_timetable).first()
        assert v.status == "PUBLISHED"


# ── 4. Revision Approval, Atomic Publication & Version Transition ─────────────

def test_proposal_confirmation_and_atomic_publication(admin_token, published_timetable):
    """
    Publishes an approved revision:
    - Atomically creates new TimetableVersion in PUBLISHED status.
    - Archives prior published timetable.
    - Generates targeted notifications.
    - Stores outbox records.
    """
    with Session(engine) as db:
        entry = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(TimetableEntry.version_id == published_timetable)
            .first()
        )
        fac_id = entry.faculty_id
        target_slot_id = entry.slot_id
        target_day = entry.slot.day

    # 1. Propose
    prop_res = client.post(
        "/timetable/disruptions/propose",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "disruption_type": "FACULTY_LEAVE",
            "reason": "Faculty sick leave",
            "faculty_id": fac_id,
            "slot_ids": [target_slot_id],
            "day": target_day,
            "source_version_id": published_timetable,
        },
    )
    assert prop_res.status_code == 200
    prop_id = prop_res.json()["proposal_id"]

    # 2. Confirm and Publish
    conf_res = client.post(
        "/timetable/disruptions/confirm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"proposal_id": prop_id},
    )
    assert conf_res.status_code == 200, conf_res.text
    pub_data = conf_res.json()

    assert pub_data["success"] is True
    assert pub_data["status"] == "PUBLISHED"
    assert pub_data["old_version_id"] == published_timetable
    new_v_id = pub_data["new_version_id"]
    assert new_v_id != published_timetable

    # 3. Verify Database State
    with Session(engine) as db:
        old_v = db.query(TimetableVersion).filter(TimetableVersion.id == published_timetable).first()
        assert old_v.status == "ARCHIVED", "Prior timetable must be archived"

        new_v = db.query(TimetableVersion).filter(TimetableVersion.id == new_v_id).first()
        assert new_v.status == "PUBLISHED", "New revision must be published"
        assert new_v.published_at is not None

        new_entries = db.query(TimetableEntry).filter(TimetableEntry.version_id == new_v_id).all()
        assert len(new_entries) > 0

        # Audit log verification
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "TimetableVersion",
                AuditLog.entity_id == new_v_id,
                AuditLog.action == "TIMETABLE_RESCHEDULED_AND_PUBLISHED",
            )
            .first()
        )
        assert audit is not None, "AuditLog record must be persisted"


# ── 5. Single-Use Idempotency & Stale Proposal Safeguards ──────────────────────

def test_single_use_idempotency_blocks_duplicate_confirmation(admin_token):
    """
    Submitting confirmation for an already consumed proposal is strictly rejected (HTTP 409).
    """
    active_vid = get_active_published_version_id()
    with Session(engine) as db:
        entry = db.query(TimetableEntry).filter(TimetableEntry.version_id == active_vid).first()
        fac_id = entry.faculty_id

    # Create fresh proposal
    prop_res = client.post(
        "/timetable/disruptions/propose",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "disruption_type": "FACULTY_LEAVE",
            "reason": "Idempotency test",
            "faculty_id": fac_id,
            "source_version_id": active_vid,
        },
    )
    assert prop_res.status_code == 200, prop_res.text
    prop_id = prop_res.json()["proposal_id"]

    # First confirmation succeeds
    conf1 = client.post("/timetable/disruptions/confirm", headers={"Authorization": f"Bearer {admin_token}"}, json={"proposal_id": prop_id})
    assert conf1.status_code == 200

    # Second confirmation MUST be blocked
    conf2 = client.post("/timetable/disruptions/confirm", headers={"Authorization": f"Bearer {admin_token}"}, json={"proposal_id": prop_id})
    assert conf2.status_code == 409
    assert "already been confirmed" in conf2.json()["detail"].lower()


def test_expired_proposal_rejection(admin_token):
    """
    Confirming an expired proposal is rejected with HTTP 410 Gone.
    """
    active_vid = get_active_published_version_id()
    with Session(engine) as db:
        admin_u = db.query(User).filter(User.role == "ADMIN").first()
        entry = db.query(TimetableEntry).filter(TimetableEntry.version_id == active_vid).first()
        spec = DisruptionSpec(
            disruption_type="FACULTY_LEAVE",
            reason="Expiration test",
            faculty_id=entry.faculty_id,
            source_version_id=active_vid,
        )
        prop_res = create_rescheduling_proposal(db, spec, admin_u)
        assert prop_res.success is True
        prop_id = prop_res.proposal_id

        # Manually backdate expiration to 1 hour ago
        ap = db.query(AgentProposal).filter(AgentProposal.proposal_id == prop_id).first()
        ap.expires_at = utc_now() - datetime.timedelta(hours=1)
        db.commit()

    # Confirmation must fail with 410 Gone
    res = client.post(
        "/timetable/disruptions/confirm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"proposal_id": prop_id},
    )
    assert res.status_code == 410
    assert "expired" in res.json()["detail"].lower()


# ── 6. Targeted Notifications & Durable NotificationOutbox ────────────────────

def test_targeted_notification_dispatch_and_outbox(admin_token):
    """
    Verifies that:
    1. Targeted recipients (affected faculty & students in impacted sections) receive notifications.
    2. Unaffected students and faculty receive ZERO notifications.
    3. NotificationOutbox records are created in PENDING status.
    4. Outbox processing delivers pending messages and marks them SENT.
    """
    active_vid = get_active_published_version_id()
    with Session(engine) as db:
        # Find entry with specific section
        entry = (
            db.query(TimetableEntry)
            .filter(TimetableEntry.version_id == active_vid, TimetableEntry.section_id.isnot(None))
            .first()
        )
        assert entry is not None
        affected_sec_id = entry.section_id
        affected_fac_id = entry.faculty_id

        # Find unaffected section
        unaffected_sec = db.query(Student.section_id).filter(Student.section_id != affected_sec_id).first()
        unaffected_sec_id = unaffected_sec[0] if unaffected_sec else None

    # Propose and confirm
    prop_res = client.post(
        "/timetable/disruptions/propose",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "disruption_type": "FACULTY_LEAVE",
            "reason": "Targeted notification test",
            "faculty_id": affected_fac_id,
            "source_version_id": active_vid,
        },
    )
    assert prop_res.status_code == 200, prop_res.text
    prop_id = prop_res.json()["proposal_id"]

    conf_res = client.post(
        "/timetable/disruptions/confirm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"proposal_id": prop_id},
    )
    assert conf_res.status_code == 200
    new_v_id = conf_res.json()["new_version_id"]

    with Session(engine) as db:
        # 1. Affected faculty received notification
        fac_obj = db.query(Faculty).filter(Faculty.id == affected_fac_id).first()
        if fac_obj and fac_obj.user_id:
            fac_notif = (
                db.query(Notification)
                .filter(
                    Notification.user_id == fac_obj.user_id,
                    Notification.entity_id == new_v_id,
                    Notification.type == "TIMETABLE_RESCHEDULED",
                )
                .first()
            )
            assert fac_notif is not None, "Affected faculty must receive rescheduling notification"

        # 2. Affected students received notification
        affected_students = db.query(Student).filter(Student.section_id == affected_sec_id).all()
        for s in affected_students:
            if s.user_id:
                s_notif = (
                    db.query(Notification)
                    .filter(
                        Notification.user_id == s.user_id,
                        Notification.entity_id == new_v_id,
                        Notification.type == "TIMETABLE_RESCHEDULED",
                    )
                    .first()
                )
                assert s_notif is not None, f"Affected student #{s.user_id} must receive notification"

        # 3. Unaffected students received ZERO notifications
        if unaffected_sec_id:
            unaffected_students = db.query(Student).filter(Student.section_id == unaffected_sec_id).all()
            for us in unaffected_students:
                if us.user_id:
                    u_notif = (
                        db.query(Notification)
                        .filter(
                            Notification.user_id == us.user_id,
                            Notification.entity_id == new_v_id,
                            Notification.type == "TIMETABLE_RESCHEDULED",
                        )
                        .first()
                    )
                    assert u_notif is None, f"Unaffected student #{us.user_id} must NOT receive notification"

        # 4. Outbox records exist in database
        outbox_items = (
            db.query(NotificationOutbox)
            .join(Notification, NotificationOutbox.notification_id == Notification.id)
            .filter(Notification.entity_id == new_v_id)
            .all()
        )
        assert len(outbox_items) > 0, "NotificationOutbox records must be created"

        # Simulate a transient failure / pending record to test outbox retry worker
        test_item = outbox_items[0]
        test_item.status = "PENDING"
        test_item.retry_count = 0
        db.commit()

    # 5. Outbox API Endpoint inspection
    outbox_res = client.get(
        "/notifications/outbox",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert outbox_res.status_code == 200
    outbox_list = outbox_res.json()
    assert len(outbox_list) > 0

    # 6. Process Outbox Queue (Worker retry execution)
    proc_res = client.post(
        "/notifications/outbox/process",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert proc_res.status_code == 200
    stats = proc_res.json()["stats"]
    assert stats["processed_count"] > 0
    assert stats["delivered_count"] > 0

    # Verify status changed to SENT in DB
    with Session(engine) as db:
        sent_items = (
            db.query(NotificationOutbox)
            .join(Notification, NotificationOutbox.notification_id == Notification.id)
            .filter(Notification.entity_id == new_v_id, NotificationOutbox.status == "SENT")
            .all()
        )
        assert len(sent_items) > 0, "Outbox records must transition to SENT after processing"


# ── 7. Scheduling Agent Disruption Workflow ───────────────────────────────────

def test_scheduling_agent_disruption_intake_and_confirmation():
    """
    Verifies that the Intelligent Scheduling Agent:
    1. Understands natural language disruption intake.
    2. Identifies affected faculty and slots.
    3. Returns revision diff and single-use confirmation token.
    4. Successfully executes publication upon confirmation token dispatch.
    """
    active_vid = get_active_published_version_id()
    with Session(engine) as db:
        admin_u = db.query(User).filter(User.role == "ADMIN").first()
        entry = (
            db.query(TimetableEntry)
            .join(TimeSlot, TimetableEntry.slot_id == TimeSlot.id)
            .filter(TimetableEntry.version_id == active_vid)
            .first()
        )
        fac_name = entry.faculty.user.name.split()[0]
        day_text = entry.slot.day.lower()

        # Step 1: Disruption Request
        req_msg = f"Dr. {fac_name} is unavailable on {day_text} afternoon, reschedule the affected classes."
        state: AgentState = {
            "message": req_msg,
            "user_id": admin_u.id,
            "role": admin_u.role,
            "intent": "TIMETABLE_RESCHEDULING",
            "tool_calls": [],
            "sources": [],
        }

        res = run_scheduling_agent(state=state, db=db, user=admin_u)
        assert res["success"] is True
        assert res["action_type"] in ("PROPOSAL_CREATED", "NO_IMPACT")
        if res["action_type"] == "PROPOSAL_CREATED":
            prop_id = res["proposal_id"]
            assert prop_id.startswith("disrupt_prop_")
            assert "confirm disrupt_prop_" in res["final_response"].lower()

            # Step 2: Confirm Proposal via Agent
            confirm_state: AgentState = {
                "message": f"confirm {prop_id}",
                "user_id": admin_u.id,
                "role": admin_u.role,
                "intent": "TIMETABLE_RESCHEDULING",
                "tool_calls": [],
                "sources": [],
            }
            conf_res = run_scheduling_agent(state=confirm_state, db=db, user=admin_u)
            assert conf_res["success"] is True
            assert conf_res["action_type"] == "TIMETABLE_RESCHEDULED_AND_PUBLISHED"
            assert "published successfully" in conf_res["final_response"].lower()


def test_scheduling_agent_ambiguous_disruption_clarification(published_timetable):
    """
    When essential disruption details are missing, the agent asks for clarification rather than guessing.
    """
    with Session(engine) as db:
        admin_u = db.query(User).filter(User.role == "ADMIN").first()

        state: AgentState = {
            "message": "A faculty member reported sick leave, please reschedule.",
            "user_id": admin_u.id,
            "role": admin_u.role,
            "intent": "TIMETABLE_RESCHEDULING",
            "tool_calls": [],
            "sources": [],
        }

        res = run_scheduling_agent(state=state, db=db, user=admin_u)
        assert res["success"] is True
        assert res["action_type"] == "CLARIFICATION_NEEDED"
        assert "which faculty member" in res["final_response"].lower()
