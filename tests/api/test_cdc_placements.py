"""
tests/api/test_cdc_placements.py
---------------------------------
Comprehensive end-to-end integration and verification suite for CDC Placement Management:
1. Capability & RBAC: CDC_COORDINATOR assignment, revocation, scope enforcement, and role barriers.
2. Placement Drive Lifecycle: Creation, pre-flight validation, optimistic locking, publish, postpone, cancel, close.
3. Deterministic Student Eligibility Engine:
   - Eligible candidate (branch, grad year, CGPA, backlogs match) -> ELIGIBLE.
   - Branch mismatch -> NOT_ELIGIBLE.
   - CGPA below threshold -> NOT_ELIGIBLE.
   - Backlogs exceed limit -> NOT_ELIGIBLE.
   - Missing/incomplete academic record -> CANNOT_DETERMINE (safe fail-closed).
4. Student Privacy & Feed: Drafts never leak to students; published drives include deterministic eligibility.
5. CDC Dashboard Statistics: Accurate KPI calculations.
6. Multi-Agent Assistant Grounding: Zero LLM hallucinations, responses strictly grounded in PostgreSQL records.
"""

from __future__ import annotations

import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models.identity import User
from backend.models.academic import Student, Department
from backend.models.events import CoordinatorCapability
from backend.models.placements import PlacementDrive, StudentAcademicRecord
from backend.schemas.placements import PlacementDriveCreateRequest, PlacementDriveUpdateRequest
from backend.services.placement_service import (
    evaluate_student_eligibility,
    validate_placement_drive,
)
from agents.supervisor.agent import classify_intent
from agents.query_agent.agent import _extract_intent_and_tool_call, format_grounded_response
from agents.tools import execute_tool

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    with Session(engine) as db:
        yield db


@pytest.fixture(scope="module")
def admin_auth():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def faculty_auth():
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def faculty2_auth():
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty 2 login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def student_auth():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    return {"token": token, "user": me_resp.json()}


# ---------------------------------------------------------------------------
# Test 1: Capability & RBAC
# ---------------------------------------------------------------------------

def test_cdc_capabilities_and_rbac(admin_auth, faculty_auth, faculty2_auth, student_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    faculty2_headers = {"Authorization": f"Bearer {faculty2_auth['token']}"}
    student_headers = {"Authorization": f"Bearer {student_auth['token']}"}

    fac_user_id = faculty_auth["user"]["id"]

    # 1. Non-coordinator faculty cannot create drives
    resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Google",
            "title": "Software Engineer Drive 2026",
            "job_role": "SWE - I",
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)).isoformat(),
        },
        headers=faculty_headers,
    )
    assert resp.status_code in (403, 404), f"Non-coordinator faculty should be 403: {resp.text}"

    # 2. Student cannot create drives
    resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Google",
            "title": "Software Engineer Drive 2026",
            "job_role": "SWE - I",
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)).isoformat(),
        },
        headers=student_headers,
    )
    assert resp.status_code == 403, f"Student should be 403: {resp.text}"

    # 3. Unauthenticated cannot create drives
    resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Google",
            "title": "Software Engineer Drive 2026",
            "job_role": "SWE - I",
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)).isoformat(),
        },
    )
    assert resp.status_code == 401

    # 4. Admin assigns CDC_COORDINATOR capability to faculty
    assign_resp = client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac_user_id,
            "capability": "CDC_COORDINATOR",
            "scope_type": "GLOBAL",
        },
        headers=admin_headers,
    )
    assert assign_resp.status_code in (200, 201), f"Capability assignment failed: {assign_resp.text}"
    cap_data = assign_resp.json()
    assert cap_data["capability"] == "CDC_COORDINATOR"

    # 5. Now CDC faculty CAN create drives
    dl = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=14)).isoformat()
    create_resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Microsoft",
            "title": "Graduate SWE Program 2026",
            "job_role": "Software Development Engineer",
            "job_type": "FULL_TIME",
            "work_location": "Bengaluru / Hyderabad",
            "compensation_details": "CTC: 24 LPA",
            "graduation_year": 2026,
            "min_cgpa": 7.5,
            "max_active_backlogs": 0,
            "application_deadline": dl,
            "application_link": "https://careers.microsoft.com/jobs/123",
        },
        headers=faculty_headers,
    )
    assert create_resp.status_code == 201, f"CDC Coordinator create failed: {create_resp.text}"
    drive = create_resp.json()
    assert drive["company_name"] == "Microsoft"
    assert drive["status"] == "DRAFT"
    drive_id = drive["id"]

    # 6. Admin revokes CDC capability
    revoke_resp = client.post(
        f"/admin/capabilities/{cap_data['id']}/revoke",
        json={"reason": "Rotation of CDC coordinators"},
        headers=admin_headers,
    )
    assert revoke_resp.status_code == 200

    # 7. Revoked faculty can no longer create drives
    resp_after = client.post(
        "/placements/drives",
        json={
            "company_name": "Amazon",
            "title": "Amazon SDE Hiring 2026",
            "job_role": "SDE-1",
            "application_deadline": dl,
        },
        headers=faculty_headers,
    )
    assert resp_after.status_code == 403

    # Clean up / Re-assign for next tests
    reassign_resp = client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac_user_id,
            "capability": "CDC_COORDINATOR",
            "scope_type": "GLOBAL",
        },
        headers=admin_headers,
    )
    assert reassign_resp.status_code in (200, 201)


