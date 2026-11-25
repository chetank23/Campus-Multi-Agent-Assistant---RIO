import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.academic import AcademicYear, Semester, Department, Program
from backend.models.space_time import TimeSlot
from backend.models.timetable import Timetable, TimetableVersion, TimetableEntry, TimetableChangeHistory

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
def student_token():
    return _login("student@campus.edu")


@pytest.fixture(scope="module")
def generated_version_id(admin_token):
    with Session(engine) as db:
        ac_year = db.query(AcademicYear).first()
        semester = db.query(Semester).first()
        department = db.query(Department).first()
        program = db.query(Program).first()
        if not all([ac_year, semester, department, program]):
            pytest.skip("Missing academic seed data")

    resp = client.post(
        "/timetable/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "academic_year_id": ac_year.id,
            "semester_id": semester.id,
            "department_id": department.id,
            "program_id": program.id,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["version_id"] is not None
    return data["version_id"]


def test_a_generation_is_unpublished_draft(generated_version_id):
    with Session(engine) as db:
        ver = db.query(TimetableVersion).filter(TimetableVersion.id == generated_version_id).first()
        assert ver is not None
        assert ver.status == "GENERATED"
        assert ver.revision == 1
        assert ver.validated_revision is None
        assert ver.published_at is None
        entries = db.query(TimetableEntry).filter(TimetableEntry.version_id == generated_version_id).all()
        assert len(entries) > 0
        assert all(e.status == "DRAFT" for e in entries)
        assert all(e.timetable_id is None for e in entries)


def test_b_move_options_and_valid_arrangement_save(admin_token, generated_version_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    ver_resp = client.get(f"/timetable/versions/{generated_version_id}", headers=headers)
    assert ver_resp.status_code == 200
    entries = ver_resp.json()["timetable_entries"]
    assert len(entries) > 0

    target_entry = None
    valid_slot = None
    for entry in entries:
        opt_resp = client.get(
            f"/timetable/versions/{generated_version_id}/move-options",
            params={"entry_id": entry["id"]},
            headers=headers,
        )
        assert opt_resp.status_code == 200, opt_resp.text
        opts = opt_resp.json()
        valid_candidates = [
            s for s in opts["options"]
            if s["can_move"] is True and s["slot_id"] != entry["slot_id"]
        ]
        if valid_candidates:
            target_entry = entry
            valid_slot = valid_candidates[0]
            break

    if not target_entry or not valid_slot:
        pytest.skip("No free valid slot available in seeded schedule to test move")

    move_payload = {
        "entry_id": target_entry["id"],
        "target_slot_id": valid_slot["slot_id"],
        "target_room_id": (
            valid_slot["alternative_rooms"][0]["room_id"]
            if valid_slot["alternative_rooms"]
            else target_entry["room_id"]
        ),
    }

    val_resp = client.post(
        f"/timetable/versions/{generated_version_id}/arrangements/validate",
        headers=headers,
        json={"moves": [move_payload]},
    )
    assert val_resp.status_code == 200, val_resp.text
    assert val_resp.json()["can_save"] is True

    save_resp = client.post(
        f"/timetable/versions/{generated_version_id}/arrangements",
        headers=headers,
        json={"expected_revision": 1, "moves": [move_payload], "reason": "Test B move"},
    )
    assert save_resp.status_code == 200, save_resp.text
    saved = save_resp.json()
    assert saved["revision"] == 2
    assert saved["status"] == "REVIEWED"
    assert saved["version_detail"]["validated_revision"] is None


def test_c_section_conflict_blocked(admin_token, generated_version_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    ver_resp = client.get(f"/timetable/versions/{generated_version_id}", headers=headers)
    assert ver_resp.status_code == 200
    entries = ver_resp.json()["timetable_entries"]

    by_sec = {}
    for e in entries:
        by_sec.setdefault(e["section_id"], []).append(e)

    pair = None
    for sec_entries in by_sec.values():
        if len(sec_entries) >= 2 and sec_entries[0]["slot_id"] != sec_entries[1]["slot_id"]:
            pair = (sec_entries[0], sec_entries[1])
            break
    if not pair:
        pytest.skip("Need at least two entries in same section on different slots")

    e1, e2 = pair
    val_resp = client.post(
        f"/timetable/versions/{generated_version_id}/arrangements/validate",
        headers=headers,
        json={"moves": [{"entry_id": e1["id"], "target_slot_id": e2["slot_id"]}]},
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["can_save"] is False

    save_resp = client.post(
        f"/timetable/versions/{generated_version_id}/arrangements",
        headers=headers,
        json={
            "expected_revision": ver_resp.json()["revision"],
            "moves": [{"entry_id": e1["id"], "target_slot_id": e2["slot_id"]}],
        },
    )
    assert save_resp.status_code in (400, 409)


def test_d_break_or_lunch_slot_blocked(admin_token, generated_version_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    with Session(engine) as db:
        break_slot = db.query(TimeSlot).filter(TimeSlot.slot_type.in_(["BREAK", "LUNCH"])).first()
    if not break_slot:
        pytest.skip("No BREAK/LUNCH slot seeded")

    ver_resp = client.get(f"/timetable/versions/{generated_version_id}", headers=headers)
    entry = ver_resp.json()["timetable_entries"][0]
    val_resp = client.post(
        f"/timetable/versions/{generated_version_id}/arrangements/validate",
        headers=headers,
        json={"moves": [{"entry_id": entry["id"], "target_slot_id": break_slot.id}]},
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["can_save"] is False


def test_e_stale_revision_returns_409(admin_token, generated_version_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    ver_resp = client.get(f"/timetable/versions/{generated_version_id}", headers=headers)
    entry = ver_resp.json()["timetable_entries"][0]
    stale_rev = (ver_resp.json()["revision"] or 1) + 99

    resp = client.post(
        f"/timetable/versions/{generated_version_id}/arrangements",
        headers=headers,
        json={
            "expected_revision": stale_rev,
            "moves": [{"entry_id": entry["id"], "target_slot_id": entry["slot_id"]}],
        },
    )
    assert resp.status_code == 409


def test_f_patch_entry_enforces_validation(admin_token, generated_version_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    ver_resp = client.get(f"/timetable/versions/{generated_version_id}", headers=headers)
    entries = ver_resp.json()["timetable_entries"]
    by_sec = {}
    for e in entries:
        by_sec.setdefault(e["section_id"], []).append(e)
    pair = next((v[:2] for v in by_sec.values() if len(v) >= 2 and v[0]["slot_id"] != v[1]["slot_id"]), None)
    if not pair:
        pytest.skip("Need two entries in same section")

    resp = client.patch(
        f"/timetable/entries/{pair[0]['id']}",
        headers=headers,
        json={"slot_id": pair[1]["slot_id"]},
    )
    assert resp.status_code in (400, 409)


def test_g_validation_finalize_and_authoritative_publish(admin_token, generated_version_id):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Cannot publish before FINALIZED
    pre_pub = client.post(f"/timetable/versions/{generated_version_id}/publish", headers=headers)
    assert pre_pub.status_code in (400, 409)

    # Validate
    val_resp = client.post(f"/timetable/versions/{generated_version_id}/validate", headers=headers)
    assert val_resp.status_code == 200
    assert val_resp.json()["is_valid"] is True

    # Finalize
    fin_resp = client.post(f"/timetable/versions/{generated_version_id}/finalize", headers=headers)
    assert fin_resp.status_code == 200, fin_resp.text
    assert fin_resp.json()["status"] == "FINALIZED"

    # Editing finalized version is locked
    ver_detail = client.get(f"/timetable/versions/{generated_version_id}", headers=headers).json()
    e0 = ver_detail["timetable_entries"][0]
    lock_resp = client.patch(
        f"/timetable/entries/{e0['id']}",
        headers=headers,
        json={"slot_id": e0["slot_id"]},
    )
    assert lock_resp.status_code == 409

    # Explicit Publish
    pub_resp = client.post(f"/timetable/versions/{generated_version_id}/publish", headers=headers)
    assert pub_resp.status_code == 200, pub_resp.text
    pub_data = pub_resp.json()
    assert pub_data["status"] == "PUBLISHED"
    assert pub_data["total_entries_published"] > 0

    with Session(engine) as db:
        ver = db.query(TimetableVersion).filter(TimetableVersion.id == generated_version_id).first()
        assert ver.status == "PUBLISHED"
        active_entries = db.query(TimetableEntry).filter(
            TimetableEntry.version_id == generated_version_id,
            TimetableEntry.status == "ACTIVE",
            TimetableEntry.timetable_id.isnot(None),
        ).all()
        assert len(active_entries) > 0
        canon_ids = {e.timetable_id for e in active_entries}
        assert db.query(Timetable).filter(Timetable.id.in_(canon_ids), Timetable.status == "PUBLISHED").count() == len(canon_ids)


def test_h_revise_and_change_history(admin_token, generated_version_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    hist_resp = client.get(f"/timetable/versions/{generated_version_id}/history", headers=headers)
    assert hist_resp.status_code == 200
    assert any(h["validation_outcome"] == "PUBLISHED" for h in hist_resp.json())

    rev_resp = client.post(f"/timetable/versions/{generated_version_id}/revise", headers=headers)
    assert rev_resp.status_code == 200, rev_resp.text
    new_ver = rev_resp.json()
    assert new_ver["id"] != generated_version_id
    assert new_ver["status"] == "GENERATED"
    assert new_ver["revision"] == 1


def test_i_websocket_rbac(admin_token, student_token, generated_version_id):
    from starlette.websockets import WebSocketDisconnect

    # Unauthenticated must fail
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/timetable/versions/{generated_version_id}") as ws:
            ws.receive_text()

    # Student token must fail if available
    if student_token:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/ws/timetable/versions/{generated_version_id}?token={student_token}"
            ) as ws:
                ws.receive_text()

    # Admin token connects and receives CONNECTED
    with client.websocket_connect(
        f"/ws/timetable/versions/{generated_version_id}?token={admin_token}"
    ) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "CONNECTED"
        assert msg["version_id"] == generated_version_id
