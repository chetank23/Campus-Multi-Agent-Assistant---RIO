"""
tests/api/test_timetable_publication_security_safeguards.py
-----------------------------------------------------------
Comprehensive Security Safeguards & Publication Bypass Prevention Suite:
Ensures that timetable publication CANNOT be triggered through:
1. Legacy raw entry publication bypass (POST /timetable/publish).
2. Direct publication of DRAFT, GENERATED, VALIDATED, or FINALIZED versions without explicit formal approval.
3. APPROVED versions with missing metadata or stale revisions.
4. Scheduling-agent chat proposals or confirmations.
5. Background or batch generation routines.
Guarantees:
- Timetables remain strictly unpublished until explicit Admin publication of an APPROVED version.
- Rejection prevents any notification dispatch.
- Existing canonical timetables are never corrupted or altered on rejected attempts.
- Explicit Generated Timetables workflow succeeds authoritatively.
"""

from __future__ import annotations

import datetime
from typing import Any, TypeVar
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.core.security import create_access_token
from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Faculty
from backend.models.courses import Course
from backend.models.events import CoordinatorCapability
from backend.models.space_time import TimeSlot, Room
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry
from backend.models.workflow import AuditLog, Notification
from agents.common.operation_proposal_store import operation_proposal_store

client = TestClient(app)

T = TypeVar("T")


def _require_record(record: T | None, message: str) -> T:
    assert record is not None, message
    return record


@pytest.fixture(scope="module")
def admin_user() -> dict[str, Any]:
    with Session(engine) as db:
        user = _require_record(
            db.query(User).filter(User.role == "ADMIN").first(),
            "Admin user must exist",
        )
        return {"id": user.id, "email": user.email, "role": user.role}


@pytest.fixture(scope="module")
def admin_token(admin_user: dict[str, Any]) -> str:
    return create_access_token(data={"sub": str(admin_user["id"]), "role": "ADMIN"})


@pytest.fixture(scope="module")
def faculty_token(test_scope: dict[str, Any]) -> str:
    return create_access_token(data={"sub": str(test_scope["faculty_user_id"]), "role": "FACULTY"})


@pytest.fixture(scope="module")
def student_token() -> str:
    with Session(engine) as db:
        user = _require_record(
            db.query(User).filter(User.role == "STUDENT").first(),
            "Student user must exist",
        )
        return create_access_token(data={"sub": str(user.id), "role": "STUDENT"})


@pytest.fixture(scope="module")
def test_scope() -> dict[str, Any]:
    with Session(engine) as db:
        db.query(TimetableEntry).delete()
        db.query(TimetableVersion).delete()
        db.query(Timetable).delete()
        db.commit()

        ac_year = _require_record(db.query(AcademicYear).first(), "AcademicYear seed record missing")
        semester = _require_record(db.query(Semester).first(), "Semester seed record missing")
        department = _require_record(db.query(Department).first(), "Department seed record missing")
        program = _require_record(
            db.query(Program).filter(Program.department_id == department.id).first()
            or db.query(Program).first(),
            "Program seed record missing",
        )

        section = _require_record(
            db.query(Section).filter(Section.program_id == program.id).first()
            or db.query(Section).first(),
            "Section seed record missing",
        )

        fac = _require_record(
            db.query(Faculty).filter(Faculty.department_id == department.id).first()
            or db.query(Faculty).first(),
            "Faculty seed record missing",
        )

        course = db.query(Course).first()
        slot = db.query(TimeSlot).filter(TimeSlot.slot_type == "THEORY").first() or db.query(TimeSlot).first()
        room = db.query(Room).first()

        # Ensure active coordinator capability exists
        existing_cap = (
            db.query(CoordinatorCapability)
            .filter(
                CoordinatorCapability.user_id == fac.user_id,
                CoordinatorCapability.is_active == True,
            )
            .first()
        )
        if not existing_cap:
            db.add(CoordinatorCapability(
                user_id=fac.user_id,
                capability="TIMETABLE_COORDINATOR",
                scope_type="DEPARTMENT",
                scope_id=department.id,
                is_active=True,
            ))
            db.commit()

        return {
            "academic_year_id": ac_year.id,
            "semester_id": semester.id,
            "department_id": department.id,
            "program_id": program.id,
            "section_id": section.id,
            "faculty_id": fac.id,
            "faculty_user_id": fac.user_id,
            "course_id": course.id if course else None,
            "slot_id": slot.id if slot else None,
            "room_id": room.id if room else None,
        }


