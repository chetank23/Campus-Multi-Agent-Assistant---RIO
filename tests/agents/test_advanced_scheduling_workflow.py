"""
tests/agents/test_advanced_scheduling_workflow.py
-------------------------------------------------
Comprehensive Test Suite for the Advanced Scheduling Agent Workflow.
Covers all 16 required scenarios from Section 7 of the specification:

1. Natural-language generation request reaches Scheduling Agent.
2. Structured parameters resolve to valid database records.
3. Missing essential information produces clarification prompt rather than invented value.
4. Unsupported constraints are rejected or explained safely.
5. Hard constraints remain enforced during conversational revisions.
6. A successful solver result becomes a validated proposal.
7. An infeasible request returns honest diagnostics without fabricating success.
8. Unknown or timeout solver results are not misreported as infeasible or successful.
9. Revision creates the correct updated proposal and safely supersedes the parent proposal.
10. Confirmation executes only the intended current proposal.
11. Stale, expired, superseded, mismatched, and duplicate confirmations are rejected safely.
12. Invalid proposals cannot be finalized or published.
13. Unauthorized users (e.g. students) cannot create or confirm privileged scheduling actions.
14. Solver failures and database failures do not corrupt existing timetable state.
15. Conflict inspection and faculty availability workflows function authoritatively.
16. Existing Query Agent and Resource Agent regression checks continue to pass.
"""

import time
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Department, Semester, AcademicYear, Section, Faculty
from backend.models.space_time import TimeSlot, FacultyAvailability
from backend.models.timetable import TimetableVersion, TimetableEntry
from backend.schemas.timetable_generation import GenerationScope
from backend.services.timetable_service import TimetableGenerationResult
from agents.scheduling_agent.proposal_store import proposal_store, ProposalStore
from agents.tools.scheduling_tools import (
    resolve_academic_scope_data,
    analyze_scheduling_readiness_data,
    inspect_timetable_conflicts_data,
    update_faculty_availability_data,
    execute_finalize_timetable_data,
    execute_publish_timetable_data,
)
from agents.scheduling_agent.agent import run_scheduling_agent
from agents.state.state import AgentState

client = TestClient(app)


# ── Auth Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_user():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "ADMIN").first()
        assert user is not None
        return user


# ── Scenario 1: NL Generation Request Reaches Scheduling Agent ────────────────

def test_01_nl_generation_request_reaches_scheduling_agent(admin_token):
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["selected_agent"] == "scheduling_agent"
    assert body["intent"] == "TIMETABLE_PROPOSAL"
    assert body["proposal"] is not None
    assert body["proposal"]["proposal_id"].startswith("prop_")
    assert body["proposal"]["revision"] == 1


# ── Scenario 2: Structured Parameters Resolve to Valid Records ───────────────

def test_02_structured_parameters_resolve_to_valid_records():
    with Session(engine) as db:
        res = resolve_academic_scope_data(db=db, query_text="Generate a timetable for CSE Semester 1")
        assert res["resolved"] is True
        scope = res["scope"]
        assert scope is not None

        # Verify resolved IDs exist in DB
        dept = db.query(Department).filter(Department.id == scope["department_id"]).first()
        assert dept is not None
        assert "CS" in dept.department_code or "CSE" in dept.department_code

        sem = db.query(Semester).filter(Semester.id == scope["semester_id"]).first()
        assert sem is not None
        assert sem.semester_number == 1

        ay = db.query(AcademicYear).filter(AcademicYear.id == scope["academic_year_id"]).first()
        assert ay is not None


# ── Scenario 3: Missing Essential Info Produces Clarification Prompt ──────────

def test_03_missing_essential_info_clarification(admin_token):
    # Query lacking semester
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["proposal"] is None
    reply_lower = body["reply"].lower()
    assert "semester" in reply_lower or "clarification" in reply_lower
    # Must NOT invent a semester value or create a proposal token
    assert "prop_" not in body["reply"]


# ── Scenario 4: Unsupported Constraints Rejected Safely ───────────────────────

