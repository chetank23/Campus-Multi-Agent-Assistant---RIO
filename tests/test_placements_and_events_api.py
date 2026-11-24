"""
tests/test_placements_and_events_api.py
---------------------------------------
End-to-end integration tests for Placements, Clubs, Events, and Curriculum upload security.
Verifies real database persistence, RBAC enforcement, status code handling, and business constraints.
"""

import datetime
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.config import SessionLocal, engine
from backend.main import app
from backend.models.identity import User

client = TestClient(app)

ADMIN_CREDENTIALS = {"email": "admin@campus.edu", "password": "Test@1234"}
SUPERADMIN_CREDENTIALS = {"email": "superadmin@campus.edu", "password": "Test@1234"}


def get_token(credentials: dict) -> str:
    res = client.post("/auth/login", json=credentials)
    if res.status_code != 200:
        fallback = {**credentials, "password": "Admin#RioLocal26"}
        res = client.post("/auth/login", json=fallback)
    assert res.status_code == 200, f"Login failed for {credentials['email']}: {res.text}"
    return res.json()["access_token"]


def get_student_token() -> str:
    from backend.core.security import create_access_token
    from backend.models.academic import Student
    from backend.models.placements import StudentAcademicRecord

    with Session(engine) as db:
        # Prefer a verified student with academic record
        acad = db.query(StudentAcademicRecord).filter(StudentAcademicRecord.is_verified == True).first()
        if acad and acad.student and acad.student.user:
            return create_access_token(data={"sub": str(acad.student.user.id), "role": "STUDENT"})

        student = db.query(Student).join(User, Student.user_id == User.id).first()
        if student and student.user:
            return create_access_token(data={"sub": str(student.user.id), "role": "STUDENT"})

    for email in ["monica.herrera@campus.edu", "r23eh001@rio-mjp.test", "r23eh009@rio-mjp.test"]:
        for pwd in ["Test@1234", "Student#RioLocal26", "R23eh001#RioLocal26", "Password@123"]:
            res = client.post("/auth/login", json={"email": email, "password": pwd})
            if res.status_code == 200:
                return res.json()["access_token"]
    raise RuntimeError("Failed to authenticate as test student")


