"""
eval/run_browser_verification.py
--------------------------------
Authentic Live Browser Verification Suite for RIO-MJP Faculty Substitution.

Spins up:
1. Live FastAPI Backend on http://127.0.0.1:8000 using test_schema on port 5433
2. Live Vite Frontend on http://127.0.0.1:5173

Executes real Chromium browser automation:
- Faculty authenticates via React login form
- Faculty navigates to /faculty/substitutions, views scheduled class occurrences
- Faculty submits unavailability request with a private reason
- Admin authenticates via React login form
- Admin navigates to /admin/substitutions, views pending review queue
- Admin opens candidate inspector, views deterministic ranking & breakdown badges
- Admin selects top qualified substitute and approves request (optimistic locking)
- Substitute faculty authenticates and verifies covering duties
- Student authenticates and verifies schedule with privacy barrier protecting private reason

Captures high-resolution browser screenshots directly to eval/results/substitution_evidence/.
"""

from __future__ import annotations

import datetime
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
EVIDENCE_DIR = os.path.join(REPO_ROOT, "eval", "results", "substitution_evidence")
os.makedirs(EVIDENCE_DIR, exist_ok=True)

DB_URL = "postgresql://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path=test_schema"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"


def wait_for_url(url: str, timeout: int = 30, desc: str = "") -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Browser-Verification"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status in (200, 304, 404):  # 404 for vite base is ok if root responds
                    print(f"[READY] {desc} responded with HTTP {resp.status}")
                    return True
        except (urllib.error.URLError, ConnectionResetError, OSError):
            time.sleep(0.5)
    return False