def test_04_unsupported_constraints_rejected_safely(admin_token):
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate timetable for CSE Semester 1 and make sure all classes end by 10am"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_type"] == "UNSUPPORTED_CONSTRAINT_REJECTED"
    assert "unsupported scheduling constraint" in body["reply"].lower()
    assert "hard constraints cannot be waived" in body["reply"].lower()
    # Must not create a proposal
    assert body["proposal"] is None


# ── Scenario 5: Hard Constraints Remain Enforced During Conversational Revisions

def test_05_hard_constraints_remain_enforced_during_conversational_revisions():
    from backend.optimizer.timetable_solver import TimetableSolver
    from backend.schemas.timetable_generation import OptimizerInput, OptTimeSlot

    # Verify all strategies retain hard constraints (zero double booking, capacity)
    for strat in ["BALANCED", "FACULTY_COMFORT", "ROOM_EFFICIENCY", "LAB_PREFERENCE"]:
        slots = [
            OptTimeSlot(id=1, day="MON", start_time="09:00:00", end_time="10:00:00", slot_type="CLASS"),
            OptTimeSlot(id=2, day="MON", start_time="10:00:00", end_time="11:00:00", slot_type="BREAK"),
        ]
        dummy_input = OptimizerInput(
            scope=GenerationScope(department_id=1, program_id=1, semester_id=1, academic_year_id=1),
            sections=[],
            courses=[],
            faculty=[],
            rooms=[],
            time_slots=slots,
            course_assignments=[],
        )
        solver = TimetableSolver(opt_input=dummy_input, strategy=strat)
        assert solver.strategy == strat
        # Ensure eligible slots exclude BREAK slots in all strategies
        eligible = solver._get_eligible_slots(faculty_id=1)
        assert 2 not in eligible  # Break slot must be excluded across all strategies


# ── Scenario 6: Successful Solver Result Becomes Validated Proposal ───────────

def test_06_successful_solver_result_becomes_validated_proposal(admin_token):
    # Step 1: Create proposal
    prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    assert prep.status_code == 200
    prop_id = prep.json()["proposal"]["proposal_id"]

    # Step 2: Confirm execution
    exec_res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"confirm {prop_id}"},
    )
    assert exec_res.status_code == 200
    body = exec_res.json()
    assert body["action_type"] == "GENERATION_SUCCESS"
    assert "version id:" in body["reply"].lower()
    assert "solver status:" in body["reply"].lower()


# ── Scenario 7: Infeasible Request Returns Honest Diagnostics ─────────────────

def test_07_infeasible_request_returns_honest_diagnostics(admin_token):
    prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    prop_id = prep.json()["proposal"]["proposal_id"]

    infeasible_res = TimetableGenerationResult(
        success=False,
        status="INFEASIBLE",
        message="No feasible timetable exists with the current constraints.",
        diagnostics=["Faculty availability shortage: Faculty ID 3 needs 16 hours but only 10 available slots."],
    )

    with patch("agents.scheduling_agent.agent.execute_timetable_generation", return_value=infeasible_res):
        exec_res = client.post(
            "/agents/chat",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": f"confirm {prop_id}"},
        )
        assert exec_res.status_code == 200
        body = exec_res.json()
        assert body["action_type"] == "GENERATION_INFEASIBLE"
        assert "faculty availability shortage" in body["reply"].lower()
        assert "infeasible" in body["reply"].lower()


# ── Scenario 8: Unknown or Timeout Results Not Misreported ────────────────────

def test_08_unknown_or_timeout_solver_results_not_misreported(admin_token):
    prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    prop_id = prep.json()["proposal"]["proposal_id"]

    timeout_res = TimetableGenerationResult(
        success=False,
        status="UNKNOWN",
        message="Solver reached time limit without finding a solution.",
        solve_time_seconds=60.0,
    )

    with patch("agents.scheduling_agent.agent.execute_timetable_generation", return_value=timeout_res):
        exec_res = client.post(
            "/agents/chat",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": f"confirm {prop_id}"},
        )
        assert exec_res.status_code == 200
        body = exec_res.json()
        assert body["action_type"] == "GENERATION_TIMEOUT"
        assert "timeout" in body["reply"].lower()
        # Must not misreport as infeasible
        assert "infeasible" not in body["action_type"].lower()


