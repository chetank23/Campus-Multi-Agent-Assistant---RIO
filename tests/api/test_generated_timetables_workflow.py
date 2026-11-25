import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Faculty
from backend.models.events import CoordinatorCapability
from backend.models.space_time import TimeSlot
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry, TimetableChangeHistory
from backend.models.workflow import Notification, AuditLog

client = TestClient(app)


def _login(email: str, password: str = "Test@1234"):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    if resp.status_code == 200:
        return resp.json()["access_token"]
    return None


@pytest.fixture(scope="module")
def admin_token():
    token = _login("admin@campus.edu")
    if not token:
        pytest.skip("Admin seed user unavailable")
    return token


@pytest.fixture(scope="module")
def faculty_token():
    return _login("faculty@campus.edu")


@pytest.fixture(scope="module")
def test_scope():
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        semester = db.query(Semester).first()
        department = db.query(Department).first()
        program = db.query(Program).first()
        if not (ac_year and semester and department and program):
            pytest.skip("Missing academic seed data")
        return {
            "academic_year_id": ac_year.id,
            "semester_id": semester.id,
            "department_id": department.id,
            "program_id": program.id,
        }


def test_1_generation_persists_draft_without_publishing(admin_token, test_scope):
    """
    Generating a timetable MUST persist it as a draft and NEVER automatically publish it.
    """
    resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=test_scope,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    version_id = data["version_id"]
    assert version_id is not None

    with Session(engine) as db:
        version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
        assert version is not None
        assert version.status == "GENERATED"
        assert version.status != "PUBLISHED"
        assert version.revision == 1
        assert version.approved_by is None
        assert version.approved_at is None
        assert version.approved_revision is None

        # Verify no canonical published timetables were created by generation
        published_canonicals = (
            db.query(Timetable)
            .filter(
                Timetable.academic_year_id == test_scope["academic_year_id"],
                Timetable.semester_id == test_scope["semester_id"],
                Timetable.status == "PUBLISHED",
            )
            .all()
        )
        # Any published canonicals that might exist must NOT reference entries from this newly generated version
        for canon in published_canonicals:
            ver_entries = [e for e in canon.timetable_entries if e.version_id == version_id]
            assert len(ver_entries) == 0


