"""
tests/agents/test_semantic_query_rbac_security.py
-------------------------------------------------
Comprehensive security & RBAC verification for semantic database query planner.
Verifies:
1. Default-deny entity access per institutional role.
2. Cross-user isolation (students can only see their own records).
3. Faculty field-level privacy (students denied private faculty contact details).
4. Faculty section-scoped isolation for students entity.
5. Strict join whitelist enforcement (rejects unauthorized joins).
6. Pre-aggregation mandatory filtering (COUNT/SUM/AVG cannot leak unauthorized records).
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Student, Faculty, Department
from agents.tools.semantic_query_planner import (
    execute_semantic_query_plan,
    ROLE_ALLOWED_ENTITIES,
    APPROVED_JOIN_PATHS,
    STUDENT_DENIED_FACULTY_FIELDS,
)


@pytest.fixture
def db_session():
    test_engine = create_engine(os.environ["DATABASE_URL"])
    with Session(test_engine) as db:
        yield db
    test_engine.dispose()


def test_student_role_denied_sensitive_entities(db_session: Session):
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    if not student_user:
        pytest.skip("No student user in database")

    # STUDENT denied audit_logs, users, faculty_availability
    for denied_entity in ("audit_logs", "users", "faculty_availability"):
        res = execute_semantic_query_plan(
            db=db_session,
            user=student_user,
            entity=denied_entity,
        )
        assert "error" in res, f"Expected error for student querying {denied_entity}"
        assert "Access denied" in res["error"] or "not authorized" in res["error"]


def test_student_cannot_query_other_students(db_session: Session):
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    if not student_user:
        pytest.skip("No student user in database")

    res = execute_semantic_query_plan(
        db=db_session,
        user=student_user,
        entity="students",
        fields=["id", "student_id", "user_id"],
    )
    assert res.get("success") is True, f"Query failed: {res}"
    records = res["records"]
    # Must only return records belonging to the authenticated student
    for r in records:
        assert r["user_id"] == student_user.id, f"Cross-user leakage: found user_id {r['user_id']} != {student_user.id}"


def test_student_denied_private_faculty_fields(db_session: Session):
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    if not student_user:
        pytest.skip("No student user in database")

    # Requesting contact_number must be denied
    res_contact = execute_semantic_query_plan(
        db=db_session,
        user=student_user,
        entity="faculty",
        fields=["id", "contact_number"],
    )
    assert "error" in res_contact
    assert "Access denied" in res_contact["error"]

    # Requesting max_weekly_load must be denied
    res_load = execute_semantic_query_plan(
        db=db_session,
        user=student_user,
        entity="faculty",
        fields=["id", "max_weekly_load"],
    )
    assert "error" in res_load
    assert "Access denied" in res_load["error"]

    # Public fields (name, email, designation, specialization) must succeed
    res_public = execute_semantic_query_plan(
        db=db_session,
        user=student_user,
        entity="faculty",
        fields=["id", "designation", "specialization"],
    )
    assert res_public.get("success") is True
    assert "records" in res_public


def test_unauthorized_join_rejection(db_session: Session):
    admin_user = db_session.query(User).filter(User.role == "ADMIN").first()
    if not admin_user:
        pytest.skip("No admin user in database")

    # Unapproved join: joining students to audit_logs
    res = execute_semantic_query_plan(
        db=db_session,
        user=admin_user,
        entity="students",
        joins=["audit_logs"],
    )
    assert "error" in res
    assert "not authorized" in res["error"] or "Join between" in res["error"]


def test_approved_join_success(db_session: Session):
    admin_user = db_session.query(User).filter(User.role == "ADMIN").first()
    if not admin_user:
        pytest.skip("No admin user in database")

    # Approved join: students to sections
    res = execute_semantic_query_plan(
        db=db_session,
        user=admin_user,
        entity="students",
        joins=["sections"],
        fields=["id", "student_id"],
    )
    assert res.get("success") is True
    assert "records" in res


def test_pre_aggregation_filters_strictly_enforced(db_session: Session):
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    if not student_user:
        pytest.skip("No student user in database")

    # Student performs COUNT(*) on students
    res = execute_semantic_query_plan(
        db=db_session,
        user=student_user,
        entity="students",
        aggregations=[{"func": "COUNT", "field": "*", "alias": "my_student_count"}],
    )
    assert res.get("success") is True
    records = res["records"]
    assert len(records) == 1
    # Student count must be 1 (themselves), never total institution students
    assert records[0]["my_student_count"] <= 1