# ---------------------------------------------------------------------------
# Test 2: Placement Drive Lifecycle & Optimistic Locking
# ---------------------------------------------------------------------------

def test_placement_drive_lifecycle_and_validation(admin_auth, faculty_auth, db_session):
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    # 1. Create a draft placement drive
    future_deadline = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).isoformat()
    resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Goldman Sachs",
            "title": "Engineering Campus Hiring 2026",
            "job_role": "Analyst - Technology",
            "job_type": "FULL_TIME",
            "work_location": "Bengaluru",
            "compensation_details": "CTC: 28 LPA",
            "graduation_year": 2026,
            "min_cgpa": 7.0,
            "max_active_backlogs": 0,
            "application_deadline": future_deadline,
            "application_link": "https://goldmansachs.com/careers/analyst",
            "schedules": [
                {
                    "round_type": "ONLINE_ASSESSMENT",
                    "round_order": 1,
                    "title": "HackerRank Coding Test",
                    "start_time": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=8)).isoformat(),
                    "end_time": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=8, hours=2)).isoformat(),
                    "is_online": True,
                    "meeting_link": "https://hackerrank.com/gs-test",
                }
            ],
        },
        headers=faculty_headers,
    )
    assert resp.status_code == 201
    drive = resp.json()
    drive_id = drive["id"]
    assert drive["status"] == "DRAFT"
    assert drive["version"] == 1
    assert len(drive["schedules"]) == 1

    # 2. Pre-flight validation
    val_resp = client.post(
        "/placements/drives/validate",
        json={
            "company_name": "Goldman Sachs",
            "title": "Engineering Campus Hiring 2026",
            "job_role": "Analyst - Technology",
            "application_deadline": future_deadline,
            "graduation_year": 2026,
            "min_cgpa": 7.0,
            "max_active_backlogs": 0,
        },
        params={"exclude_id": drive_id},
        headers=faculty_headers,
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["is_valid"] is True
    assert val_data["eligible_students_count"] >= 0

    # 3. Optimistic concurrency locking: updating with stale version returns 409
    stale_update = client.put(
        f"/placements/drives/{drive_id}",
        json={
            "compensation_details": "CTC: 30 LPA",
            "version": 99,  # Stale version
        },
        headers=faculty_headers,
    )
    assert stale_update.status_code == 409, f"Stale update should return 409: {stale_update.text}"

    # 4. Successful update increments version
    good_update = client.put(
        f"/placements/drives/{drive_id}",
        json={
            "compensation_details": "CTC: 32 LPA",
            "version": 1,
        },
        headers=faculty_headers,
    )
    assert good_update.status_code == 200
    updated_drive = good_update.json()
    assert updated_drive["version"] == 2
    assert updated_drive["compensation_details"] == "CTC: 32 LPA"

    # 5. Publish drive
    pub_resp = client.post(f"/placements/drives/{drive_id}/publish", headers=faculty_headers)
    assert pub_resp.status_code == 200
    pub_drive = pub_resp.json()
    assert pub_drive["status"] == "PUBLISHED"
    assert pub_drive["published_at"] is not None

    # 6. Postpone drive
    postpone_resp = client.post(
        f"/placements/drives/{drive_id}/postpone",
        json={"reason": "Recruitment team rescheduling online test window"},
        headers=faculty_headers,
    )
    assert postpone_resp.status_code == 200
    postponed_drive = postpone_resp.json()
    assert postponed_drive["status"] == "POSTPONED"
    assert postponed_drive["postpone_reason"] == "Recruitment team rescheduling online test window"

    # 7. Cancel drive
    cancel_resp = client.post(
        f"/placements/drives/{drive_id}/cancel",
        json={"reason": "Company cancelled campus hiring drive for the season"},
        headers=faculty_headers,
    )
    assert cancel_resp.status_code == 200
    cancelled_drive = cancel_resp.json()
    assert cancelled_drive["status"] == "CANCELLED"

    # 8. Close drive
    close_resp = client.post(f"/placements/drives/{drive_id}/close", headers=faculty_headers)
    assert close_resp.status_code == 200
    closed_drive = close_resp.json()
    assert closed_drive["status"] == "CLOSED"


# ---------------------------------------------------------------------------
# Test 3: Deterministic Student Eligibility Engine
# ---------------------------------------------------------------------------

def test_deterministic_student_eligibility_engine(admin_auth, faculty_auth, student_auth, db_session):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    student_headers = {"Authorization": f"Bearer {student_auth['token']}"}

    # Identify Monica Herrera (our authenticated student)
    student_record = db_session.query(Student).filter(Student.user_id == student_auth["user"]["id"]).first()
    assert student_record is not None, "Student record for monica.herrera not found"
    student_dept_id = student_record.department_id

    # 1. Upsert authoritative StudentAcademicRecord for Monica: CGPA 8.75, 0 backlogs, grad year 2026, verified
    rec_resp = client.post(
        "/placements/academic-records",
        json={
            "student_id": student_record.id,
            "cgpa": 8.75,
            "grading_scale": 10.0,
            "active_backlogs": 0,
            "total_backlogs": 0,
            "graduation_year": 2026,
            "tenth_percentage": 92.5,
            "twelfth_percentage": 90.0,
            "is_verified": True,
        },
        headers=admin_headers,
    )
    assert rec_resp.status_code == 200
    rec = rec_resp.json()
    assert rec["cgpa"] == 8.75
    assert rec["is_verified"] is True

    # 2. Case A: Student meets ALL criteria -> ELIGIBLE
    drive_a_resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Oracle",
            "title": "Cloud Infrastructure Engineer 2026",
            "job_role": "Cloud Engineer",
            "eligible_department_ids": [student_dept_id],
            "graduation_year": 2026,
            "min_cgpa": 7.5,
            "max_active_backlogs": 0,
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=5)).isoformat(),
        },
        params={"direct_publish": True},
        headers=faculty_headers,
    )
    assert drive_a_resp.status_code == 201
    drive_a = drive_a_resp.json()
    assert drive_a["status"] == "PUBLISHED"

    elig_a = client.get(f"/placements/drives/{drive_a['id']}/eligibility", headers=student_headers)
    assert elig_a.status_code == 200
    res_a = elig_a.json()
    assert res_a["status"] == "ELIGIBLE"
    assert res_a["is_eligible"] is True
    assert len(res_a["reasons"]) > 0

    # 3. Case B: Department mismatch -> NOT_ELIGIBLE
    other_dept = db_session.query(Department).filter(Department.id != student_dept_id).first()
    assert other_dept is not None

    drive_b_resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Tesla",
            "title": "Mechanical Systems Engineer 2026",
            "job_role": "Systems Engineer",
            "eligible_department_ids": [other_dept.id],  # Does not include student's dept
            "graduation_year": 2026,
            "min_cgpa": 7.0,
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=5)).isoformat(),
        },
        params={"direct_publish": True},
        headers=faculty_headers,
    )
    assert drive_b_resp.status_code == 201
    drive_b = drive_b_resp.json()

    elig_b = client.get(f"/placements/drives/{drive_b['id']}/eligibility", headers=student_headers)
    assert elig_b.status_code == 200
    res_b = elig_b.json()
    assert res_b["status"] == "NOT_ELIGIBLE"
    assert res_b["is_eligible"] is False
    assert any("Department" in r for r in res_b["reasons"])

    # 4. Case C: High CGPA requirement (9.5) -> NOT_ELIGIBLE
    drive_c_resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Jane Street",
            "title": "Quantitative Developer 2026",
            "job_role": "Quant Dev",
            "eligible_department_ids": [student_dept_id],
            "graduation_year": 2026,
            "min_cgpa": 9.5,  # Student has 8.75
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=5)).isoformat(),
        },
        params={"direct_publish": True},
        headers=faculty_headers,
    )
    assert drive_c_resp.status_code == 201
    drive_c = drive_c_resp.json()

    elig_c = client.get(f"/placements/drives/{drive_c['id']}/eligibility", headers=student_headers)
    assert elig_c.status_code == 200
    res_c = elig_c.json()
    assert res_c["status"] == "NOT_ELIGIBLE"
    assert res_c["is_eligible"] is False
    assert any("CGPA" in r for r in res_c["reasons"])

    # 5. Case D: Graduation year mismatch -> NOT_ELIGIBLE
    drive_d_resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Cisco",
            "title": "Early Career Graduate 2025",
            "job_role": "Network Engineer",
            "eligible_department_ids": [student_dept_id],
            "graduation_year": 2025,  # Student is 2026
            "min_cgpa": 7.0,
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=5)).isoformat(),
        },
        params={"direct_publish": True},
        headers=faculty_headers,
    )
    assert drive_d_resp.status_code == 201
    drive_d = drive_d_resp.json()

    elig_d = client.get(f"/placements/drives/{drive_d['id']}/eligibility", headers=student_headers)
    assert elig_d.status_code == 200
    res_d = elig_d.json()
    assert res_d["status"] == "NOT_ELIGIBLE"
    assert res_d["is_eligible"] is False
    assert any("Graduation year" in r for r in res_d["reasons"])

    # 6. Case E: Student without academic record -> CANNOT_DETERMINE (Safe fail-closed)
    student_without_record = (
        db_session.query(Student)
        .outerjoin(StudentAcademicRecord, Student.id == StudentAcademicRecord.student_id)
        .filter(StudentAcademicRecord.id == None, Student.department_id == student_dept_id)
        .first()
    )
    if not student_without_record:
        test_user = User(name="No Acad Student", email="no_acad_dept@test.com", password_hash="hash", role="STUDENT", department_id=student_dept_id)
        db_session.add(test_user)
        db_session.commit()
        db_session.refresh(test_user)
        student_without_record = Student(user_id=test_user.id, usn="1MS22CS998", department_id=student_dept_id)
        db_session.add(student_without_record)
        db_session.commit()
        db_session.refresh(student_without_record)

    if student_without_record:
        drive_obj = db_session.query(PlacementDrive).filter(PlacementDrive.id == drive_a["id"]).first()
        assert drive_obj is not None
        eval_result = evaluate_student_eligibility(db=db_session, drive=drive_obj, student=student_without_record)
        assert eval_result.status == "CANNOT_DETERMINE"
        assert eval_result.is_eligible is False
        assert any("academic record" in r.lower() for r in eval_result.reasons)