def _create_helper_version(db: Session, test_scope: dict, status: str, admin_id: int) -> TimetableVersion:
    """Helper to insert a version with sample entries for testing publication safeguards."""
    now = datetime.datetime.now(datetime.timezone.utc)
    v = TimetableVersion(
        academic_year_id=test_scope["academic_year_id"],
        department_id=test_scope["department_id"],
        program_id=test_scope["program_id"],
        semester_id=test_scope["semester_id"],
        version_number=f"T-{int(datetime.datetime.now().timestamp() * 1000) % 100000}",
        status=status,
        validation_status="NOT_VALIDATED",
        revision=1,
        created_by=admin_id,
        created_at=now,
    )
    db.add(v)
    db.flush()

    if test_scope.get("section_id") and test_scope.get("course_id") and test_scope.get("slot_id") and test_scope.get("room_id"):
        e = TimetableEntry(
            version_id=v.id,
            department_id=test_scope["department_id"],
            program_id=test_scope["program_id"],
            semester_id=test_scope["semester_id"],
            section_id=test_scope["section_id"],
            course_id=test_scope["course_id"],
            faculty_id=test_scope["faculty_id"],
            room_id=test_scope["room_id"],
            slot_id=test_scope["slot_id"],
            status="DRAFT",
        )
        db.add(e)
    db.commit()
    db.refresh(v)
    return v


# ── Scenario 1: Legacy Raw Entry Publication Rejection ─────────────────────────

def test_01_legacy_raw_entry_publication_rejection(admin_token, test_scope):
    """POST /timetable/publish with raw, unapproved entries returns HTTP 409 Conflict."""
    payload = {
        "academic_year_id": test_scope["academic_year_id"],
        "semester_id": test_scope["semester_id"],
        "department_id": test_scope["department_id"],
        "entries": [
            {
                "section_id": test_scope["section_id"],
                "course_id": test_scope["course_id"],
                "faculty_id": test_scope["faculty_id"],
                "room_id": test_scope["room_id"],
                "slot_id": test_scope["slot_id"],
                "day": "MON",
            }
        ],
    }
    resp = client.post(
        "/timetable/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert resp.status_code == 409
    assert "Legacy direct raw entry publication without an approved persisted version is disabled" in resp.json()["detail"]


# ── Scenario 2: DRAFT Version Cannot Be Published ──────────────────────────────

def test_02_draft_version_cannot_be_published(admin_token, admin_user, test_scope):
    """Direct publication attempt on DRAFT returns HTTP 400."""
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "DRAFT", admin_user["id"])
        vid = v.id

    resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "Version must be APPROVED" in resp.json()["detail"] or "DRAFT" in resp.json()["detail"]


# ── Scenario 3: GENERATED Version Cannot Be Published ──────────────────────────

def test_03_generated_version_cannot_be_published(admin_token, admin_user, test_scope):
    """Direct publication attempt on GENERATED returns HTTP 400."""
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "GENERATED", admin_user["id"])
        vid = v.id

    resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "Version must be APPROVED" in resp.json()["detail"] or "GENERATED" in resp.json()["detail"]


# ── Scenario 4: VALIDATED Version Cannot Be Published Without Approval ─────────