def test_list_placement_drives():
    admin_token = get_token(ADMIN_CREDENTIALS)
    res = client.get(
        "/placements/drives",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    drives = res.json()
    assert isinstance(drives, list)
    assert len(drives) >= 1
    assert "company_name" in drives[0]
    assert "job_role" in drives[0]


def test_placement_application_lifecycle():
    admin_token = get_token(ADMIN_CREDENTIALS)
    student_token = get_student_token()

    # 1. Fetch drives
    res = client.get(
        "/placements/drives",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 200
    drives = res.json()
    assert len(drives) > 0

    eligible_drives = [
        d for d in drives
        if d.get("status") == "PUBLISHED"
        and not d.get("is_deadline_passed")
        and (d.get("eligibility") is None or d.get("eligibility", {}).get("is_eligible", False))
    ]
    if eligible_drives:
        target_drive_id = eligible_drives[0]["id"]
    else:
        # Create an open eligible drive for the student
        create_res = client.post(
            "/placements/drives",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "company_name": f"Acme Testing {int(datetime.datetime.now().timestamp())}",
                "title": f"Software Engineer {int(datetime.datetime.now().timestamp())}",
                "job_role": "Full Stack Engineer",
                "job_type": "FULL_TIME",
                "application_deadline": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat(),
            },
        )
        assert create_res.status_code in (200, 201), f"Failed to create drive: {create_res.text}"
        target_drive_id = create_res.json()["id"]
        pub_res = client.post(
            f"/placements/drives/{target_drive_id}/publish",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert pub_res.status_code == 200

    # 2. Student applies
    apply_res = client.post(
        f"/placements/drives/{target_drive_id}/apply",
        headers={"Authorization": f"Bearer {student_token}"},
        json={
            "resume_url": "https://drive.google.com/file/d/test-resume/view",
            "notes": "E2E integration test application.",
        },
    )
    # 201 (created), 200 (ok), or 409 (already applied)
    assert apply_res.status_code in (200, 201, 409)

    # 3. Student views my applications
    my_apps_res = client.get(
        "/placements/my-applications",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert my_apps_res.status_code == 200
    my_apps = my_apps_res.json()
    assert isinstance(my_apps, list)
    assert any(a["drive_id"] == target_drive_id for a in my_apps)

    # 4. Admin views applications for that drive
    admin_apps_res = client.get(
        f"/placements/drives/{target_drive_id}/applications",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_apps_res.status_code == 200
    drive_apps = admin_apps_res.json()
    assert isinstance(drive_apps, list)
    assert len(drive_apps) >= 1

    app_id = drive_apps[0]["id"]

    # 5. Admin updates application status
    patch_res = client.patch(
        f"/placements/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "SHORTLISTED", "notes": "Candidate shortlisted for technical round."},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["status"] == "SHORTLISTED"


def test_club_membership_lifecycle():
    student_token = get_student_token()

    # 1. List clubs
    clubs_res = client.get(
        "/clubs",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert clubs_res.status_code == 200
    clubs = clubs_res.json()
    assert len(clubs) > 0
    target_club_id = clubs[0]["id"]

    # 2. Join club
    join_res = client.post(
        f"/clubs/{target_club_id}/join",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"role": "MEMBER"},
    )
    assert join_res.status_code in (200, 201, 409)

    # 3. View my memberships
    mems_res = client.get(
        "/clubs/my-memberships",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert mems_res.status_code == 200
    memberships = mems_res.json()
    assert isinstance(memberships, list)
    assert any(m["club_id"] == target_club_id for m in memberships)

    # 4. Leave club
    leave_res = client.post(
        f"/clubs/{target_club_id}/leave",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert leave_res.status_code == 200


def test_event_registration_lifecycle():
    student_token = get_student_token()

    # 1. List events
    events_res = client.get(
        "/events",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) > 0
    target_event_id = events[0]["id"]

    # 2. Register for event
    reg_res = client.post(
        f"/events/{target_event_id}/register",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"notes": "Registering for test event."},
    )
    assert reg_res.status_code in (200, 201, 409)

    # 3. View my registrations
    my_regs_res = client.get(
        "/events/my-registrations",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert my_regs_res.status_code == 200
    regs = my_regs_res.json()
    assert any(r["event_id"] == target_event_id for r in regs)

    # 4. Cancel registration
    cancel_res = client.post(
        f"/events/{target_event_id}/cancel-registration",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert cancel_res.status_code == 200


def test_curriculum_upload_security():
    super_admin_token = get_token(SUPERADMIN_CREDENTIALS)

    # 1. Rejects non-PDF file (magic byte validation)
    fake_pdf = io.BytesIO(b"This is a plaintext file, not a real PDF.")
    res = client.post(
        "/super-admin/documents/upload",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        data={"title": "Test Document"},
        files={"file": ("fake.pdf", fake_pdf, "application/pdf")},
    )
    assert res.status_code == 400
    assert "invalid file signature" in res.json().get("detail", "").lower()

    # 2. Rejects file exceeding 25 MB limit
    oversized_data = b"%PDF-1.4\n" + (b"0" * (25 * 1024 * 1024 + 100))
    oversized_file = io.BytesIO(oversized_data)
    res_oversized = client.post(
        "/super-admin/documents/upload",
        headers={"Authorization": f"Bearer {super_admin_token}"},
        data={"title": "Oversized Document"},
        files={"file": ("big.pdf", oversized_file, "application/pdf")},
    )
    assert res_oversized.status_code == 413
    assert "exceeds" in res_oversized.json().get("detail", "").lower()