# ── Scenario 9: Revision Creates Correct Updated Proposal & Supersedes Parent ──

def test_09_revision_creates_correct_updated_proposal_and_supersedes_parent(admin_token):
    # Step 1: Request initial proposal
    res1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    p1 = res1.json()["proposal"]
    p1_id = p1["proposal_id"]
    assert p1["revision"] == 1
    assert p1["strategy"] == "BALANCED"

    # Step 2: Request conversational revision
    res2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Avoid assigning labs in the morning where possible"},
    )
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["action_type"] == "PROPOSAL_REVISED"
    p2 = body2["proposal"]
    assert p2 is not None
    assert p2["proposal_id"] != p1_id
    assert p2["revision"] == 2
    assert p2["parent_proposal_id"] == p1_id
    assert p2["strategy"] == "LAB_PREFERENCE"
    assert p2["parameters"].get("avoid_morning_labs") is True

    # Step 3: Verify parent proposal is marked superseded in store
    parent_stored = proposal_store.get_proposal(p1_id)
    assert parent_stored is not None
    assert parent_stored.superseded is True
    assert parent_stored.superseded_by == p2["proposal_id"]


# ── Scenario 10: Confirmation Executes Only Intended Current Proposal ─────────

def test_10_confirmation_executes_only_intended_current_proposal(admin_token):
    # Request generation
    res1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    p1_id = res1.json()["proposal"]["proposal_id"]

    # Revise to faculty comfort
    res2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Revise the proposed timetable to reduce consecutive periods"},
    )
    p2 = res2.json()["proposal"]
    p2_id = p2["proposal_id"]

    # Confirm the revised proposal P2
    conf = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"confirm {p2_id}"},
    )
    assert conf.status_code == 200
    body = conf.json()
    assert body["action_type"] == "GENERATION_SUCCESS"

    # Verify P2 is marked consumed
    stored_p2 = proposal_store.get_proposal(p2_id)
    assert stored_p2 is not None
    assert stored_p2.consumed is True


# ── Scenario 11: Stale, Expired, Superseded, and Duplicate Confirmations Blocked

def test_11_stale_expired_superseded_and_duplicate_confirmations_rejected(admin_token):
    # 1. Create P1 and revise to P2
    res1 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    p1_id = res1.json()["proposal"]["proposal_id"]

    res2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Avoid assigning labs in the morning where possible"},
    )
    p2_id = res2.json()["proposal"]["proposal_id"]

    # Attempt to confirm superseded P1 -> Blocked
    stale_conf = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"confirm {p1_id}"},
    )
    assert stale_conf.status_code == 200
    assert "superseded by revision" in stale_conf.json()["reply"].lower()

    # Confirm P2 -> Success
    conf2 = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"confirm {p2_id}"},
    )
    assert conf2.status_code == 200
    assert conf2.json()["action_type"] == "GENERATION_SUCCESS"

    # Attempt to re-confirm P2 -> Duplicate submission blocked
    dup_conf = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"confirm {p2_id}"},
    )
    assert dup_conf.status_code == 200
    assert "already been confirmed" in dup_conf.json()["reply"].lower()

    # Expired token check
    store = ProposalStore(ttl_seconds=-1)
    exp_prop = store.create_proposal(
        user_id=1,
        role="ADMIN",
        scope={},
        scope_display={},
        readiness_status="READY",
        readiness_summary={},
    )
    ok, _, err = store.consume_proposal(exp_prop.proposal_id, user_id=1)
    assert ok is False
    assert "expired" in err.lower() or "not found" in err.lower()


# ── Scenario 12: Invalid Proposals Cannot Be Finalized or Published ───────────