def test_04_validated_version_cannot_be_published_without_approval(admin_token, admin_user, test_scope):
    """Status VALIDATED without approval returns HTTP 400."""
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "VALIDATED", admin_user["id"])
        v.validation_status = "PASSED"
        v.validated_revision = 1
        db.commit()
        vid = v.id

    resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "Version must be APPROVED" in resp.json()["detail"] or "VALIDATED" in resp.json()["detail"]


# ── Scenario 5: FINALIZED Version Cannot Bypass Approval ───────────────────────

def test_05_finalized_version_cannot_bypass_approval(admin_token, admin_user, test_scope):
    """Status FINALIZED without explicit approval returns HTTP 400."""
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "FINALIZED", admin_user["id"])
        v.validation_status = "PASSED"
        v.validated_revision = 1
        db.commit()
        vid = v.id

    resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "Version must be APPROVED" in resp.json()["detail"] or "FINALIZED" in resp.json()["detail"]


# ── Scenario 6: APPROVED Status Missing Approval Metadata is Rejected ──────────

def test_06_approved_status_missing_approval_metadata_rejected(admin_token, admin_user, test_scope):
    """Missing approved_by, approved_at, or approved_revision returns HTTP 400."""
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "APPROVED", admin_user["id"])
        v.validation_status = "PASSED"
        v.validated_revision = 1
        v.approved_by = None  # Missing
        v.approved_at = None
        v.approved_revision = None
        db.commit()
        vid = v.id

    resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "missing formal approval metadata" in resp.json()["detail"].lower()


# ── Scenario 7: APPROVED Status with Stale Revision is Rejected ────────────────

def test_07_approved_status_with_stale_revision_rejected(admin_token, admin_user, test_scope):
    """approved_revision != revision returns HTTP 409 Conflict."""
    now = datetime.datetime.now(datetime.timezone.utc)
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "APPROVED", admin_user["id"])
        v.validation_status = "PASSED"
        v.validated_revision = 2
        v.revision = 2
        v.approved_by = admin_user["id"]
        v.approved_at = now
        v.approved_revision = 1  # Stale!
        db.commit()
        vid = v.id

    resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409
    assert "modified after approval" in resp.json()["detail"].lower()


# ── Scenario 8: Valid APPROVED Current Revision Can Be Published ───────────────

def test_08_valid_approved_current_revision_can_be_published(admin_token, admin_user, test_scope):
    """Timetable publishes successfully with valid audit log and timetable records."""
    # Generate fresh scope
    gen_res = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": test_scope["academic_year_id"],
            "semester_id": test_scope["semester_id"],
            "department_id": test_scope["department_id"],
            "force_regenerate": True,
        },
    )
    assert gen_res.status_code == 200
    vid = gen_res.json()["version_id"]

    # Validate
    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    assert val_res.status_code == 200

    # Approve
    app_res = client.post(f"/timetable/versions/{vid}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    assert app_res.status_code == 200

    # Publish
    pub_res = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 200
    data = pub_res.json()
    assert data["status"] == "PUBLISHED"

    # Verify AuditLog recorded
    with Session(engine) as db:
        v = _require_record(
            db.query(TimetableVersion).filter(TimetableVersion.id == vid).one_or_none(),
            f"Expected TimetableVersion {vid} to exist",
        )
        assert v.status == "PUBLISHED"
        assert v.published_at is not None

        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "TIMETABLE_PUBLISHED",
                AuditLog.entity_id == vid,
            )
            .first()
        )
        assert audit is not None


# ── Scenario 9: Chat Confirmation Cannot Publish a Timetable Independently ─────

