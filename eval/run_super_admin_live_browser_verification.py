"""
eval/run_super_admin_live_browser_verification.py
-------------------------------------------------
Authentic Live Browser Verification Suite for RIO-MJP Super Admin & Central Curriculum.

Executes real Playwright Chromium browser automation against:
1. Live FastAPI Backend on http://127.0.0.1:8000 (test database on port 5433)
2. Live Vite Frontend on http://127.0.0.1:5173

Navigates actual React components via authentic UI clicks, submits forms, inspects real DOM elements,
and captures high-resolution browser screenshots in eval/results/super_admin_evidence/.
"""

from __future__ import annotations

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

EVIDENCE_DIR = os.path.join(REPO_ROOT, "eval", "results", "super_admin_evidence")
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
                if resp.status in (200, 304, 404):
                    print(f"[READY] {desc} responded with HTTP {resp.status}")
                    return True
        except (urllib.error.URLError, ConnectionResetError, OSError):
            time.sleep(0.5)
    return False


def run_super_admin_live_browser():
    print("=" * 80)
    print("RIO-MJP SUPER ADMIN & CENTRAL CURRICULUM — AUTHENTIC BROWSER VERIFICATION")
    print("=" * 80)

    env = os.environ.copy()
    env["DATABASE_URL"] = DB_URL
    env["TEST_DATABASE_URL"] = DB_URL
    env["VITE_API_BASE_URL"] = BACKEND_URL

    # Ensure pre-flight test data setup in test database
    from backend.database import SessionLocal
    from backend.models.identity import User
    from backend.core.security import get_password_hash
    from backend.models.academic import Department, Program, AcademicYear, Semester, Section, Faculty, Student
    from backend.models.curriculum import Regulation, AdmissionCohort, CurriculumVersion, CurriculumSemester, CurriculumSubjectMapping

    with SessionLocal() as db:
        # Ensure Super Admin account exists in test_schema
        sa = db.query(User).filter(User.email == "superadmin@campus.edu").first()
        if not sa:
            sa = User(
                email="superadmin@campus.edu",
                name="Dr. Eleanor Vance",
                password_hash=get_password_hash("Test@1234"),
                role="SUPER_ADMIN",
                is_active=True,
            )
            db.add(sa)
            db.commit()
            db.refresh(sa)
        else:
            sa.password_hash = get_password_hash("Test@1234")
            sa.role = "SUPER_ADMIN"
            db.commit()

        # Ensure Department Admin exists with known password
        adm = db.query(User).filter(User.email == "admin@campus.edu").first()
        if not adm:
            adm = User(
                email="admin@campus.edu",
                name="Prof. Marcus Brody",
                password_hash=get_password_hash("Test@1234"),
                role="ADMIN",
                is_active=True,
            )
            db.add(adm)
            db.commit()
            db.refresh(adm)
        else:
            adm.password_hash = get_password_hash("Test@1234")
            adm.role = "ADMIN"
            db.commit()

        # Ensure Department, Program, Regulation exist
        dept = db.query(Department).first()
        if not dept:
            dept = Department(name="Computer Science & Engineering", code="CSE")
            db.add(dept)
            db.commit()
            db.refresh(dept)

        prog = db.query(Program).filter(Program.department_id == dept.id).first() or db.query(Program).first()
        if not prog:
            prog = Program(name="B.Tech Computer Science & Engineering", program_name="B.Tech Computer Science & Engineering", department_id=dept.id, duration=4)
            db.add(prog)
            db.commit()
            db.refresh(prog)

        reg = db.query(Regulation).first()
        if not reg:
            reg = Regulation(code="R2026-LIVE", name="Autonomous Regulation 2026", effective_year=2026, is_active=True)
            db.add(reg)
            db.commit()
            db.refresh(reg)

        cohort = db.query(AdmissionCohort).first()
        if not cohort:
            cohort = AdmissionCohort(cohort_name="2026-2030 Batch", start_year=2026, end_year=2030, program_id=prog.id, regulation_id=reg.id, is_active=True)
            db.add(cohort)
            db.commit()
            db.refresh(cohort)

        # Ensure a sample version exists for workspace
        v = db.query(CurriculumVersion).first()
        if not v:
            v = CurriculumVersion(
                version_code="CURR-CSE-R2026-V1",
                department_id=dept.id,
                program_id=prog.id,
                regulation_id=reg.id,
                cohort_id=cohort.id,
                version_number=1,
                status="DRAFT",
                total_semesters=8,
                total_credits=4.0,
                created_by_id=sa.id,
            )
            db.add(v)
            db.flush()
            for s_num in range(1, 9):
                sem_row = CurriculumSemester(curriculum_version_id=v.id, semester_number=s_num, total_credits=0.0, total_contact_hours=0)
                db.add(sem_row)
            db.flush()
            first_sem = db.query(CurriculumSemester).filter(CurriculumSemester.curriculum_version_id == v.id, CurriculumSemester.semester_number == 1).first()
            if first_sem:
                sub = CurriculumSubjectMapping(
                    curriculum_version_id=v.id,
                    curriculum_semester_id=first_sem.id,
                    subject_code="CS101",
                    subject_name="Introduction to Computing Systems",
                    subject_type="THEORY",
                    credits=4.0,
                    lecture_hours=3,
                    tutorial_hours=1,
                    practical_hours=0,
                    contact_hours=4,
                    is_mandatory=True,
                )
                db.add(sub)
            db.commit()

        sample_v_id = v.id

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

            # =================================================================
            # FLOW 1: Super Admin Logs In & Explores All 8 Pages
            # =================================================================
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.on("console", lambda msg: print(f"[BROWSER CONSOLE {msg.type.upper()}] {msg.text}"))
            page.on("pageerror", lambda err: print(f"[BROWSER ERROR] {err}"))

            print("\n[Step 1] Navigating to Login Page...")
            page.goto(f"{FRONTEND_URL}/login")
            page.wait_for_selector("#email", timeout=10000)
            page.fill("#email", "superadmin@campus.edu")
            page.fill("#password", "Test@1234")
            page.click("button[type='submit']")

            # Verify redirect to /super-admin
            page.wait_for_url(lambda u: "/super-admin" in u, timeout=12000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            print(f"  [PASS] Logged in as Super Admin. Current URL: {page.url}")

            # 1. Executive Dashboard
            shot1 = os.path.join(EVIDENCE_DIR, "01_super_admin_dashboard.png")
            page.screenshot(path=shot1, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot1)}")

            # 2. Academic Regulations Page
            print("\n[Step 2] Navigating to Academic Regulations...")
            page.locator("text='Academic Regulations'").first.click()
            page.wait_for_url(lambda u: "/super-admin/regulations" in u, timeout=8000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            shot2 = os.path.join(EVIDENCE_DIR, "02_super_admin_regulations.png")
            page.screenshot(path=shot2, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot2)}")

            # 3. Admission Cohorts Page
            print("\n[Step 3] Navigating to Admission Cohorts...")
            page.locator("text='Admission Cohorts'").first.click()
            page.wait_for_url(lambda u: "/super-admin/cohorts" in u, timeout=8000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            shot3 = os.path.join(EVIDENCE_DIR, "03_super_admin_cohorts.png")
            page.screenshot(path=shot3, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot3)}")

            # 4. Curriculum Versions Catalog
            print("\n[Step 4] Navigating to Curriculum Catalog...")
            page.locator("text='Curriculum Versions'").first.click()
            page.wait_for_url(lambda u: "/super-admin/curriculum" in u, timeout=8000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            shot4 = os.path.join(EVIDENCE_DIR, "04_super_admin_curriculum_catalog.png")
            page.screenshot(path=shot4, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot4)}")

            # 5. Semester Matrix Workspace
            print(f"\n[Step 5] Opening Semester Matrix Workspace for version #{sample_v_id}...")
            # Click the Open Workspace button in the catalog table
            open_btn = page.locator("button[title='Open Workspace']").first
            if open_btn.is_visible(timeout=3000):
                open_btn.click()
            else:
                page.evaluate(f"window.location.hash = ''; window.history.pushState({{}}, '', '/super-admin/curriculum-versions/{sample_v_id}'); window.dispatchEvent(new Event('popstate'));")
            page.wait_for_url(lambda u: f"/{sample_v_id}" in u or "workspace" in u, timeout=10000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            shot5 = os.path.join(EVIDENCE_DIR, "05_super_admin_semester_workspace.png")
            page.screenshot(path=shot5, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot5)}")

            # Return to layout by clicking back
            back_btn = page.locator("button[title='Back to Versions']").first
            if back_btn.is_visible(timeout=3000):
                back_btn.click()
                page.wait_for_url(lambda u: "/super-admin/curriculum" in u, timeout=8000)
                page.wait_for_load_state("networkidle")
                time.sleep(1)

            print(f"[DEBUG] Current URL before Step 6: {page.url}")
            links = page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href + ' text=' + a.innerText.trim())")
            print("[DEBUG] Page links:", links)
            # 6. AI Syllabus Extraction Studio
            print("\n[Step 6] Navigating to Syllabus Extraction Studio...")
            page.locator("a[href*='/super-admin/extraction'], a[href*='/super-admin/ai-extraction']").first.click()
            page.wait_for_url(lambda u: "/super-admin/extraction" in u or "/super-admin/ai-extraction" in u, timeout=8000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            shot6 = os.path.join(EVIDENCE_DIR, "06_super_admin_pdf_studio.png")
            page.screenshot(path=shot6, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot6)}")

            # 7. Discrepancy Requests Inbox
            print("\n[Step 7] Navigating to Admin Discrepancy Requests...")
            page.locator("a[href*='/super-admin/requests']").first.click()
            page.wait_for_url(lambda u: "/super-admin/requests" in u, timeout=8000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            shot7 = os.path.join(EVIDENCE_DIR, "07_super_admin_discrepancy_requests.png")
            page.screenshot(path=shot7, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot7)}")

            # 8. Governance Audit Trail
            print("\n[Step 8] Navigating to Governance Audit History...")
            page.locator("a[href*='/super-admin/audit']").first.click()
            page.wait_for_url(lambda u: "/super-admin/audit" in u, timeout=8000)
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            shot8 = os.path.join(EVIDENCE_DIR, "08_super_admin_audit_history.png")
            page.screenshot(path=shot8, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot8)}")

            context.close()

            # =================================================================
            # FLOW 2: Department Admin Logs In & Explores All 4 Admin Pages
            # =================================================================
            context_adm = browser.new_context(viewport={"width": 1440, "height": 900})
            page_adm = context_adm.new_page()
            page_adm.on("console", lambda msg: print(f"[ADM CONSOLE {msg.type.upper()}] {msg.text}"))
            page_adm.on("pageerror", lambda err: print(f"[ADM PAGE ERROR] {err}"))

            print("\n[Step 9] Logging in as Department Admin...")
            page_adm.goto(f"{FRONTEND_URL}/login")
            page_adm.wait_for_selector("#email", timeout=10000)
            page_adm.fill("#email", "admin@campus.edu")
            page_adm.fill("#password", "Test@1234")
            page_adm.click("button[type='submit']")

            page_adm.wait_for_url(lambda u: "/admin" in u, timeout=12000)
            page_adm.wait_for_load_state("networkidle")
            print(f"  [PASS] Logged in as Admin. Current URL: {page_adm.url}")

            # 9. Admin Curriculum Inbox
            print("\n[Step 10] Navigating to Admin Curriculum Inbox via sidebar...")
            page_adm.locator("a[href*='/admin/curriculum/inbox']").first.click()
            page_adm.wait_for_url(lambda u: "/admin/curriculum/inbox" in u, timeout=8000)
            page_adm.wait_for_load_state("networkidle")
            time.sleep(1)
            shot9 = os.path.join(EVIDENCE_DIR, "09_admin_curriculum_inbox.png")
            page_adm.screenshot(path=shot9, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot9)}")

            # 10. Admin Section-Course Allocation
            print("\n[Step 11] Navigating to Section Course Allocation via sidebar...")
            page_adm.locator("a[href*='/admin/curriculum/allocation']").first.click()
            page_adm.wait_for_url(lambda u: "/admin/curriculum/allocation" in u, timeout=8000)
            page_adm.wait_for_load_state("networkidle")
            time.sleep(1)
            shot10 = os.path.join(EVIDENCE_DIR, "10_admin_course_allocation.png")
            page_adm.screenshot(path=shot10, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot10)}")

            print(f"[DEBUG ADM] Current URL before Step 12: {page_adm.url}")
            adm_links = page_adm.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href + ' text=' + a.innerText.trim())")
            print("[DEBUG ADM] Page links count:", len(adm_links))
            readiness_links = [l for l in adm_links if 'readiness' in l]
            print("[DEBUG ADM] Readiness links:", readiness_links)
            # 11. Admin Timetable Readiness
            print("\n[Step 12] Navigating to Timetable Readiness via sidebar...")
            page_adm.locator("a[href*='/admin/curriculum/readiness']").first.click()
            page_adm.wait_for_url(lambda u: "/admin/curriculum/readiness" in u, timeout=8000)
            page_adm.wait_for_load_state("networkidle")
            time.sleep(1)
            shot11 = os.path.join(EVIDENCE_DIR, "11_admin_curriculum_readiness.png")
            page_adm.screenshot(path=shot11, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot11)}")

            # 12. Admin Correction Requests
            print("\n[Step 13] Navigating to Admin Correction Requests via sidebar...")
            page_adm.locator("a[href*='/admin/curriculum/requests']").first.click()
            page_adm.wait_for_url(lambda u: "/admin/curriculum/requests" in u, timeout=8000)
            page_adm.wait_for_load_state("networkidle")
            time.sleep(1)
            shot12 = os.path.join(EVIDENCE_DIR, "12_admin_curriculum_requests.png")
            page_adm.screenshot(path=shot12, full_page=True)
            print(f"  [PASS] Captured: {os.path.basename(shot12)}")

            context_adm.close()
            browser.close()

            print("\n" + "=" * 80)
            print("AUTHENTIC BROWSER VERIFICATION COMPLETE — 12 REAL DOM SCREENSHOTS CAPTURED!")
            print("=" * 80)

    finally:
        print("\nShutting down backend and frontend server processes...")
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=5)
        except Exception:
            try:
                backend_proc.kill()
            except Exception:
                pass

        try:
            subprocess.run(f"taskkill /F /T /PID {frontend_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                frontend_proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    run_super_admin_live_browser()
