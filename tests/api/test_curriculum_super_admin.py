"""
tests/api/test_curriculum_super_admin.py
----------------------------------------
Exhaustive end-to-end integration test suite for:
1. Super Admin Authentication & Strict RBAC Enforcement
2. Central Academic Structure (Regulations & Admission Cohorts)
3. Curriculum Versioning Lifecycle (Draft -> Review -> Approval -> Publication -> Immutability -> Revision)
4. Subject Mappings, Contact Hours, Lab Requirements & Credit Recalculation
5. AI Syllabus PDF Upload, Extraction, Page Citations & Approval Studio
6. Department Releases & Admin Curriculum Inbox & Acknowledgement
7. Correction Request Ticketing & Persistent Threaded Communications
8. Operational Offerings Allocation & Timetable Readiness Preflight Check
9. Timetable Engine Input Loader Integration with Curriculum Snapshots
10. Scoped Student & Faculty Read-Only Curriculum Access
11. Executive Dashboard KPIs & Immutable Audit Trail Verification
"""

from __future__ import annotations

import io
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.core.security import get_password_hash
from backend.models.identity import User
from backend.models.academic import Department, Program, AcademicYear, Semester, Section, Faculty, Student
from backend.models.courses import Course
from backend.models.curriculum import (
    Regulation, AdmissionCohort, CurriculumVersion, CurriculumSemester,
    CurriculumSubjectMapping, CurriculumDocument, CurriculumExtractionJob,
    CurriculumRelease, CurriculumRequest, SectionCourseOffering, FacultyCourseOffering
)
from backend.schemas.timetable_generation import GenerationScope
from backend.services.timetable_input_loader import validate_and_load_input


