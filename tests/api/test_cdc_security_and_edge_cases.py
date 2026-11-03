"""
tests/api/test_cdc_security_and_edge_cases.py
----------------------------------------------
Focused security, privacy, and deterministic eligibility engine verification suite:
1. Academic Record Privacy Audit & Strict RBAC:
   - Cross-student ID guessing (403).
   - Unauthorized faculty (403).
   - Department-scoped CDC coordinator restricted to matching department students (403 cross-dept, 200 within dept).
   - Global CDC coordinator and Admin full access.
   - Unauthenticated rejected (401).
2. Deterministic Eligibility Engine Edge Cases:
   - Exact CGPA boundary (CGPA == min_cgpa -> PASS).
   - Under CGPA boundary (CGPA < min_cgpa -> FAIL).
   - Grading scale normalization (e.g. 3.6 / 4.0 scale normalized against 10.0 scale).
   - Unverified academic records (CANNOT_DETERMINE).
   - Missing CGPA (CANNOT_DETERMINE).
   - Negative backlog counts (CANNOT_DETERMINE).
   - Department branch mismatch (NOT_ELIGIBLE).
   - Graduation year mismatch (NOT_ELIGIBLE).
3. Non-Discriminatory Policy & Gender Neutrality:
   - Advisory warnings against discriminatory criteria.
   - Operational evaluation evaluates purely on academic merit.
4. LLM Transcript & Secret Privacy Barrier:
   - Zero transcript / password hash leakage to LLM context.
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
from backend.schemas.placements import PlacementDriveCreateRequest, StudentAcademicRecordUpsert
from backend.services.placement_service import (
    evaluate_student_eligibility,
    validate_placement_drive,
    upsert_student_academic_record,
)
from agents.tools import execute_tool

client = TestClient(app)


@pytest.fixture
def db_session():
    with Session(engine) as db:
        yield db


@pytest.fixture(scope="module")
def admin_auth():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def faculty_unauthorized():
    """Allison Hill: Faculty member WITHOUT CDC coordinator capability."""
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def student_monica():
    """Monica Herrera: Student #1 in Department 3 (EE)."""
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"token": token, "user": me_resp.json()}