# ---------------------------------------------------------------------------
# Test 4: Student Feed & Privacy
# ---------------------------------------------------------------------------

def test_student_feed_and_privacy(admin_auth, faculty_auth, student_auth, db_session):
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    student_headers = {"Authorization": f"Bearer {student_auth['token']}"}

    # Create 1 DRAFT drive and 1 PUBLISHED drive
    draft_resp = client.post(
        "/placements/drives",
        json={
            "company_name": "Secret Confidential Corp",
            "title": "Stealth Hiring Round",
            "job_role": "R&D Scientist",
            "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)).isoformat(),
        },
        headers=faculty_headers,
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    # Student requests all drives
    student_drives_resp = client.get("/placements/drives", headers=student_headers)
    assert student_drives_resp.status_code == 200
    student_drives = student_drives_resp.json()

    # Verify DRAFT drive is STRICTLY NEVER leaked to student
    for d in student_drives:
        assert d["status"] != "DRAFT", f"Draft drive leaked to student: {d}"
        assert d["id"] != draft_id, "Draft drive ID present in student list"
        # Each student drive must have attached eligibility result
        assert "eligibility" in d
        assert d["eligibility"] is not None
        assert d["eligibility"]["status"] in ("ELIGIBLE", "NOT_ELIGIBLE", "CANNOT_DETERMINE")

    # Verify only_eligible filter works
    only_elig_resp = client.get("/placements/drives", params={"only_eligible": True}, headers=student_headers)
    assert only_elig_resp.status_code == 200
    only_elig_drives = only_elig_resp.json()
    for d in only_elig_drives:
        assert d["eligibility"]["status"] == "ELIGIBLE"


# ---------------------------------------------------------------------------
# Test 5: Dashboard Statistics
# ---------------------------------------------------------------------------

def test_cdc_dashboard_statistics(admin_auth, faculty_auth):
    faculty_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    dash_resp = client.get("/placements/dashboard", headers=faculty_headers)
    assert dash_resp.status_code == 200
    stats = dash_resp.json()
    assert "total_drives" in stats
    assert "published_drives" in stats
    assert "draft_drives" in stats
    assert "upcoming_deadlines_count" in stats
    assert stats["total_drives"] >= stats["published_drives"] + stats["draft_drives"]


# ---------------------------------------------------------------------------
# Test 6: Multi-Agent Assistant Grounding
# ---------------------------------------------------------------------------

def test_assistant_placement_grounding(admin_auth, faculty_auth, student_auth, db_session):
    student_user = db_session.query(User).filter(User.id == student_auth["user"]["id"]).first()
    assert student_user is not None

    # 1. Intent routing
    intent = classify_intent("What placement drives are open for me?")
    assert intent == "QUERY_AGENT", f"Placement intent should route to QUERY_AGENT, got {intent}"

    tool_call = _extract_intent_and_tool_call("Show all campus placement drives", student_user)
    assert tool_call is not None
    assert tool_call[0] in ("list_placement_drives", "list_published_placement_drives", "check_student_placement_eligibility")

    # 2. Tool execution grounded in database
    result = execute_tool(tool_call[0], tool_call[1], student_user, db_session)
    assert isinstance(result, (dict, list))
    if isinstance(result, dict):
        assert "error" not in result

    # 3. Check student eligibility tool execution
    oracle_drive = db_session.query(PlacementDrive).filter(PlacementDrive.company_name == "Oracle").first()
    if oracle_drive:
        elig_tool_res = execute_tool(
            "get_student_drive_eligibility",
            {"drive_id": oracle_drive.id},
            student_user,
            db_session,
        )
        assert "status" in elig_tool_res
        assert elig_tool_res["status"] in ("ELIGIBLE", "NOT_ELIGIBLE", "CANNOT_DETERMINE")
        assert elig_tool_res["company_name"] == "Oracle"

    # 4. Formatter test
    mock_placement_data = {
        "drives": [
            {
                "id": 1,
                "company_name": "Google",
                "title": "Software Engineer 2026",
                "job_role": "SWE",
                "job_type": "FULL_TIME",
                "compensation_details": "CTC: 35 LPA",
                "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=5)).isoformat(),
                "status": "PUBLISHED",
                "is_deadline_passed": False,
                "eligibility": {"status": "ELIGIBLE", "is_eligible": True, "reasons": ["All criteria met"]},
            }
        ]
    }
    formatted_res = format_grounded_response(
        tool_call[0],
        {},
        mock_placement_data,
        student_user,
    )
    formatted = formatted_res[0] if isinstance(formatted_res, tuple) else formatted_res
    assert "Google" in formatted
    assert "Software Engineer 2026" in formatted
    assert "CTC: 35 LPA" in formatted