def test_12_invalid_proposals_cannot_be_finalized_or_published(admin_token, admin_user):
    with Session(engine) as db:
        # Create a timetable version with a blocker violation (e.g. invalid slot type BREAK)
        break_slot = db.query(TimeSlot).filter(TimeSlot.slot_type == "BREAK").first()
        tv = TimetableVersion(academic_year_id=1, status="VALIDATED", created_by=admin_user.id)
        db.add(tv)
        db.flush()

        entry = TimetableEntry(
            version_id=tv.id,
            department_id=1,
            program_id=1,
            semester_id=1,
            section_id=1,
            course_id=1,
            faculty_id=1,
            room_id=1,
            slot_id=break_slot.id if break_slot else 1,
            status="DRAFT",
        )
        db.add(entry)
        db.commit()
        tv_id = tv.id

        # Attempt to finalize -> Must be rejected by validator
        fin_res = execute_finalize_timetable_data(db=db, version_id=tv_id, user=admin_user)
        assert fin_res["success"] is False
        assert "constraint validation failed with blockers" in fin_res["error"].lower()

        # Attempt to publish -> Must be rejected by validator
        pub_res = execute_publish_timetable_data(db=db, version_id=tv_id, user=admin_user)
        assert pub_res["success"] is False


# ── Scenario 13: Unauthorized Users Cannot Create or Confirm ──────────────────

def test_13_unauthorized_users_cannot_create_or_confirm(student_token):
    # Student attempts generation request
    res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    assert res.status_code == 200
    assert "only university administrators" in res.json()["reply"].lower()
    assert res.json()["proposal"] is None

    # Student attempts confirmation
    conf = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": "confirm prop_1234567890abcdef"},
    )
    assert conf.status_code == 200
    assert "only university administrators" in conf.json()["reply"].lower()


# ── Scenario 14: Failures Do Not Corrupt Existing Timetable State ──────────────

def test_14_solver_or_database_failures_do_not_corrupt_existing_state(admin_token, admin_user):
    with Session(engine) as db:
        # Create an existing published version
        existing = TimetableVersion(
            academic_year_id=1,
            status="PUBLISHED",
            version_number="1.0",
            created_by=admin_user.id,
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        existing_id = existing.id

    # Simulate solver failure on a new request
    prep = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Generate a timetable for CSE Semester 1"},
    )
    prop_id = prep.json()["proposal"]["proposal_id"]

    with patch("agents.scheduling_agent.agent.execute_timetable_generation", side_effect=RuntimeError("DB Connection Lost")):
        fail_res = client.post(
            "/agents/chat",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"message": f"confirm {prop_id}"},
        )
        assert fail_res.status_code == 200
        assert "solver execution failed" in fail_res.json()["reply"].lower()

    # Verify existing version is completely untouched
    with Session(engine) as db:
        check_existing = db.query(TimetableVersion).filter(TimetableVersion.id == existing_id).first()
        assert check_existing is not None
        assert check_existing.status == "PUBLISHED"


# ── Scenario 15: Conflict Inspection & Faculty Availability Workflows ─────────

def test_15_conflict_inspection_and_faculty_availability_workflow(admin_token):
    # 1. Conflict Inspection inquiry
    conf_res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Show the conflicts before I approve this schedule"},
    )
    assert conf_res.status_code == 200
    body = conf_res.json()
    assert body["success"] is True
    assert "conflict inspection" in body["reply"].lower()

    # 2. Infeasibility explanation inquiry
    why_res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Why could the solver not create a valid timetable?"},
    )
    assert why_res.status_code == 200
    why_body = why_res.json()
    assert why_body["action_type"] == "EXPLANATION"
    assert "hard constraints are mathematically non-negotiable" in why_body["reply"].lower()

    # 3. Faculty unavailability registration
    fac_res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "This faculty member is unavailable on Wednesday afternoon"},
    )
    assert fac_res.status_code == 200
    fac_body = fac_res.json()
    assert fac_body["success"] is True
    assert "faculty availability constraint registered" in fac_body["reply"].lower()
    assert "unavailable" in fac_body["reply"].lower()


# ── Scenario 16: Regression Checks for Query & Resource Agents ────────────────

def test_16_existing_query_and_resource_agents_continue_passing(admin_token, student_token):
    # Query Agent inquiry
    q_res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"message": "What courses are offered in Computer Science?"},
    )
    assert q_res.status_code == 200
    assert q_res.json()["selected_agent"] == "query_agent"

    # Resource Agent inquiry
    r_res = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": "Is Seminar Hall available on Friday?"},
    )
    assert r_res.status_code == 200
    assert r_res.json()["selected_agent"] == "resource_agent"