def test_2_versions_summary_and_filters(admin_token, test_scope):
    """
    Verify summary card metrics endpoint and enriched filtering capabilities.
    """
    summary_resp = client.get(
        "/timetable/versions/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert "total_generated" in summary
    assert "awaiting_review" in summary
    assert "approved" in summary
    assert "published" in summary
    assert "archived" in summary
    assert summary["total_generated"] >= 1

    # Filter by department and status
    list_resp = client.get(
        f"/timetable/versions?department_id={test_scope['department_id']}&status=GENERATED",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    versions = list_resp.json()
    assert isinstance(versions, list)
    for v in versions:
        assert v["department_id"] == test_scope["department_id"]
        assert v["status"] == "GENERATED"
        assert "entry_count" in v
        assert "section_names" in v


def test_3_unapproved_timetable_cannot_be_published(admin_token, test_scope):
    """
    Attempting to publish an unapproved/unvalidated timetable must be rejected.
    """
    # Create fresh generated draft
    resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert resp.status_code == 200, resp.text
    version_id = resp.json()["version_id"]

    # Direct publish should fail with 400 Bad Request
    pub_resp = client.post(
        f"/timetable/versions/{version_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_resp.status_code in (400, 422), pub_resp.text
    assert "APPROVED" in pub_resp.text or "FINALIZED" in pub_resp.text or "status" in pub_resp.text


def test_4_approve_timetable_lifecycle(admin_token, test_scope):
    """
    Approval is a distinct step: verifies constraints, transitions status to APPROVED,
    records approved_by, approved_at, and approved_revision.
    """
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    version_id = gen_resp.json()["version_id"]

    # Validate first
    val_resp = client.post(
        f"/timetable/versions/{version_id}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert val_resp.status_code == 200

    # Formally Approve
    approve_resp = client.post(
        f"/timetable/versions/{version_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    app_data = approve_resp.json()
    assert app_data["status"] == "APPROVED"
    assert app_data["version_id"] == version_id

    with Session(engine) as db:
        version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
        assert version is not None
        assert version.status == "APPROVED"
        assert version.approved_by is not None
        assert version.approved_at is not None
        assert version.approved_revision == version.revision


def test_5_editing_after_approval_invalidates_approval(admin_token, test_scope):
    """
    CRITICAL: Any edits saved after approval MUST invalidate the prior approval,
    increment the revision, reset status to REVIEWED, and clear approved_by/approved_at/approved_revision.
    """
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    version_id = gen_resp.json()["version_id"]

    # Approve
    app_resp = client.post(
        f"/timetable/versions/{version_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert app_resp.status_code == 200
    init_rev = app_resp.json()["revision"]

    # Find an entry and an instructional slot to move to
    with Session(engine) as db:
        entry = (
            db.query(TimetableEntry)
            .filter(TimetableEntry.version_id == version_id, TimetableEntry.status != "CANCELLED")
            .first()
        )
        assert entry is not None
        entry_id = entry.id
        current_slot_id = entry.slot_id

        # Find another slot that is valid
        other_slot = (
            db.query(TimeSlot)
            .filter(TimeSlot.id != current_slot_id, TimeSlot.slot_type == "CLASS")
            .first()
        )
        assert other_slot is not None
        target_slot_id = other_slot.id

    # Check move options to ensure we pick a valid move
    opts_resp = client.get(
        f"/timetable/versions/{version_id}/move-options?entry_id={entry_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert opts_resp.status_code == 200
    valid_opts = [s for s in opts_resp.json()["options"] if s["can_move"]]
    if valid_opts:
        target_slot_id = valid_opts[0]["slot_id"]

    # Save move arrangement
    save_resp = client.post(
        f"/timetable/versions/{version_id}/arrangements",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "expected_revision": init_rev,
            "moves": [{"entry_id": entry_id, "target_slot_id": target_slot_id}],
            "note": "Test post-approval invalidation",
        },
    )
    assert save_resp.status_code == 200, save_resp.text
    save_data = save_resp.json()
    assert save_data["revision"] == init_rev + 1
    assert save_data["status"] == "REVIEWED"

    # Verify database state: approval MUST be completely cleared
    with Session(engine) as db:
        version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
        assert version is not None
        assert version.status == "REVIEWED"
        assert version.revision == init_rev + 1
        assert version.approved_by is None
        assert version.approved_at is None
        assert version.approved_revision is None

    # Now publishing must be blocked because the approval was invalidated!
    pub_block_resp = client.post(
        f"/timetable/versions/{version_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_block_resp.status_code in (400, 409), pub_block_resp.text


def test_6_coordinator_resolution_and_preflight(admin_token, test_scope):
    """
    Coordinator resolution must query authoritative DB relations:
    CoordinatorCapability and Section.class_teacher.
    """
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    version_id = gen_resp.json()["version_id"]

    preflight_resp = client.get(
        f"/timetable/versions/{version_id}/coordinators",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert preflight_resp.status_code == 200, preflight_resp.text
    pf = preflight_resp.json()
    assert pf["version_id"] == version_id
    assert "coordinators" in pf
    assert "coordinator_count" in pf
    assert "can_publish" in pf
    assert "blocking_reasons" in pf


def test_7_publish_blocked_when_zero_coordinators(admin_token, test_scope):
    """
    If a scope has 0 coordinators mapped, publication MUST be blocked with an actionable message.
    """
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    version_id = gen_resp.json()["version_id"]

    with Session(engine) as db:
        version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
        entries = db.query(TimetableEntry).filter(TimetableEntry.version_id == version_id).all()
        sec_ids = {e.section_id for e in entries if e.section_id}

        # Temporarily clear capabilities and class teachers for isolation test
        old_caps = db.query(CoordinatorCapability).filter(CoordinatorCapability.is_active == True).all()  # noqa: E712
        for c in old_caps:
            c.is_active = False

        old_cts = {}
        for sid in sec_ids:
            sec = db.query(Section).filter(Section.id == sid).first()
            if sec and sec.class_teacher_id:
                old_cts[sid] = sec.class_teacher_id
                sec.class_teacher_id = None
        db.commit()

        try:
            # Approve the version
            assert version is not None
            version.status = "APPROVED"
            version.approved_revision = version.revision
            db.commit()

            # Attempt publish with 0 coordinators
            pub_resp = client.post(
                f"/timetable/versions/{version_id}/publish",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert pub_resp.status_code == 422, pub_resp.text
            assert "No eligible coordinators mapped" in pub_resp.text
        finally:
            # Restore state
            for c in old_caps:
                c.is_active = True
            for sid, ctid in old_cts.items():
                s = db.query(Section).filter(Section.id == sid).first()
                if s:
                    s.class_teacher_id = ctid
            db.commit()


def test_8_publish_approved_version_with_coordinators_succeeds(admin_token, test_scope):
    """
    Publishing an approved version with coordinators:
    - Atomically creates canonical records.
    - Transitions version status to PUBLISHED.
    - Dispatches notifications to coordinators linking to /faculty/dept-timetable.
    """
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    version_id = gen_resp.json()["version_id"]

    # Ensure at least one coordinator is mapped
    with Session(engine) as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        faculty_user = db.query(Faculty).first()
        assert admin_user and faculty_user

        cap = db.query(CoordinatorCapability).filter(
            CoordinatorCapability.user_id == faculty_user.user_id,
            CoordinatorCapability.capability == "TIMETABLE_COORDINATOR",
        ).first()
        if not cap:
            cap = CoordinatorCapability(
                user_id=faculty_user.user_id,
                capability="TIMETABLE_COORDINATOR",
                scope_type="GLOBAL",
                is_active=True,
                assigned_by=admin_user.id,
            )
            db.add(cap)
        else:
            cap.is_active = True
        db.commit()

    # Preflight check should now show coordinators available
    preflight = client.get(
        f"/timetable/versions/{version_id}/coordinators",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    assert preflight["coordinator_count"] >= 1

    # Formally approve
    app_res = client.post(
        f"/timetable/versions/{version_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert app_res.status_code == 200

    # Publish
    pub_res = client.post(
        f"/timetable/versions/{version_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_res.status_code == 200, pub_res.text
    pub_data = pub_res.json()
    assert pub_data["status"] == "PUBLISHED"
    assert pub_data["total_entries_published"] > 0

    # Verify database state & coordinator notification
    with Session(engine) as db:
        ver = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
        assert ver is not None
        assert ver.status == "PUBLISHED"
        assert ver.published_at is not None

        # Check coordinator notification was dispatched
        coord_notif = (
            db.query(Notification)
            .filter(
                Notification.entity_type == "TimetableVersion",
                Notification.entity_id == version_id,
                Notification.link == "/faculty/dept-timetable",
            )
            .first()
        )
        assert coord_notif is not None
        assert coord_notif.title is not None
        assert "Timetable Published" in coord_notif.title


def test_9_archive_and_delete_version(admin_token, test_scope):
    """
    Test archiving a draft version and deleting an unpublished version.
    """
    gen_resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    v1_id = gen_resp.json()["version_id"]

    # Archive
    arch_resp = client.post(
        f"/timetable/versions/{v1_id}/archive",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert arch_resp.status_code == 200
    with Session(engine) as db:
        v1 = db.query(TimetableVersion).filter(TimetableVersion.id == v1_id).first()
        assert v1 is not None
        assert v1.status == "ARCHIVED"

    # Delete another draft
    gen2 = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen2.status_code == 200, gen2.text
    v2_id = gen2.json()["version_id"]

    del_resp = client.delete(
        f"/timetable/versions/{v2_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert del_resp.status_code == 200
    with Session(engine) as db:
        v2 = db.query(TimetableVersion).filter(TimetableVersion.id == v2_id).first()
        assert v2 is None


def test_10_duplicate_prevention_blocks_accidental_regeneration(admin_token, test_scope):
    """
    Duplicate prevention:
    Generating a timetable when an active or draft version exists must return 409 Conflict
    unless force_regenerate=True is explicitly supplied.
    """
    # 1. Ensure an active timetable exists for this scope
    gen1 = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen1.status_code == 200, gen1.text
    v1_id = gen1.json()["version_id"]
    assert v1_id is not None

    # 2. Attempt duplicate generation without force_regenerate -> Must 409 Conflict
    gen_dup = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=test_scope,
    )
    assert gen_dup.status_code == 409, gen_dup.text
    err_body = gen_dup.json()
    assert "already exists for this academic scope" in err_body["detail"]
    assert f"Version {v1_id}" in err_body["detail"]

    # 3. Supply force_regenerate=True -> Must succeed and supersede/replace
    gen_force = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen_force.status_code == 200, gen_force.text
    v2_id = gen_force.json()["version_id"]
    assert v2_id is not None
    assert v2_id != v1_id


def test_11_scope_check_endpoint(admin_token, test_scope):
    """
    Preflight scope check endpoint returns has_existing=True and detailed version info
    when an active timetable exists, and has_existing=False when none exists.
    """
    # Active version exists from test_10
    check_resp = client.get(
        f"/timetable/scope/check?academic_year_id={test_scope['academic_year_id']}&semester_id={test_scope['semester_id']}&department_id={test_scope['department_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert check_resp.status_code == 200, check_resp.text
    data = check_resp.json()
    assert data["has_existing"] is True
    assert data["existing_version"] is not None
    assert data["existing_version"]["id"] is not None
    assert data["existing_version"]["status"] in ("DRAFT", "GENERATED", "REVIEWED", "VALIDATED", "APPROVED", "PUBLISHED")

    # Scope check on non-existent department ID
    empty_check = client.get(
        f"/timetable/scope/check?academic_year_id={test_scope['academic_year_id']}&semester_id={test_scope['semester_id']}&department_id=99999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert empty_check.status_code == 200
    assert empty_check.json()["has_existing"] is False


def test_12_validation_status_tracking(admin_token, test_scope):
    """
    Validation status, error counts, warning counts, and validated_at are persisted
    when calling the validate endpoint.
    """
    gen = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    assert gen.status_code == 200
    vid = gen.json()["version_id"]

    val_resp = client.post(
        f"/timetable/versions/{vid}/validate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()

    with Session(engine) as db:
        ver = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert ver is not None
        assert ver.validation_status in ("PASSED", "PASSED_WITH_WARNINGS", "FAILED")
        assert ver.validated_at is not None
        if val_data["is_valid"]:
            assert ver.validation_errors_count == 0
            assert ver.validation_status in ("PASSED", "PASSED_WITH_WARNINGS")
        else:
            assert ver.validation_status == "FAILED"
            assert ver.validation_errors_count > 0


def test_13_recall_published_timetable(admin_token, test_scope):
    """
    Recall lifecycle:
    1. Timetable is approved and published.
    2. Admin recalls with mandatory reason.
    3. Version status becomes RECALLED; recaller, recall_at, recall_reason recorded.
    4. Canonical Timetable status becomes RECALLED; entries unlinked.
    5. AuditLog created; Coordinator notification dispatched.
    """
    # 1. Generate & publish
    gen = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    vid = gen.json()["version_id"]

    # Ensure coordinator exists
    with Session(engine) as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        faculty_user = db.query(Faculty).first()
        assert admin_user and faculty_user
        cap = db.query(CoordinatorCapability).filter(
            CoordinatorCapability.user_id == faculty_user.user_id,
            CoordinatorCapability.capability == "TIMETABLE_COORDINATOR",
        ).first()
        if not cap:
            db.add(CoordinatorCapability(
                user_id=faculty_user.user_id,
                capability="TIMETABLE_COORDINATOR",
                scope_type="GLOBAL",
                is_active=True,
                assigned_by=admin_user.id,
            ))
            db.commit()

    # Validate, approve & publish
    client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    client.post(f"/timetable/versions/{vid}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    pub_res = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 200, pub_res.text

    # 2. Attempt recall without reason -> Must fail with 422
    fail_recall = client.post(
        f"/timetable/versions/{vid}/recall",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "  "},
    )
    assert fail_recall.status_code == 422, fail_recall.text

    # 3. Recall with valid reason
    recall_reason = "Faculty emergency reassignment & laboratory maintenance schedule clash"
    rec_res = client.post(
        f"/timetable/versions/{vid}/recall",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": recall_reason},
    )
    assert rec_res.status_code == 200, rec_res.text
    rec_data = rec_res.json()
    assert rec_data["status"] == "RECALLED"
    assert rec_data["recall_reason"] == recall_reason
    assert rec_data["recalled_at"] is not None

    # 4. Verify database state
    with Session(engine) as db:
        ver = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        assert ver is not None
        assert ver.status == "RECALLED"
        assert ver.recalled_by is not None
        assert ver.recalled_at is not None
        assert ver.recall_reason == recall_reason

        # Canonical timetable must be RECALLED and entries unlinked
        canon = db.query(Timetable).filter(
            Timetable.academic_year_id == test_scope["academic_year_id"],
            Timetable.semester_id == test_scope["semester_id"],
        ).first()
        if canon:
            assert canon.status == "RECALLED"
            # Canonical entries should be unlinked
            canon_entries = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == canon.id).all()
            assert len(canon_entries) == 0

        # Coordinator recall notification must exist
        notif = db.query(Notification).filter(
            Notification.entity_type == "TimetableVersion",
            Notification.entity_id == vid,
            Notification.title.ilike("%Recalled%"),
        ).first()
        assert notif is not None
        assert recall_reason in notif.message


def test_14_recalled_timetable_can_be_edited_revalidated_and_republished(admin_token, test_scope):
    """
    Recalled timetables can be edited, re-validated, approved, and republished.
    """
    # 1. Generate, approve, publish, and recall
    gen = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**test_scope, "force_regenerate": True},
    )
    vid = gen.json()["version_id"]

    client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    client.post(f"/timetable/versions/{vid}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    client.post(
        f"/timetable/versions/{vid}/recall",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Curriculum realignment requirement"},
    )

    # 2. Check move options and save an edit on the RECALLED version
    with Session(engine) as db:
        entry = db.query(TimetableEntry).filter(
            TimetableEntry.version_id == vid,
            TimetableEntry.status != "CANCELLED",
        ).first()
        assert entry is not None
        entry_id = entry.id
        cur_rev = entry.version.revision or 1

        other_slot = db.query(TimeSlot).filter(TimeSlot.id != entry.slot_id, TimeSlot.slot_type == "CLASS").first()
        assert other_slot is not None
        target_slot_id = other_slot.id

    # Recalled timetables allow arrangement edits!
    save_res = client.post(
        f"/timetable/versions/{vid}/arrangements",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "expected_revision": cur_rev,
            "moves": [{"entry_id": entry_id, "target_slot_id": target_slot_id}],
            "reason": "Fix clash after recall",
        },
    )
    assert save_res.status_code == 200, save_res.text
    assert save_res.json()["status"] == "REVIEWED"

    # 3. Re-validate
    val_res = client.post(f"/timetable/versions/{vid}/validate", headers={"Authorization": f"Bearer {admin_token}"})
    assert val_res.status_code == 200

    # 4. Re-approve
    app_res = client.post(f"/timetable/versions/{vid}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"

    # 5. Re-publish
    pub_res = client.post(f"/timetable/versions/{vid}/publish", headers={"Authorization": f"Bearer {admin_token}"})
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "PUBLISHED"