@pytest.fixture(scope="module")
def student_brent():
    """Brent Jordan: Student #49 in Department 1 (CS)."""
    resp = client.post("/auth/login", json={"email": "brent.jordan@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"token": token, "user": me_resp.json()}


# ---------------------------------------------------------------------------
# 1. Academic Record Privacy & RBAC Boundaries
# ---------------------------------------------------------------------------

def test_academic_record_privacy_and_cross_student_boundaries(
    admin_auth,
    faculty_unauthorized,
    student_monica,
    student_brent,
    db_session,
):
    admin_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    unauth_fac_headers = {"Authorization": f"Bearer {faculty_unauthorized['token']}"}
    monica_headers = {"Authorization": f"Bearer {student_monica['token']}"}
    brent_headers = {"Authorization": f"Bearer {student_brent['token']}"}

    # Clean up any capabilities for faculty_unauthorized to test unauthorized faculty access
    db_session.query(CoordinatorCapability).filter(
        CoordinatorCapability.user_id == faculty_unauthorized["user"]["id"]
    ).delete()
    db_session.commit()

    # Ensure academic records exist for student 1 and student 49
    upsert_student_academic_record(
        db=db_session,
        updater=db_session.query(User).filter(User.email == "admin@campus.edu").first(),
        payload=StudentAcademicRecordUpsert(
            student_id=1,
            cgpa=8.5,
            grading_scale=10.0,
            active_backlogs=0,
            total_backlogs=0,
            graduation_year=2025,
            is_verified=True,
        ),
    )
    upsert_student_academic_record(
        db=db_session,
        updater=db_session.query(User).filter(User.email == "admin@campus.edu").first(),
        payload=StudentAcademicRecordUpsert(
            student_id=49,
            cgpa=9.1,
            grading_scale=10.0,
            active_backlogs=0,
            total_backlogs=0,
            graduation_year=2025,
            is_verified=True,
        ),
    )

    # 1. Unauthenticated request -> 401
    resp = client.get("/placements/academic-records/1")
    assert resp.status_code == 401, f"Expected 401 unauthenticated, got {resp.status_code}"

    # 2. Unauthorized Faculty without capability -> 403
    resp = client.get("/placements/academic-records/1", headers=unauth_fac_headers)
    assert resp.status_code == 403, f"Expected 403 for unauthorized faculty, got {resp.status_code}"

    # 3. Student Monica accessing her own record (student_id = 1) -> 200
    resp = client.get("/placements/academic-records/1", headers=monica_headers)
    assert resp.status_code == 200, f"Expected 200 for own record, got {resp.status_code}"
    data = resp.json()
    assert data["student_id"] == 1
    assert data["cgpa"] == 8.5

    # 4. Cross-student ID guessing: Monica attempting to view Brent's record (student_id = 49) -> 403
    resp = client.get("/placements/academic-records/49", headers=monica_headers)
    assert resp.status_code == 403, f"Expected 403 for cross-student access, got {resp.status_code}"
    assert "Access denied" in resp.json()["detail"]

    # 5. Cross-student ID guessing: Brent attempting to view Monica's record (student_id = 1) -> 403
    resp = client.get("/placements/academic-records/1", headers=brent_headers)
    assert resp.status_code == 403, f"Expected 403 for cross-student access, got {resp.status_code}"
    assert "Access denied" in resp.json()["detail"]

    # 6. Department-Scoped Coordinator Isolation:
    # Setup Noah Rhodes as CDC Coordinator strictly scoped to Department 1 (CS)
    noah = db_session.query(User).filter(User.email == "noah.rhodes@campus.edu").first()
    db_session.query(CoordinatorCapability).filter(
        CoordinatorCapability.user_id == noah.id,
        CoordinatorCapability.capability == "CDC_COORDINATOR",
    ).delete()
    dept_cap = CoordinatorCapability(
        user_id=noah.id,
        capability="CDC_COORDINATOR",
        scope_type="DEPARTMENT",
        scope_id=1,  # CS only
        assigned_by=admin_auth["user"]["id"],
    )
    db_session.add(dept_cap)
    db_session.commit()

    # Login as Noah
    resp_noah = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    noah_token = resp_noah.json()["access_token"]
    noah_headers = {"Authorization": f"Bearer {noah_token}"}

    # Noah (Dept 1 scope) accessing Brent (Dept 1) -> 200
    resp = client.get("/placements/academic-records/49", headers=noah_headers)
    assert resp.status_code == 200, f"Expected 200 for in-scope student, got {resp.status_code}: {resp.text}"

    # Noah (Dept 1 scope) attempting to access Monica (Dept 3) -> 403 Forbidden
    resp = client.get("/placements/academic-records/1", headers=noah_headers)
    assert resp.status_code == 403, f"Expected 403 for out-of-scope student, got {resp.status_code}"
    assert "CDC Coordinator capability required" in resp.json()["detail"] or "Access denied" in resp.json()["detail"]

    # 7. Admin accessing both -> 200
    resp1 = client.get("/placements/academic-records/1", headers=admin_headers)
    assert resp1.status_code == 200
    resp49 = client.get("/placements/academic-records/49", headers=admin_headers)
    assert resp49.status_code == 200


# ---------------------------------------------------------------------------
# 2. Deterministic Eligibility Engine Edge Cases
# ---------------------------------------------------------------------------

def test_deterministic_eligibility_engine_edge_cases(db_session):
    student = db_session.query(Student).filter(Student.id == 1).first()
    assert student is not None

    base_drive = PlacementDrive(
        id=9999,
        title="Edge Case Drive",
        company_name="AlgoCorp",
        job_role="Software Engineer",
        job_type="FULL_TIME",
        status="PUBLISHED",
        eligible_department_ids=[student.department_id],
        graduation_year=2025,
        min_cgpa=8.0,
        grading_scale=10.0,
        max_active_backlogs=0,
        max_total_backlogs=1,
    )

    # Case A: Exact Boundary: CGPA == min_cgpa (8.0 == 8.0)
    acad_exact = StudentAcademicRecord(
        student_id=student.id,
        cgpa=8.0,
        grading_scale=10.0,
        active_backlogs=0,
        total_backlogs=0,
        graduation_year=2025,
        is_verified=True,
    )
    res = evaluate_student_eligibility(db=db_session, drive=base_drive, student=student, acad=acad_exact)
    assert res.status == "ELIGIBLE", f"Expected ELIGIBLE for exact CGPA boundary, got {res.status}"
    assert res.criteria_breakdown["cgpa"]["status"] == "PASS"

    # Case B: Below Boundary: CGPA < min_cgpa (7.99 < 8.0)
    acad_below = StudentAcademicRecord(
        student_id=student.id,
        cgpa=7.99,
        grading_scale=10.0,
        active_backlogs=0,
        total_backlogs=0,
        graduation_year=2025,
        is_verified=True,
    )
    res = evaluate_student_eligibility(db=db_session, drive=base_drive, student=student, acad=acad_below)
    assert res.status == "NOT_ELIGIBLE", f"Expected NOT_ELIGIBLE for CGPA 7.99, got {res.status}"
    assert any("7.99" in r for r in res.reasons)

    # Case C: Scaled Normalization (3.6 on 4.0 scale == 9.0 on 10.0 scale)
    acad_scaled = StudentAcademicRecord(
        student_id=student.id,
        cgpa=3.6,
        grading_scale=4.0,
        active_backlogs=0,
        total_backlogs=0,
        graduation_year=2025,
        is_verified=True,
    )
    res = evaluate_student_eligibility(db=db_session, drive=base_drive, student=student, acad=acad_scaled)
    assert res.status == "ELIGIBLE", f"Expected ELIGIBLE for 3.6/4.0 scale normalized, got {res.status}"
    assert res.criteria_breakdown["cgpa"]["status"] == "PASS"

    # Case D: Unverified Record (is_verified = False)
    acad_unverified = StudentAcademicRecord(
        student_id=student.id,
        cgpa=9.5,
        grading_scale=10.0,
        active_backlogs=0,
        total_backlogs=0,
        graduation_year=2025,
        is_verified=False,
    )
    res = evaluate_student_eligibility(db=db_session, drive=base_drive, student=student, acad=acad_unverified)
    assert res.status == "CANNOT_DETERMINE", f"Expected CANNOT_DETERMINE for unverified record, got {res.status}"
    assert any("pending official CDC verification" in r for r in res.reasons)
    assert res.criteria_breakdown["academic_record"]["status"] == "UNVERIFIED"

    # Case E: Missing CGPA
    acad_no_cgpa = StudentAcademicRecord(
        student_id=student.id,
        cgpa=None,
        grading_scale=10.0,
        active_backlogs=0,
        total_backlogs=0,
        graduation_year=2025,
        is_verified=True,
    )
    res = evaluate_student_eligibility(db=db_session, drive=base_drive, student=student, acad=acad_no_cgpa)
    assert res.status == "CANNOT_DETERMINE", f"Expected CANNOT_DETERMINE for missing CGPA, got {res.status}"

    # Case F: Negative active backlog count (< 0)
    acad_neg_backlog = StudentAcademicRecord(
        student_id=student.id,
        cgpa=8.5,
        grading_scale=10.0,
        active_backlogs=-1,
        total_backlogs=0,
        graduation_year=2025,
        is_verified=True,
    )
    res = evaluate_student_eligibility(db=db_session, drive=base_drive, student=student, acad=acad_neg_backlog)
    assert res.status == "CANNOT_DETERMINE", f"Expected CANNOT_DETERMINE for negative backlogs, got {res.status}"

    # Case G: Department Mismatch
    drive_diff_dept = PlacementDrive(
        id=9998,
        title="Other Dept Drive",
        company_name="AlgoCorp",
        job_role="Software Engineer",
        job_type="FULL_TIME",
        status="PUBLISHED",
        eligible_department_ids=[999],  # non-matching dept
        graduation_year=2025,
        min_cgpa=8.0,
        grading_scale=10.0,
    )
    res = evaluate_student_eligibility(db=db_session, drive=drive_diff_dept, student=student, acad=acad_exact)
    assert res.status == "NOT_ELIGIBLE"
    assert any("not in the eligible branches list" in r for r in res.reasons)

    # Case H: Graduation Year Mismatch
    drive_diff_year = PlacementDrive(
        id=9997,
        title="2026 Drive",
        company_name="AlgoCorp",
        job_role="Software Engineer",
        job_type="FULL_TIME",
        status="PUBLISHED",
        eligible_department_ids=[student.department_id],
        graduation_year=2026,
        min_cgpa=8.0,
        grading_scale=10.0,
    )
    res = evaluate_student_eligibility(db=db_session, drive=drive_diff_year, student=student, acad=acad_exact)
    assert res.status == "NOT_ELIGIBLE"
    assert any("Graduation year" in r for r in res.reasons)


# ---------------------------------------------------------------------------
# 3. Non-Discriminatory Policy & Gender Neutrality
# ---------------------------------------------------------------------------

def test_gender_neutrality_and_advisory_warning(db_session):
    now = datetime.datetime.now(datetime.timezone.utc)
    deadline = now + datetime.timedelta(days=7)

    payload = PlacementDriveCreateRequest(
        title="Software Engineer - Systems",
        company_name="Nova Systems",
        job_role="Systems Engineer",
        job_type="FULL_TIME",
        work_location="Bengaluru",
        application_deadline=deadline,
        allowed_genders="FEMALE_ONLY",  # Non-ALL value
    )

    result = validate_placement_drive(db=db_session, payload=payload)
    assert any("Institutional policy does not authorize discriminatory eligibility filtering by gender" in w for w in result.warnings), (
        f"Expected advisory warning on non-neutral gender, got warnings: {result.warnings}"
    )

    # Operational evaluation maintains MERIT_BASED_ACCESS
    student = db_session.query(Student).filter(Student.id == 1).first()
    drive = PlacementDrive(
        id=9996,
        title="Nova Systems Drive",
        company_name="Nova Systems",
        job_role="Systems Engineer",
        job_type="FULL_TIME",
        status="PUBLISHED",
        eligible_department_ids=[student.department_id],
        allowed_genders="ALL",
    )
    acad = StudentAcademicRecord(
        student_id=student.id,
        cgpa=8.8,
        grading_scale=10.0,
        is_verified=True,
    )
    res = evaluate_student_eligibility(db=db_session, drive=drive, student=student, acad=acad)
    assert res.criteria_breakdown["gender_policy"]["status"] == "MERIT_BASED_ACCESS"
    assert res.criteria_breakdown["gender_policy"]["policy"] == "NON_DISCRIMINATORY"


# ---------------------------------------------------------------------------
# 4. LLM Transcript & Sensitive Data Privacy Barrier
# ---------------------------------------------------------------------------

def test_llm_privacy_barrier_no_transcript_or_secret_leakage(student_monica, db_session):
    monica_user = db_session.query(User).filter(User.id == student_monica["user"]["id"]).first()
    assert monica_user is not None

    # Execute query tool as student Monica
    tool_res = execute_tool(
        tool_name="list_published_placement_drives",
        tool_args={"limit": 5},
        user=monica_user,
        db=db_session,
    )
    assert "drives" in tool_res
    res_str = str(tool_res)

    # Verify absence of secrets and unneeded personal identifying records
    assert "password_hash" not in res_str
    assert "hashed_password" not in res_str
    assert "SECRET_KEY" not in res_str
    assert "transcript_file" not in res_str
    assert "raw_database" not in res_str