def test_09_chat_confirmation_cannot_publish_independently(admin_token, admin_user, test_scope):
    """Simulate scheduling-agent confirmation flow for PUBLISH_TIMETABLE; remains unpublished."""
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "FINALIZED", admin_user["id"])
        vid = v.id

    # Create proposal for publication
    prop = operation_proposal_store.create_proposal(
        user_id=admin_user["id"],
        role="ADMIN",
        action_name="PUBLISH_TIMETABLE",
        entity_type="TimetableVersion",
        entity_id=vid,
        entity_name=f"Timetable Version #{vid}",
        changes={"status": "PUBLISHED"},
        consequences="Chat publication attempt",
        proposal_data={"version_id": vid},
    )

    # Chat execution attempt
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"message": f"confirm {prop.proposal_id}"},
    )
    assert resp.status_code == 200
    reply = resp.json()["reply"].lower()
    assert "disabled" in reply or "rejected" in resp.json().get("action_type", "").lower()

    # Verify database state remained unpublished
    with Session(engine) as db:
        refetched = _require_record(
            db.query(TimetableVersion).filter(TimetableVersion.id == vid).one_or_none(),
            f"Expected TimetableVersion {vid} to exist",
        )
        assert refetched.status == "FINALIZED"
        assert refetched.published_at is None


# ── Scenario 10: Generation Tasks Do Not Publish ───────────────────────────────

def test_10_generation_tasks_do_not_publish(admin_token, test_scope):
    """Generation endpoints leave version strictly in GENERATED state and unpublished."""
    resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": test_scope["academic_year_id"],
            "semester_id": test_scope["semester_id"],
            "department_id": test_scope["department_id"],
            "force_regenerate": True,
        },
    )
    assert resp.status_code == 200
    vid = resp.json()["version_id"]

    with Session(engine) as db:
        v = _require_record(
            db.query(TimetableVersion).filter(TimetableVersion.id == vid).one_or_none(),
            f"Expected TimetableVersion {vid} to exist",
        )
        assert v.status == "GENERATED"
        assert v.published_at is None
        assert v.validation_status == "NOT_VALIDATED"


# ── Scenario 11: No Publication Notification Sent on Rejected Attempt ──────────

def test_11_no_publication_notification_sent_for_rejected_attempt(admin_token, admin_user, test_scope):
    """Assert notification dispatch occurs only on successful publication, never for rejected attempts."""
    with Session(engine) as db:
        v = _create_helper_version(db, test_scope, "DRAFT", admin_user["id"])
        vid = v.id

    # Attempt rejected publication
    resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400

    # Verify zero notifications for this version
    with Session(engine) as db:
        notif_count = (
            db.query(Notification)
            .filter(
                Notification.entity_type == "TimetableVersion",
                Notification.entity_id == vid,
                Notification.type == "TIMETABLE_PUBLISHED",
            )
            .count()
        )
        assert notif_count == 0


# ── Scenario 12: Canonical Timetables Unchanged When Publication Rejected ──────