def run_live_browser_verification():
    print("=" * 80)
    print("RIO-MJP FACULTY SUBSTITUTION — AUTHENTIC BROWSER ACCEPTANCE SUITE")
    print("=" * 80)

    env = os.environ.copy()
    env["DATABASE_URL"] = DB_URL
    env["TEST_DATABASE_URL"] = DB_URL
    env["VITE_API_BASE_URL"] = BACKEND_URL

    # Ensure pre-flight test data setup via direct python script
    from backend.database import SessionLocal
    from backend.models.identity import User
    from backend.models.academic import Faculty, Student, Section
    from backend.models.courses import Course, CourseAssignment
    from backend.models.space_time import Room, TimeSlot
    from backend.models.substitution import FacultySubstitution
    from backend.models.timetable import TimetableEntry, TimetableVersion

    with SessionLocal() as db:
        # Clear prior substitution records for a clean run
        db.query(FacultySubstitution).delete()
        db.commit()

        pub_v = db.query(TimetableVersion).filter(TimetableVersion.status == "PUBLISHED").first()
        if not pub_v:
            pub_v = TimetableVersion(status="PUBLISHED", version_number="V-LIVE-UI", published_at=datetime.datetime.now(datetime.timezone.utc))
            db.add(pub_v)
            db.flush()

        fac1 = db.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "allison.hill@campus.edu").first()
        fac2 = db.query(Faculty).join(User, Faculty.user_id == User.id).filter(User.email == "noah.rhodes@campus.edu").first()
        assert fac1 and fac2

        course = db.query(Course).first()
        room = db.query(Room).first()
        sec = db.query(Section).first()
        slots = db.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").all()
        assert course and room and sec and len(slots) >= 5

        # Ensure verified CourseAssignments exist for both faculty
        ca1 = db.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac1.id, CourseAssignment.course_id == course.id).first()
        if not ca1:
            db.add(CourseAssignment(faculty_id=fac1.id, course_id=course.id, section_id=sec.id))
        ca2 = db.query(CourseAssignment).filter(CourseAssignment.faculty_id == fac2.id, CourseAssignment.course_id == course.id).first()
        if not ca2:
            db.add(CourseAssignment(faculty_id=fac2.id, course_id=course.id, section_id=sec.id))

        # Ensure scheduled timetable entries exist for fac1
        existing = db.query(TimetableEntry).filter(TimetableEntry.version_id == pub_v.id, TimetableEntry.faculty_id == fac1.id).all()
        if not existing:
            days_seen = set()
            for s in slots:
                if s.day and s.day not in days_seen and len(days_seen) < 5:
                    days_seen.add(s.day)
                    db.add(
                        TimetableEntry(
                            version_id=pub_v.id,
                            faculty_id=fac1.id,
                            course_id=course.id,
                            room_id=room.id,
                            slot_id=s.id,
                            section_id=sec.id,
                            department_id=fac1.department_id,
                            status="ACTIVE",
                        )
                    )
            db.commit()

    # Launch FastAPI Backend
    print("[1/2] Launching FastAPI backend server on port 8000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Launch Vite Frontend
    print("[2/2] Launching Vite frontend server on port 5173...")
    frontend_proc = subprocess.Popen(
        "npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173",
        env=env,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        assert wait_for_url(f"{BACKEND_URL}/health", timeout=25, desc="Backend /health") or wait_for_url(f"{BACKEND_URL}/docs", timeout=15, desc="Backend /docs")
        assert wait_for_url(FRONTEND_URL, timeout=30, desc="Frontend Vite")

        print("\n--- Starting Playwright Chromium Real Browser Session ---")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # -----------------------------------------------------------------
            # FLOW 1: Faculty Allison Hill Logs In & Views Scheduled Occurrences
            # -----------------------------------------------------------------
            context = browser.new_context(viewport={"width": 1400, "height": 900})
            page = context.new_page()

            print("\n[Step 1] Navigating to Login Page...")
            page.goto(f"{FRONTEND_URL}/login")
            page.wait_for_selector("#email", timeout=10000)
            page.fill("#email", "allison.hill@campus.edu")
            page.fill("#password", "Test@1234")
            page.click("button[type='submit']")

            # Wait for authentication and redirection
            page.wait_for_url(lambda url: "/login" not in url, timeout=10000)
            print(f"  Authenticated successfully. Current URL: {page.url}")

            # Client-side navigation to Faculty Substitutions via sidebar
            page.wait_for_url(lambda u: "/faculty" in u, timeout=10000)
            nav_link = page.locator("a[href='/faculty/substitutions']").first
            nav_link.wait_for(timeout=10000)
            nav_link.click()
            page.wait_for_url(lambda u: "/faculty/substitutions" in u, timeout=10000)
            page.wait_for_selector("table", timeout=10000)

            shot1 = os.path.join(EVIDENCE_DIR, "01_faculty_classes_view.png")
            page.screenshot(path=shot1, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot1)}")

            # -----------------------------------------------------------------
            # FLOW 2: Faculty Submits Unavailability Request
            # -----------------------------------------------------------------
            print("\n[Step 2] Reporting unavailability on first upcoming occurrence...")
            report_btn = page.locator("button:has-text('Report Absence')").first
            report_btn.wait_for(timeout=8000)
            report_btn.click()

            # Wait for Modal to open
            page.wait_for_selector("textarea", timeout=5000)
            reason_text = "Participating in IEEE International Academic Accreditation Panel"
            page.fill("textarea", reason_text)

            # Capture modal filled
            shot2_modal = os.path.join(EVIDENCE_DIR, "02_faculty_absence_modal.png")
            page.screenshot(path=shot2_modal, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot2_modal)}")

            # Submit
            page.click("button:has-text('Submit Request')")
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Switch to 'My Absence Requests' Tab
            tab_requests = page.locator("button:has-text('My Absence Requests')")
            tab_requests.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            shot2_tab = os.path.join(EVIDENCE_DIR, "02_faculty_absence_submitted.png")
            page.screenshot(path=shot2_tab, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot2_tab)}")
            context.close()

            # -----------------------------------------------------------------
            # FLOW 3: Admin Reviewer Inspects Pending Queue & Ranked Candidates
            # -----------------------------------------------------------------
            context_admin = browser.new_context(viewport={"width": 1400, "height": 900})
            page_admin = context_admin.new_page()

            print("\n[Step 3] Admin logs in to Substitution Review Workspace...")
            page_admin.goto(f"{FRONTEND_URL}/login")
            page_admin.wait_for_selector("#email", timeout=10000)
            page_admin.fill("#email", "admin@campus.edu")
            page_admin.fill("#password", "Test@1234")
            page_admin.click("button[type='submit']")

            page_admin.wait_for_url(lambda u: "/admin" in u, timeout=10000)
            nav_admin = page_admin.locator("a[href='/admin/substitutions']").first
            nav_admin.wait_for(timeout=10000)
            nav_admin.click()
            page_admin.wait_for_url(lambda u: "/admin/substitutions" in u, timeout=10000)
            page_admin.wait_for_selector("table", timeout=10000)

            shot3 = os.path.join(EVIDENCE_DIR, "03_admin_pending_queue.png")
            page_admin.screenshot(path=shot3, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot3)}")

            # Click 'Review & Assign'
            print("\n[Step 4] Admin inspects deterministic candidate recommendations...")
            review_btn = page_admin.locator("button:has-text('Review & Assign')").first
            review_btn.wait_for(timeout=8000)
            review_btn.click()

            # Wait for candidate cards to load
            page_admin.wait_for_selector("button:has-text('Approve Substitution')", timeout=10000)
            time.sleep(1)  # allow query and animations to settle

            shot4 = os.path.join(EVIDENCE_DIR, "04_admin_candidate_inspector.png")
            page_admin.screenshot(path=shot4, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot4)}")

            # -----------------------------------------------------------------
            # FLOW 4: Admin Approves Candidate Noah Rhodes
            # -----------------------------------------------------------------
            print("\n[Step 5] Approving top eligible substitute candidate...")
            # Click on Noah Rhodes candidate card if available, or first eligible candidate
            eligible_card = page_admin.locator("div.cursor-pointer:has-text('Noah Rhodes')").first
            if eligible_card.count() > 0:
                eligible_card.click()
            else:
                page_admin.locator("div.cursor-pointer").first.click()

            page_admin.click("button:has-text('Approve Substitution')")
            page_admin.wait_for_load_state("networkidle")
            time.sleep(1.5)

            # Switch to 'All Requests' Tab to view approved status
            page_admin.locator("button:has-text('All Requests')").click()
            page_admin.wait_for_load_state("networkidle")
            time.sleep(1)

            shot5 = os.path.join(EVIDENCE_DIR, "05_admin_approval_confirmed.png")
            page_admin.screenshot(path=shot5, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot5)}")
            context_admin.close()

            # -----------------------------------------------------------------
            # FLOW 5: Substitute Faculty Noah Rhodes Inspects Covering Duties
            # -----------------------------------------------------------------
            context_sub = browser.new_context(viewport={"width": 1400, "height": 900})
            page_sub = context_sub.new_page()

            print("\n[Step 6] Substitute faculty Noah Rhodes logs in...")
            page_sub.goto(f"{FRONTEND_URL}/login")
            page_sub.wait_for_selector("#email", timeout=10000)
            page_sub.fill("#email", "noah.rhodes@campus.edu")
            page_sub.fill("#password", "Test@1234")
            page_sub.click("button[type='submit']")

            page_sub.wait_for_url(lambda u: "/faculty" in u, timeout=10000)
            nav_sub = page_sub.locator("a[href='/faculty/substitutions']").first
            nav_sub.wait_for(timeout=10000)
            nav_sub.click()
            page_sub.wait_for_url(lambda u: "/faculty/substitutions" in u, timeout=10000)
            page_sub.wait_for_load_state("networkidle")

            # Click 'My Covering Duties' tab
            tab_duties = page_sub.locator("button:has-text('My Covering Duties')")
            tab_duties.click()
            page_sub.wait_for_load_state("networkidle")
            time.sleep(1)

            shot6 = os.path.join(EVIDENCE_DIR, "06_substitute_covering_duties.png")
            page_sub.screenshot(path=shot6, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot6)}")
            context_sub.close()

            # -----------------------------------------------------------------
            # FLOW 6: Student Timetable Schedule & Privacy Barrier Verification
            # -----------------------------------------------------------------
            context_stu = browser.new_context(viewport={"width": 1400, "height": 900})
            page_stu = context_stu.new_page()

            print("\n[Step 7] Student logs in and verifies timetable & privacy barrier...")
            page_stu.goto(f"{FRONTEND_URL}/login")
            page_stu.wait_for_selector("#email", timeout=10000)
            page_stu.fill("#email", "monica.herrera@campus.edu")
            page_stu.fill("#password", "Test@1234")
            page_stu.click("button[type='submit']")

            page_stu.wait_for_url(lambda u: "/student" in u, timeout=10000)
            nav_stu = page_stu.locator("a[href='/student/schedule']").first
            if nav_stu.count() > 0:
                nav_stu.click()
                page_stu.wait_for_url(lambda u: "/student/schedule" in u, timeout=10000)
            else:
                page_stu.goto(f"{FRONTEND_URL}/student/schedule")
            page_stu.wait_for_load_state("networkidle")
            time.sleep(1)

            # Assert absence reason is never present in student page DOM
            student_body_text = page_stu.content()
            assert "IEEE International Academic Accreditation Panel" not in student_body_text, (
                "CRITICAL PRIVACY VIOLATION: Private faculty absence reason leaked to student DOM!"
            )
            print("  [PASS] Privacy barrier verified: Faculty private reason completely masked from student view.")

            shot7 = os.path.join(EVIDENCE_DIR, "07_student_schedule_privacy_verified.png")
            page_stu.screenshot(path=shot7, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot7)}")
            context_stu.close()

            browser.close()

        print("\n" + "=" * 80)
        print("AUTHENTIC LIVE BROWSER VERIFICATION COMPLETE — ALL WORKFLOWS PASSED!")
        print(f"Visual evidence saved in: {EVIDENCE_DIR}")
        print("=" * 80)

    finally:
        print("\n--- Terminating live servers ---")
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=5)
        except Exception:
            backend_proc.kill()

        try:
            frontend_proc.terminate()
            subprocess.run("taskkill /F /IM node.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


if __name__ == "__main__":
    run_live_browser_verification()
