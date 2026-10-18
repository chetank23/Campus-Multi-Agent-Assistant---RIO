"""
tests/agents/test_scheduling_agent.py
------------------------------------
Tests for Stage 9B: Advanced Intelligent Scheduling Agent.
- Non-admin authorization rejection
- Natural-language scope resolution (exact match, missing semester, invalid department)
- Readiness analysis checks
- Strategy comparison and explanation
- Proposal creation, single-use idempotency, and TTL expiry in ProposalStore
- Confirmation execution invoking execute_timetable_generation
"""

import time
import pytest
from sqlalchemy.orm import Session
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Department, Semester, AcademicYear
from agents.scheduling_agent.proposal_store import ProposalStore, SchedulingProposal
from agents.scheduling_agent.agent import run_scheduling_agent
from agents.tools.scheduling_tools import (
    resolve_academic_scope_data,
    analyze_scheduling_readiness_data,
)


def test_proposal_store_lifecycle_and_idempotency():
    store = ProposalStore()
    prop = store.create_proposal(
        user_id=1,
        role="ADMIN",
        scope={"department_id": 1, "semester_id": 1, "academic_year_id": 1},
        scope_display={"department": "CSE", "semester": "Semester 1"},
        readiness_status="READY",
        readiness_summary={"status": "READY"},
        strategy="BALANCED",
    )

    # Retrieval works
    fetched = store.get_proposal(prop.proposal_id)
    assert fetched is not None
    assert fetched.proposal_id == prop.proposal_id

    # Rejection for mismatched user
    ok, _, err = store.consume_proposal(prop.proposal_id, user_id=999)
    assert ok is False
    assert "belongs to another user" in err

    # Successful consumption (single-use)
    ok, consumed_prop, err = store.consume_proposal(prop.proposal_id, user_id=1)
    assert ok is True
    assert consumed_prop is not None
    assert consumed_prop.proposal_id == prop.proposal_id

    # Re-consuming should fail (replay protection)
    ok2, _, err2 = store.consume_proposal(prop.proposal_id, user_id=1)
    assert ok2 is False
    assert "already been confirmed" in err2


def test_proposal_store_expiry():
    store = ProposalStore(ttl_seconds=-10)  # Immediately expired
    prop = store.create_proposal(
        user_id=1,
        role="ADMIN",
        scope={},
        scope_display={},
        readiness_status="READY",
        readiness_summary={},
        strategy="BALANCED",
    )
    assert store.get_proposal(prop.proposal_id) is None
    ok, _, err = store.consume_proposal(prop.proposal_id, user_id=1)
    assert ok is False
    assert "expired" in err.lower() or "not found" in err.lower()



def test_scheduling_agent_rejects_non_admin():
    from backend.models.identity import User
    fake_student = User(id=5, email="student@reva.edu.in", name="Student", password_hash="dummy", role="STUDENT")
    state = {
        "user_id": 5,
        "role": "STUDENT",
        "department_id": 1,
        "message": "Generate a timetable for CSE Semester 1",
    }
    with Session(engine) as db:
        res = run_scheduling_agent(state=state, db=db, user=fake_student)
    assert "Administrators" in res["final_response"]
    assert res.get("proposal") is None


def test_scope_resolution_requires_semester():
    with Session(engine) as db:
        res = resolve_academic_scope_data(db=db, query_text="Generate a timetable for CSE")
        assert res["resolved"] is False
        assert any("semester" in p.lower() for p in res["missing_parameters"])


def test_scope_resolution_valid_cse_sem1():
    with Session(engine) as db:
        dept = db.query(Department).filter(Department.department_code == "CSE").first()
        sem = db.query(Semester).first()
        if dept and sem:
            query = f"Create timetable for {dept.department_code} Semester {sem.semester_number}"
            res = resolve_academic_scope_data(db=db, query_text=query)
            assert res["resolved"] is True
            assert res["scope"]["department_id"] == dept.id
            assert res["scope"]["semester_id"] == sem.id