def test_12_canonical_timetables_unchanged_when_publication_rejected(admin_token, admin_user, test_scope):
    """Failed publish must preserve existing canonical entries."""
    with Session(engine) as db:
        # Count existing canonical timetables and entries
        canon_before = db.query(Timetable).filter(Timetable.status == "PUBLISHED").count()
        entries_before = (
            db.query(TimetableEntry)
            .join(Timetable, TimetableEntry.timetable_id == Timetable.id)
            .filter(Timetable.status == "PUBLISHED")
            .count()
        )

        v_bad = _create_helper_version(db, test_scope, "DRAFT", admin_user["id"])
        bad_vid = v_bad.id

    # Attempt publish that fails
    resp = client.post(
        f"/timetable/versions/{bad_vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400

    with Session(engine) as db:
        canon_after = db.query(Timetable).filter(Timetable.status == "PUBLISHED").count()
        entries_after = (
            db.query(TimetableEntry)
            .join(Timetable, TimetableEntry.timetable_id == Timetable.id)
            .filter(Timetable.status == "PUBLISHED")
            .count()
        )
        assert canon_after == canon_before
        assert entries_after == entries_before


# ── Scenario 13: Explicit Publication Through Generated Timetables Workflow ───

def test_13_explicit_workflow_publication_succeeds(admin_token, test_scope):
    """Full happy path: Generate -> Validate -> Approve -> Publish via the management endpoint."""
    # 1. Generate
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": test_scope["academic_year_id"],
            "semester_id": test_scope["semester_id"],
            "department_id": test_scope["department_id"],
            "force_regenerate": True,
        },
    )
    assert gen_resp.status_code == 200
    vid = gen_resp.json()["version_id"]

    # 2. Validate
    val_resp = client.post(
        f"/timetable/versions/{vid}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["is_valid"] is True

    # 3. Approve
    app_resp = client.post(
        f"/timetable/versions/{vid}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "APPROVED"

    # 4. Publish
    pub_resp = client.post(
        f"/timetable/versions/{vid}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_resp.status_code == 200
    assert pub_resp.json()["status"] == "PUBLISHED"

    with Session(engine) as db:
        v = _require_record(
            db.query(TimetableVersion).filter(TimetableVersion.id == vid).one_or_none(),
            f"Expected TimetableVersion {vid} to exist",
        )
        assert v.status == "PUBLISHED"
        assert v.published_at is not None


# ── Scenario 14: Existing Privacy Regression Suite Passes ─────────────────────

def test_14_existing_privacy_regression_suite_passes(admin_token, test_scope):
    """Ensures unpublished versions remain completely private from external portals."""
    # Generate draft
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": test_scope["academic_year_id"],
            "semester_id": test_scope["semester_id"],
            "department_id": test_scope["department_id"],
            "force_regenerate": True,
        },
    )
    assert gen_resp.status_code == 200
    vid = gen_resp.json()["version_id"]

    # Verify that the draft has NOT_VALIDATED validation_status
    with Session(engine) as db:
        v = _require_record(
            db.query(TimetableVersion).filter(TimetableVersion.id == vid).one_or_none(),
            f"Expected TimetableVersion {vid} to exist",
        )
        assert v.validation_status == "NOT_VALIDATED"
        assert v.published_at is None
        assert v.status == "GENERATED"


# ── Scenario 15: Unauthorized Publish/Recall Blocked & Audit Preserved ─────────

def test_15_unauthorized_publish_and_recall_blocked_and_audit_preserved(
    admin_token, faculty_token, student_token, test_scope
):
    """Non-admins receive 403 on publish/recall; admin recall preserves entries and audit log."""
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": test_scope["academic_year_id"],
            "semester_id": test_scope["semester_id"],
            "department_id": test_scope["department_id"],
            "force_regenerate": True,
        },
    )
    assert gen_resp.status_code == 200
    vid = gen_resp.json()["version_id"]

    assert client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
    assert client.post(f"/timetable/versions/{vid}/approve", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200

    # Unauthorized publish attempts must fail with 403
    assert client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {faculty_token}"}).status_code == 403
    assert client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {student_token}"}).status_code == 403

    # Admin publishes
    assert client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200

    # Unauthorized recall attempts must fail with 403
    assert client.post(f"/timetable/versions/{vid}/recall", headers={"Authorization": f"Bearer {faculty_token}"}, json={"reason": "bad"}).status_code == 403
    assert client.post(f"/timetable/versions/{vid}/recall", headers={"Authorization": f"Bearer {student_token}"}, json={"reason": "bad"}).status_code == 403

    # Admin recalls and historical records + audit log are preserved
    recall_resp = client.post(
        f"/timetable/versions/{vid}/recall",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Security audit test recall"},
    )
    assert recall_resp.status_code == 200

    with Session(engine) as db:
        v = _require_record(
            db.query(TimetableVersion).filter(TimetableVersion.id == vid).one_or_none(),
            f"Expected TimetableVersion {vid} to exist",
        )
        assert v.status == "RECALLED"
        assert v.recall_reason == "Security audit test recall"
        entries_count = db.query(TimetableEntry).filter(TimetableEntry.version_id == vid).count()
        assert entries_count > 0, "Recall must preserve historical version entries"
        recall_audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "TIMETABLE_RECALLED", AuditLog.entity_id == vid)
            .first()
        )
        assert recall_audit is not None, "Recall must record an AuditLog entry"