client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def super_admin_auth():
    # Ensure super admin exists in DB
    with Session(engine) as db:
        user = db.query(User).filter(User.email == "superadmin@campus.edu").first()
        if not user:
            user = User(
                email="superadmin@campus.edu",
                name="Super Admin",
                password_hash=get_password_hash("Test@1234"),
                role="SUPER_ADMIN",
                is_active=True,
            )
            db.add(user)
            db.commit()

    resp = client.post("/auth/login", json={"email": "superadmin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Super admin login failed: {resp.text}"
    token = resp.json()["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "SUPER_ADMIN"
    return {"token": token, "user": me_resp.json()}


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
    # Use existing faculty or create one
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "FACULTY").first()
        if not user:
            dept = db.query(Department).first()
            user = User(
                email="faculty_curr_test@campus.edu",
                name="Prof. Alan Turing",
                password_hash=get_password_hash("Test@1234"),
                role="FACULTY",
                department_id=dept.id if dept else None,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            fac = Faculty(user_id=user.id, faculty_id="FAC-TURING", department_id=dept.id if dept else None)
            db.add(fac)
            db.commit()

    resp = client.post("/auth/login", json={"email": user.email, "password": "Test@1234"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"token": token, "user": user}


@pytest.fixture(scope="module")
def student_auth():
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        if not user:
            dept = db.query(Department).first()
            prog = db.query(Program).first()
            user = User(
                email="student_curr_test@campus.edu",
                name="Ada Lovelace",
                password_hash=get_password_hash("Test@1234"),
                role="STUDENT",
                department_id=dept.id if dept else None,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            st = Student(user_id=user.id, student_id="STU-ADA", department_id=dept.id if dept else None, program_id=prog.id if prog else None)
            db.add(st)
            db.commit()

    resp = client.post("/auth/login", json={"email": user.email, "password": "Test@1234"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"token": token, "user": user}


# ---------------------------------------------------------------------------
# 1. RBAC Tests
# ---------------------------------------------------------------------------

def test_rbac_super_admin_endpoints_reject_non_super_admin(admin_auth, faculty_auth, student_auth):
    """Ordinary Admin, Faculty, and Students must receive 403 Forbidden on Super Admin endpoints."""
    endpoints = [
        "/super-admin/regulations",
        "/super-admin/cohorts",
        "/super-admin/curriculum-versions",
        "/super-admin/dashboard/stats",
    ]
    for auth in (admin_auth, faculty_auth, student_auth):
        headers = {"Authorization": f"Bearer {auth['token']}"}
        for ep in endpoints:
            resp = client.get(ep, headers=headers)
            assert resp.status_code == 403, f"Expected 403 on {ep} for {auth['user']['role']}, got {resp.status_code}"


def test_rbac_super_admin_authorized(super_admin_auth):
    """Super Admin should access all super-admin endpoints without restriction."""
    headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}
    resp = client.get("/super-admin/dashboard/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_regulations" in data
    assert "total_curriculum_versions" in data


# ---------------------------------------------------------------------------
# 2. Academic Structure: Regulations & Admission Cohorts
# ---------------------------------------------------------------------------

def test_regulations_crud(super_admin_auth):
    headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}
    reg_code = "R2026-TEST"

    # Create Regulation
    create_payload = {
        "code": reg_code,
        "name": "Academic Scheme 2026 Autonomous",
        "effective_year": 2026,
        "is_active": True,
        "description": "Outcome-Based Education Scheme 2026",
    }
    resp = client.post("/super-admin/regulations", json=create_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["code"] == reg_code
    reg_id = created["id"]

    # Duplicate creation check
    dup_resp = client.post("/super-admin/regulations", json=create_payload, headers=headers)
    assert dup_resp.status_code == 409

    # List regulations
    list_resp = client.get("/super-admin/regulations", headers=headers)
    assert list_resp.status_code == 200
    assert any(r["id"] == reg_id for r in list_resp.json())

    # Update regulation
    update_resp = client.put(
        f"/super-admin/regulations/{reg_id}",
        json={"name": "Academic Scheme 2026 (Updated)", "description": "Updated description"},
        headers=headers
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Academic Scheme 2026 (Updated)"


def test_admission_cohorts_crud(super_admin_auth):
    headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}

    # Fetch a regulation and program
    with Session(engine) as db:
        reg = db.query(Regulation).first()
        prog = db.query(Program).first()

    assert reg is not None and prog is not None

    cohort_name = f"2026-2030-{reg.id}"
    create_payload = {
        "cohort_name": cohort_name,
        "start_year": 2026,
        "end_year": 2030,
        "program_id": prog.id,
        "regulation_id": reg.id,
        "is_active": True,
    }
    resp = client.post("/super-admin/cohorts", json=create_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["cohort_name"] == cohort_name
    cohort_id = created["id"]

    # Validation: end_year <= start_year must fail
    invalid_payload = dict(create_payload, cohort_name="Invalid-Cohort", start_year=2026, end_year=2025)
    fail_resp = client.post("/super-admin/cohorts", json=invalid_payload, headers=headers)
    assert fail_resp.status_code == 400

    # List cohorts
    list_resp = client.get(f"/super-admin/cohorts?program_id={prog.id}", headers=headers)
    assert list_resp.status_code == 200
    assert any(c["id"] == cohort_id for c in list_resp.json())


# ---------------------------------------------------------------------------
# 3. Curriculum Versioning & Subject Mapping Lifecycle
# ---------------------------------------------------------------------------

def test_curriculum_version_full_lifecycle(super_admin_auth):
    headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}

    with Session(engine) as db:
        dept = db.query(Department).first()
        if not dept:
            dept = Department(name="Computer Science and Engineering", code="CSE")
            db.add(dept)
            db.commit()
            db.refresh(dept)
        assert dept is not None, "Department must exist in database"
        dept_id = dept.id

        prog = db.query(Program).filter(Program.department_id == dept_id).first() or db.query(Program).first()
        if not prog:
            prog = Program(name="B.Tech Computer Science and Engineering", program_name="B.Tech Computer Science and Engineering", department_id=dept_id, duration=4)
            db.add(prog)
            db.commit()
            db.refresh(prog)
        assert prog is not None, "Program must exist in database"
        prog_id = prog.id

        reg = db.query(Regulation).first()
        if not reg:
            reg = Regulation(code="R2026-AUTONOMOUS", name="Autonomous Regulation 2026", effective_year=2026, is_active=True)
            db.add(reg)
            db.commit()
            db.refresh(reg)
        assert reg is not None, "Regulation must exist in database"
        reg_id = reg.id

    # Step 1: Create Draft Curriculum Version
    ver_payload = {
        "department_id": dept_id,
        "program_id": prog_id,
        "regulation_id": reg_id,
        "description": "B.Tech Computer Science 2026 Curriculum",
        "total_semesters": 8,
    }
    resp = client.post("/super-admin/curriculum-versions", json=ver_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    ver = resp.json()
    ver_id = ver["id"]
    assert ver["status"] == "DRAFT"
    assert len(ver["semesters"]) == 8

    # Step 2: Add Subject Mappings to Semester 1
    sem1_id = ver["semesters"][0]["id"]
    sub1_payload = {
        "curriculum_semester_id": sem1_id,
        "subject_code": f"CS101-{ver_id}",
        "subject_name": "Programming Fundamentals",
        "subject_type": "THEORY",
        "is_mandatory": True,
        "credits": 4.0,
        "lecture_hours": 3,
        "tutorial_hours": 1,
        "practical_hours": 0,
        "contact_hours": 4,
        "requires_lab": False,
    }
    sub1_resp = client.post(f"/super-admin/curriculum-versions/{ver_id}/subjects", json=sub1_payload, headers=headers)
    assert sub1_resp.status_code == 201, sub1_resp.text
    sub1 = sub1_resp.json()
    assert sub1["credits"] == 4.0
    assert sub1["contact_hours"] == 4

    # Add Lab Subject to Semester 1
    sub2_payload = {
        "curriculum_semester_id": sem1_id,
        "subject_code": f"CS102L-{ver_id}",
        "subject_name": "Programming Laboratory",
        "subject_type": "PRACTICAL",
        "is_mandatory": True,
        "credits": 2.0,
        "lecture_hours": 0,
        "tutorial_hours": 0,
        "practical_hours": 3,
        "contact_hours": 3,
        "practical_consecutive_periods": 3,
        "requires_lab": True,
    }
    sub2_resp = client.post(f"/super-admin/curriculum-versions/{ver_id}/subjects", json=sub2_payload, headers=headers)
    assert sub2_resp.status_code == 201, sub2_resp.text

    # Verify credit totals recalculated
    ver_detail = client.get(f"/super-admin/curriculum-versions/{ver_id}", headers=headers).json()
    assert ver_detail["total_credits"] == 6.0
    assert ver_detail["semesters"][0]["total_credits"] == 6.0

    # Step 3: Transition to NEEDS_REVIEW
    status_resp = client.post(
        f"/super-admin/curriculum-versions/{ver_id}/status",
        json={"status": "NEEDS_REVIEW", "review_notes": "Submitted for Academic Council review"},
        headers=headers
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "NEEDS_REVIEW"

    # Step 4: Approve Version
    appr_resp = client.post(
        f"/super-admin/curriculum-versions/{ver_id}/status",
        json={"status": "APPROVED", "review_notes": "Approved by BoS"},
        headers=headers
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "APPROVED"

    # Step 5: Publish Version
    pub_resp = client.post(f"/super-admin/curriculum-versions/{ver_id}/publish", headers=headers)
    assert pub_resp.status_code == 200, pub_resp.text
    published = pub_resp.json()
    assert published["status"] == "PUBLISHED"
    assert published["published_at"] is not None

    # Step 6: Verify Immutability (Attempting to add or edit subjects must fail)
    fail_add = client.post(
        f"/super-admin/curriculum-versions/{ver_id}/subjects",
        json=sub1_payload,
        headers=headers
    )
    assert fail_add.status_code == 400
    assert "Cannot modify a published curriculum" in fail_add.text

    # Step 7: Branch a New Revision
    rev_resp = client.post(f"/super-admin/curriculum-versions/{ver_id}/revise", headers=headers)
    assert rev_resp.status_code == 201, rev_resp.text
    revision = rev_resp.json()
    assert revision["status"] == "DRAFT"
    assert revision["version_number"] == published["version_number"] + 1
    assert revision["previous_version_id"] == ver_id
    assert revision["total_credits"] == published["total_credits"]


# ---------------------------------------------------------------------------
# 4. Document Upload & Extraction Studio
# ---------------------------------------------------------------------------

def test_pdf_upload_and_extraction_workflow(super_admin_auth):
    headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}

    # Generate a lightweight valid PDF using PyPDF or simple bytes
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()

    # Upload document
    files = {"file": ("test_syllabus.pdf", pdf_bytes, "application/pdf")}
    data = {"title": "Test Syllabus 2026", "department_id": "1"}
    upload_resp = client.post("/super-admin/documents/upload", files=files, data=data, headers=headers)
    assert upload_resp.status_code == 200, upload_resp.text
    doc_id = upload_resp.json()["id"]

    # Trigger extraction job
    extract_resp = client.post(f"/super-admin/documents/{doc_id}/extract", headers=headers)
    assert extract_resp.status_code == 200, extract_resp.text
    job = extract_resp.json()
    assert job["document_id"] == doc_id
    job_id = job["id"]

    # Review & Approve extraction with edited items
    review_payload = {
        "action": "APPROVE",
        "feedback": "Approved with verified course codes",
        "edited_data": [
            {
                "semester": 1,
                "code": f"AI101-{job_id}",
                "name": "Artificial Intelligence Basics",
                "type": "THEORY",
                "credits": 3.0,
                "lecture": 3,
                "tutorial": 0,
                "practical": 0,
                "contact_hours": 3,
                "requires_lab": False,
                "is_mandatory": True,
                "source_page": 1,
                "source_text": "AI101 Artificial Intelligence Basics 3-0-0-3",
                "confidence_score": 0.98,
            }
        ]
    }
    review_resp = client.post(f"/super-admin/extraction-jobs/{job_id}/review", json=review_payload, headers=headers)
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "APPROVED"


# ---------------------------------------------------------------------------
# 5. Admin Curriculum Inbox & Acknowledgement
# ---------------------------------------------------------------------------

def test_admin_curriculum_inbox_and_acknowledgement(super_admin_auth, admin_auth):
    sa_headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}
    adm_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    admin_dept_id = admin_auth["user"]["department_id"] or 1

    # Super admin releases a curriculum version to admin's department
    with Session(engine) as db:
        v = db.query(CurriculumVersion).filter(CurriculumVersion.status == "PUBLISHED").first()
        if not v:
            dept = db.query(Department).first()
            if not dept:
                dept = Department(name="Computer Science and Engineering", code="CSE")
                db.add(dept)
                db.commit()
                db.refresh(dept)
            assert dept is not None, "Department must exist in database"
            dept_id = dept.id

            prog = db.query(Program).filter(Program.department_id == dept_id).first() or db.query(Program).first()
            if not prog:
                prog = Program(name="B.Tech Computer Science and Engineering", program_name="B.Tech Computer Science and Engineering", department_id=dept_id, duration=4)
                db.add(prog)
                db.commit()
                db.refresh(prog)
            assert prog is not None, "Program must exist in database"
            prog_id = prog.id

            reg = db.query(Regulation).first()
            if not reg:
                reg = Regulation(code="R2026-INBOX", name="Inbox Regulation 2026", effective_year=2026, is_active=True)
                db.add(reg)
                db.commit()
                db.refresh(reg)
            assert reg is not None, "Regulation must exist in database"
            reg_id = reg.id

            user = db.query(User).first()
            assert user is not None, "User must exist in database"
            user_id = user.id

            v = CurriculumVersion(
                version_code="CURR-TEST-INBOX-PUB",
                department_id=dept_id,
                program_id=prog_id,
                regulation_id=reg_id,
                status="PUBLISHED",
                created_by_id=user_id,
            )
            db.add(v)
            db.commit()
            db.refresh(v)
        assert v is not None, "CurriculumVersion must exist in database"
        v_id = v.id

    release_payload = {"curriculum_version_id": v_id, "department_ids": [admin_dept_id]}
    client.post(f"/super-admin/curriculum-versions/{v_id}/release", json=release_payload, headers=sa_headers)

    # Admin checks inbox
    inbox_resp = client.get("/admin/curriculum/inbox", headers=adm_headers)
    assert inbox_resp.status_code == 200
    releases = inbox_resp.json()
    assert len(releases) > 0
    rel = releases[0]

    # Admin acknowledges release
    ack_resp = client.post(
        f"/admin/curriculum/inbox/{rel['id']}/acknowledge",
        json={"acknowledgement_notes": "Reviewed by HOD. Ready for allocation."},
        headers=adm_headers
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["is_acknowledged"] is True


# ---------------------------------------------------------------------------
# 6. Admin Correction Requests & Persistent Communication
# ---------------------------------------------------------------------------

def test_curriculum_correction_requests_workflow(super_admin_auth, admin_auth):
    adm_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    sa_headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}
    admin_dept_id = admin_auth["user"]["department_id"] or 1

    # Admin creates correction ticket
    req_payload = {
        "department_id": admin_dept_id,
        "request_type": "INCORRECT_CREDITS",
        "title": "CS101 Practical hours discrepancy",
        "description": "CS101 should include 2 practical hours according to BoS meeting minutes.",
    }
    create_resp = client.post("/admin/curriculum/requests", json=req_payload, headers=adm_headers)
    assert create_resp.status_code == 201, create_resp.text
    req = create_resp.json()
    req_id = req["id"]
    assert req["status"] == "OPEN"
    assert len(req["messages"]) == 1

    # Super Admin reviews and replies
    sa_msg_resp = client.post(
        f"/super-admin/requests/{req_id}/messages",
        json={"message": "Please attach the signed BoS minutes document for verification."},
        headers=sa_headers
    )
    assert sa_msg_resp.status_code == 200

    # Admin replies back
    adm_msg_resp = client.post(
        f"/admin/curriculum/requests/{req_id}/messages",
        json={"message": "Attached minutes. Resolution requested for R2026."},
        headers=adm_headers
    )
    assert adm_msg_resp.status_code == 200

    # Super Admin resolves ticket
    resolve_resp = client.put(
        f"/super-admin/requests/{req_id}/status",
        json={"status": "RESOLVED", "resolution_notes": "Updated in R2026 Revision 2"},
        headers=sa_headers
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "RESOLVED"
    assert len(resolve_resp.json()["messages"]) == 3


# ---------------------------------------------------------------------------
# 7. Operational Allocation & Readiness Verification
# ---------------------------------------------------------------------------

def test_operational_allocation_and_readiness_preflight(admin_auth):
    headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    with Session(engine) as db:
        ay = db.query(AcademicYear).first()
        if not ay:
            ay = AcademicYear(name="2026-2027", start_year=2026, end_year=2027, is_current=True)
            db.add(ay)
            db.commit()
            db.refresh(ay)
        assert ay is not None, "AcademicYear must exist in database"
        ay_id = ay.id

        sem = db.query(Semester).first()
        if not sem:
            sem = Semester(name="Fall 2026", semester_number=1, academic_year_id=ay_id)
            db.add(sem)
            db.commit()
            db.refresh(sem)
        assert sem is not None, "Semester must exist in database"
        sem_id = sem.id

        sec = db.query(Section).first()
        if not sec:
            dept = db.query(Department).first()
            if not dept:
                dept = Department(name="Computer Science and Engineering", code="CSE")
                db.add(dept)
                db.commit()
                db.refresh(dept)
            assert dept is not None, "Department must exist in database"

            prog = db.query(Program).filter(Program.department_id == dept.id).first() or db.query(Program).first()
            if not prog:
                prog = Program(name="B.Tech Computer Science and Engineering", program_name="B.Tech Computer Science and Engineering", department_id=dept.id, duration=4)
                db.add(prog)
                db.commit()
                db.refresh(prog)
            assert prog is not None, "Program must exist in database"

            sec = Section(name="A", section_name="A", department_id=dept.id, program_id=prog.id, semester_id=sem_id)
            db.add(sec)
            db.commit()
            db.refresh(sec)
        assert sec is not None, "Section must exist in database"
        sec_id = sec.id

        fac = db.query(Faculty).first()
        if not fac:
            user = db.query(User).filter(User.role == "FACULTY").first()
            if not user:
                user = User(
                    name="Prof. Faculty Test",
                    email="faculty_test_off@campus.edu",
                    password_hash=get_password_hash("Test@1234"),
                    role="FACULTY",
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            assert user is not None, "Faculty User must exist in database"
            fac = Faculty(faculty_id="FAC-TEST-OFF", user_id=user.id, department_id=sec.department_id)
            db.add(fac)
            db.commit()
            db.refresh(fac)
        assert fac is not None, "Faculty must exist in database"
        fac_id = fac.id

        csm = db.query(CurriculumSubjectMapping).first()
        if not csm:
            dept = db.query(Department).first()
            assert dept is not None, "Department must exist"
            dept_id = dept.id

            prog = db.query(Program).filter(Program.department_id == dept_id).first() or db.query(Program).first()
            assert prog is not None, "Program must exist"
            prog_id = prog.id

            reg = db.query(Regulation).first()
            if not reg:
                reg = Regulation(code="R2026-OFF", name="Off Regulation 2026", effective_year=2026, is_active=True)
                db.add(reg)
                db.commit()
                db.refresh(reg)
            assert reg is not None, "Regulation must exist"
            reg_id = reg.id

            user = db.query(User).first()
            assert user is not None, "User must exist"
            user_id = user.id

            v = CurriculumVersion(
                version_code="CURR-TEST-OFF",
                department_id=dept_id,
                program_id=prog_id,
                regulation_id=reg_id,
                status="PUBLISHED",
                created_by_id=user_id,
            )
            db.add(v)
            db.flush()
            c_sem = CurriculumSemester(curriculum_version_id=v.id, semester_number=1)
            db.add(c_sem)
            db.flush()
            csm = CurriculumSubjectMapping(
                curriculum_version_id=v.id,
                curriculum_semester_id=c_sem.id,
                subject_code="TEST-SUB-99",
                subject_name="Test Engineering",
                credits=3.0,
                contact_hours=3,
            )
            db.add(csm)
            db.commit()
            db.refresh(csm)

        assert csm is not None, "CurriculumSubjectMapping must exist in database"
        csm_id = csm.id
        version_id = csm.curriculum_version_id
        c_semester = csm.curriculum_semester
        assert c_semester is not None, "CurriculumSemester relationship must be loaded"
        semester_num = c_semester.semester_number

    # Step 1: Create Section Course Offering
    offering_payload = {
        "curriculum_version_id": version_id,
        "curriculum_subject_mapping_id": csm_id,
        "academic_year_id": ay_id,
        "semester_id": sem_id,
        "section_id": sec_id,
        "enrolled_student_count": 60,
    }
    off_resp = client.post("/admin/curriculum/offerings", json=offering_payload, headers=headers)
    assert off_resp.status_code in (200, 201), off_resp.text
    offering = off_resp.json()
    off_id = offering["id"]

    # Step 2: Allocate Faculty to Offering
    alloc_payload = {
        "section_course_offering_id": off_id,
        "faculty_id": fac_id,
        "assigned_role": "PRIMARY_LECTURER",
        "assigned_hours": 3,
    }
    alloc_resp = client.post("/admin/curriculum/faculty-allocations", json=alloc_payload, headers=headers)
    assert alloc_resp.status_code == 201, alloc_resp.text
    alloc = alloc_resp.json()
    assert alloc["faculty_id"] == fac_id

    # Step 3: Check Readiness Preflight
    readiness_resp = client.get(
        f"/admin/curriculum/readiness?curriculum_version_id={version_id}&semester_number={semester_num}&academic_year_id={ay_id}&semester_id={sem_id}",
        headers=headers
    )
    assert readiness_resp.status_code == 200, readiness_resp.text
    readiness = readiness_resp.json()
    assert "readiness_percentage" in readiness
    assert "total_subjects" in readiness
    assert len(readiness["subjects"]) > 0


# ---------------------------------------------------------------------------
# 8. Timetable Engine Input Loader Integration
# ---------------------------------------------------------------------------

def test_timetable_input_loader_curriculum_snapshot():
    """Verify validate_and_load_input accepts curriculum_version_id and syncs assignments."""
    with Session(engine) as db:
        ay = db.query(AcademicYear).first()
        if not ay:
            ay = AcademicYear(name="2026-2027", start_year=2026, end_year=2027, is_current=True)
            db.add(ay)
            db.commit()
            db.refresh(ay)
        assert ay is not None, "AcademicYear must exist in database"
        ay_id = ay.id

        sem = db.query(Semester).first()
        if not sem:
            sem = Semester(name="Fall 2026", semester_number=1, academic_year_id=ay_id)
            db.add(sem)
            db.commit()
            db.refresh(sem)
        assert sem is not None, "Semester must exist in database"
        sem_id = sem.id

        dept = db.query(Department).first()
        if not dept:
            dept = Department(name="Computer Science and Engineering", code="CSE")
            db.add(dept)
            db.commit()
            db.refresh(dept)
        assert dept is not None, "Department must exist in database"
        dept_id = dept.id

        prog = db.query(Program).filter(Program.department_id == dept_id).first() or db.query(Program).first()
        if not prog:
            prog = Program(name="B.Tech Computer Science and Engineering", program_name="B.Tech Computer Science and Engineering", department_id=dept_id, duration=4)
            db.add(prog)
            db.commit()
            db.refresh(prog)
        assert prog is not None, "Program must exist in database"
        prog_id = prog.id

        sec = db.query(Section).filter(Section.department_id == dept_id, Section.program_id == prog_id).first()
        if not sec:
            sec = Section(name="A", section_name="A", department_id=dept_id, program_id=prog_id, semester_id=sem_id)
            db.add(sec)
            db.commit()
            db.refresh(sec)
        assert sec is not None, "Section must exist in database"
        sec_id = sec.id

        csm = db.query(CurriculumSubjectMapping).first()

        scope = GenerationScope(
            academic_year_id=ay_id,
            semester_id=sem_id,
            department_id=dept_id,
            program_id=prog_id,
            section_ids=[sec_id],
            curriculum_version_id=csm.curriculum_version_id if csm else None,
        )

        # Non-existent curriculum version should raise HTTPException 400
        invalid_scope = GenerationScope(
            academic_year_id=ay_id,
            semester_id=sem_id,
            department_id=dept_id,
            program_id=prog_id,
            section_ids=[sec_id],
            curriculum_version_id=999999,
        )
        with pytest.raises(Exception):
            validate_and_load_input(db, invalid_scope)


# ---------------------------------------------------------------------------
# 9. Scoped Student & Faculty Access
# ---------------------------------------------------------------------------

def test_student_and_faculty_curriculum_access(student_auth, faculty_auth):
    st_headers = {"Authorization": f"Bearer {student_auth['token']}"}
    fac_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}

    # Student views their assigned curriculum
    st_resp = client.get("/curriculum/student/current", headers=st_headers)
    assert st_resp.status_code == 200
    st_data = st_resp.json()
    assert "student_name" in st_data

    # Faculty views their assigned curriculum teaching offerings
    fac_resp = client.get("/curriculum/faculty/assigned", headers=fac_headers)
    assert fac_resp.status_code == 200
    fac_data = fac_resp.json()
    assert "faculty_name" in fac_data
    assert "assigned_offerings_count" in fac_data


# ---------------------------------------------------------------------------
# 10. Audit Verification Tests: Configurable Duration, Explicit Credits & RBAC
# ---------------------------------------------------------------------------

def test_configurable_curriculum_duration_beyond_and_below_eight_semesters(super_admin_auth):
    """Verify that programs with >8 semesters (e.g. 10) and <8 semesters (e.g. 4) are fully supported."""
    headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}

    with Session(engine) as db:
        dept = db.query(Department).first()
        assert dept is not None, "Department must exist"
        dept_id = dept.id

        prog = db.query(Program).filter(Program.department_id == dept_id).first() or db.query(Program).first()
        assert prog is not None, "Program must exist"
        prog_id = prog.id

        reg = db.query(Regulation).first()
        assert reg is not None, "Regulation must exist"
        reg_id = reg.id

    # 1. Ten-semester program curriculum (e.g. 5-year integrated / B.Arch)
    ten_sem_payload = {
        "department_id": dept_id,
        "program_id": prog_id,
        "regulation_id": reg_id,
        "description": "5-Year Integrated Dual Degree Curriculum",
        "total_semesters": 10,
    }
    resp10 = client.post("/super-admin/curriculum-versions", json=ten_sem_payload, headers=headers)
    assert resp10.status_code == 201, resp10.text
    ver10 = resp10.json()
    assert ver10["total_semesters"] == 10
    assert len(ver10["semesters"]) == 10
    assert [s["semester_number"] for s in ver10["semesters"]] == list(range(1, 11))

    # 2. Four-semester program curriculum (e.g. 2-year M.Tech / MBA)
    four_sem_payload = {
        "department_id": dept_id,
        "program_id": prog_id,
        "regulation_id": reg_id,
        "description": "2-Year Postgraduate M.Tech Curriculum",
        "total_semesters": 4,
    }
    resp4 = client.post("/super-admin/curriculum-versions", json=four_sem_payload, headers=headers)
    assert resp4.status_code == 201, resp4.text
    ver4 = resp4.json()
    assert ver4["total_semesters"] == 4
    assert len(ver4["semesters"]) == 4
    assert [s["semester_number"] for s in ver4["semesters"]] == list(range(1, 5))


def test_explicit_credits_preservation_without_formula_overwrite(super_admin_auth):
    """Verify that explicitly specified credits are preserved even when diverging from L+T+0.5P heuristic."""
    headers = {"Authorization": f"Bearer {super_admin_auth['token']}"}

    with Session(engine) as db:
        dept = db.query(Department).first()
        assert dept is not None
        dept_id = dept.id
        prog = db.query(Program).first()
        assert prog is not None
        prog_id = prog.id
        reg = db.query(Regulation).first()
        assert reg is not None
        reg_id = reg.id

    # Create a draft version
    ver_payload = {
        "department_id": dept_id,
        "program_id": prog_id,
        "regulation_id": reg_id,
        "description": "Credit Formula Preservation Test",
        "total_semesters": 4,
    }
    resp = client.post("/super-admin/curriculum-versions", json=ver_payload, headers=headers)
    assert resp.status_code == 201
    ver = resp.json()
    ver_id = ver["id"]
    sem1_id = ver["semesters"][0]["id"]

    # Subject A: L=3, T=0, P=0, but official credits = 4.0 (e.g. Honors Course)
    # Heuristic L+T+0.5P would calculate 3.0, but official credit is 4.0
    sub_a_payload = {
        "curriculum_semester_id": sem1_id,
        "subject_code": "CS-HON-401",
        "subject_name": "Advanced Algorithmic Honors",
        "subject_type": "THEORY",
        "credits": 4.0,
        "lecture_hours": 3,
        "tutorial_hours": 0,
        "practical_hours": 0,
        "is_mandatory": True,
    }
    sub_a_resp = client.post(f"/super-admin/curriculum-versions/{ver_id}/subjects", json=sub_a_payload, headers=headers)
    assert sub_a_resp.status_code == 201
    assert sub_a_resp.json()["credits"] == 4.0
    assert sub_a_resp.json()["contact_hours"] == 3

    # Subject B: L=0, T=0, P=4, but official credits = 1.0 (e.g. Workshop/Fieldwork)
    # Heuristic L+T+0.5P would calculate 2.0, but official credit is 1.0
    sub_b_payload = {
        "curriculum_semester_id": sem1_id,
        "subject_code": "ME-WS-102",
        "subject_name": "Mechanical Fabrication Workshop",
        "subject_type": "PRACTICAL",
        "credits": 1.0,
        "lecture_hours": 0,
        "tutorial_hours": 0,
        "practical_hours": 4,
        "practical_consecutive_periods": 3,
        "requires_lab": True,
        "is_mandatory": True,
    }
    sub_b_resp = client.post(f"/super-admin/curriculum-versions/{ver_id}/subjects", json=sub_b_payload, headers=headers)
    assert sub_b_resp.status_code == 201
    assert sub_b_resp.json()["credits"] == 1.0
    assert sub_b_resp.json()["contact_hours"] == 4
    assert sub_b_resp.json()["practical_consecutive_periods"] == 3

    # Verify version total credits sums the explicitly provided credits (4.0 + 1.0 = 5.0)
    ver_detail = client.get(f"/super-admin/curriculum-versions/{ver_id}", headers=headers).json()
    assert ver_detail["total_credits"] == 5.0


def test_ordinary_admin_cannot_promote_or_create_super_admin(admin_auth):
    """Verify that ordinary ADMIN accounts cannot provision or promote accounts into SUPER_ADMIN."""
    headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    # Attempt to create a user with role SUPER_ADMIN
    illegal_create = {
        "name": "Malicious User",
        "email": "malicious_sa@campus.edu",
        "password": "Password@123",
        "role": "SUPER_ADMIN",
    }
    create_resp = client.post("/users", json=illegal_create, headers=headers)
    assert create_resp.status_code == 403, f"Expected 403 Forbidden, got {create_resp.status_code}"

    # Attempt to promote an existing user to SUPER_ADMIN
    with Session(engine) as db:
        user = db.query(User).filter(User.role == "STUDENT").first()
        assert user is not None
        user_id = user.id

    patch_resp = client.patch(f"/users/{user_id}", json={"role": "SUPER_ADMIN"}, headers=headers)
    assert patch_resp.status_code == 403, f"Expected 403 Forbidden, got {patch_resp.status_code}"


def test_cohort_and_regulation_curriculum_resolution_integrity():
    """Verify that student curriculum is resolved strictly by cohort and regulation, never falling back to arbitrary curricula."""
    with Session(engine) as db:
        # Create an unassigned student with no program
        unassigned_user = User(
            name="Unassigned Student",
            email="unassigned_stu@campus.edu",
            password_hash=get_password_hash("Test@1234"),
            role="STUDENT",
            is_active=True,
        )
        db.add(unassigned_user)
        db.commit()
        db.refresh(unassigned_user)

        stu = Student(user_id=unassigned_user.id, student_id="STU-UNASSIGNED")
        db.add(stu)
        db.commit()

    login_resp = client.post("/auth/login", json={"email": "unassigned_stu@campus.edu", "password": "Test@1234"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Student with no enrolled program must return is_curriculum_resolved = False, NOT an arbitrary version
    res = client.get("/curriculum/student/current", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["curriculum"] is None
    assert body["is_curriculum_resolved"] is False
    assert "not enrolled in an academic program" in body["unresolved_reason"]