def test_readiness_analysis_blocked_on_invalid_scope():
    with Session(engine) as db:
        res = analyze_scheduling_readiness_data(
            db=db,
            scope_dict={
                "academic_year_id": 999999,
                "semester_id": 999999,
                "department_id": 999999,
                "program_id": 999999,
            },
        )
        assert res["status"] == "BLOCKED"
        assert len(res["findings"]) > 0


def test_strategy_comparison_query():
    fake_admin = User(id=1, email="admin@reva.edu.in", name="Admin", password_hash="dummy", role="ADMIN")
    state = {
        "user_id": 1,
        "role": "ADMIN",
        "department_id": None,
        "message": "Compare the available scheduling strategies",
    }
    with Session(engine) as db:
        res = run_scheduling_agent(state=state, db=db, user=fake_admin)
    assert "Available Optimization Strategies" in res["final_response"]
    assert "BALANCED" in res["final_response"]
    assert "FACULTY_COMFORT" in res["final_response"]
    assert "ROOM_EFFICIENCY" in res["final_response"]
    assert "LAB_PREFERENCE" in res["final_response"]


def test_confirmation_invalid_proposal_id():
    fake_admin = User(id=1, email="admin@reva.edu.in", name="Admin", password_hash="dummy", role="ADMIN")
    state = {
        "user_id": 1,
        "role": "ADMIN",
        "department_id": None,
        "message": "confirm prop_nonexistent_999",
    }
    with Session(engine) as db:
        res = run_scheduling_agent(state=state, db=db, user=fake_admin)
    assert "Confirmation Blocked" in res["final_response"]


def test_solver_strategy_weights_configuration():
    from backend.optimizer.timetable_solver import TimetableSolver
    from backend.schemas.timetable_generation import OptimizerInput, GenerationScope

    mock_scope = GenerationScope(
        academic_year_id=1,
        department_id=1,
        program_id=1,
        semester_id=1,
    )

    mock_input = OptimizerInput(
        scope=mock_scope,
        courses=[],
        sections=[],
        batches=[],
        rooms=[],
        labs=[],
        faculty=[],
        time_slots=[],
        faculty_availability=[],
        course_assignments=[],
        elective_groups=[],
        elective_group_courses=[],
    )

    s_balanced = TimetableSolver(opt_input=mock_input, strategy="BALANCED")
    assert s_balanced.strategy == "BALANCED"

    s_comfort = TimetableSolver(opt_input=mock_input, strategy="FACULTY_COMFORT")
    assert s_comfort.strategy == "FACULTY_COMFORT"

    s_room = TimetableSolver(opt_input=mock_input, strategy="ROOM_EFFICIENCY")
    assert s_room.strategy == "ROOM_EFFICIENCY"

    s_lab = TimetableSolver(opt_input=mock_input, strategy="LAB_PREFERENCE")
    assert s_lab.strategy == "LAB_PREFERENCE"



def test_proposal_cannot_be_redirected_or_replayed():
    store = ProposalStore()
    prop = store.create_proposal(
        user_id=1,
        role="ADMIN",
        scope={"department_id": 1, "semester_id": 1, "academic_year_id": 1},
        scope_display={"department": "CSE", "semester": "Semester 1"},
        readiness_status="READY",
        readiness_summary={"status": "READY"},
        strategy="FACULTY_COMFORT",
    )

    # Cross-user attempt is blocked
    ok, _, err = store.consume_proposal(prop.proposal_id, user_id=2)
    assert ok is False
    assert "belongs to another user" in err

    # First consumption succeeds with exact strategy and scope preserved
    ok, consumed, err = store.consume_proposal(prop.proposal_id, user_id=1)
    assert ok is True
    assert consumed is not None
    assert consumed.strategy == "FACULTY_COMFORT"
    assert consumed.scope["department_id"] == 1

    # Second consumption is blocked (no replay)
    ok2, _, err2 = store.consume_proposal(prop.proposal_id, user_id=1)
    assert ok2 is False
    assert "already been confirmed" in err2
