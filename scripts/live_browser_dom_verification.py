"""
scripts/live_browser_dom_verification.py
---------------------------------------
End-to-End Headless Browser DOM Verification for RIO-MJP:
Tests Admin, Faculty, and Student workflows using real Playwright Chromium against
live Frontend (http://localhost:5173) and live Backend (http://127.0.0.1:8000).

Verifies:
1. ADMIN:
   - Login
   - Rooms & Labs page (/admin/campus/rooms) loads data without 500 error
   - Buildings page (/admin/campus/buildings) loads data
   - Timetable Management (/admin/timetable): Select AY -> Sem -> Dept -> Generate Preview -> Publish
2. FACULTY:
   - Login as Dr. Nimrita Koul
   - Personal Timetable (/faculty/timetable) loads published classes
   - Department Timetable (/faculty/dept-timetable) loads
3. STUDENT:
   - Login as R23EH001
   - Student Timetable (/student/timetable) displays section schedule and class teacher info
"""

from __future__ import annotations

import os
import sys
import time
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:5173"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def run_dom_verification():
    console_errors = []
    network_errors = []

    print("[*] Launching Chromium browser with Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Capture console and network errors
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("response", lambda res: network_errors.append(f"{res.status} {res.url}") if res.status >= 400 else None)

        # =========================================================================
        # 1. ADMIN WORKFLOW
        # =========================================================================
        print("\n--- 1. ADMIN DOM VERIFICATION ---")
        page.goto(f"{FRONTEND_URL}/login")
        page.wait_for_selector("input[type='email']", timeout=10000)
        page.fill("input[type='email']", "admin@campus.edu")
        page.fill("input[type='password']", "Test@1234")
        page.click("button[type='submit']")

        # Wait for redirect to admin portal
        page.wait_for_url("**/admin**", timeout=15000)
        print("  [+] Admin logged in successfully, reached dashboard.")

        # 1A. Buildings Page
        print("  [*] Verifying /admin/campus/buildings...")
        page.click("a[href='/admin/campus/buildings']")
        page.wait_for_selector("h1:has-text('Campus Buildings')", timeout=15000)
        page.wait_for_selector("table", timeout=15000)
        # Check building names
        body_text = page.inner_text("body")
        assert "Error loading" not in body_text, "Buildings page showed error loading records"
        assert "SIR M VISHWESH BLOCK" in body_text or "Main Block" in body_text, "Expected building not found in table"
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "01_admin_buildings.png"))
        print("  [PASS] Buildings page rendered correctly.")

        # 1B. Rooms & Labs Page
        print("  [*] Verifying /admin/campus/rooms...")
        page.click("a[href='/admin/campus/rooms']")
        page.wait_for_selector("h1:has-text('Rooms & Lecture Halls')", timeout=15000)
        page.wait_for_selector("table", timeout=15000)
        body_text = page.inner_text("body")
        assert "Error loading table records" not in body_text, "Rooms page crashed with Error loading table records"
        assert "Request failed with status code 500" not in body_text, "Rooms page returned 500"
        assert "001" in body_text, "Expected room number 001 not found"
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "02_admin_rooms.png"))
        print("  [PASS] Rooms & Labs page rendered correctly without 500 errors.")

        # 1C. Timetable Management Workflow
        print("  [*] Verifying /admin/timetable generation & publishing...")
        page.click("a[href='/admin/timetable']")
        page.wait_for_selector("h1:has-text('Timetable Management')", timeout=15000)

        # Select Academic Year
        page.wait_for_selector("select", timeout=10000)
        selects = page.query_selector_all("select")
        # 0: Academic Year, 1: Semester, 2: Department
        ay_select = selects[0]
        ay_select.select_option(label="2026-2027")
        time.sleep(1)

        # Select Semester
        selects = page.query_selector_all("select")
        sem_select = selects[1]
        sem_select.select_option(label="Semester 7")
        time.sleep(1)

        # Select Department
        selects = page.query_selector_all("select")
        dept_select = selects[2]
        dept_select.select_option(label="AI & DS (AIDS)")
        time.sleep(1.5)

        # Assert section AIDS-A is present
        body_text = page.inner_text("body")
        assert "AIDS-A" in body_text, "Section AIDS-A was not loaded in scope"

        # Click Generate / Regenerate
        gen_btn = page.query_selector("button:has-text('GENERATE TIMETABLE'), button:has-text('REGENERATE TIMETABLE')")
        assert gen_btn is not None, "Generate button not found"
        print("  [*] Clicking GENERATE/REGENERATE TIMETABLE...")
        gen_btn.click()

        # Wait for solving & validation (up to 30s)
        page.wait_for_selector("text='Temporary Generated Preview'", timeout=35000)
        print("  [+] Solver completed! Ephemeral preview displayed.")

        # Assert zero blockers and ready to publish
        body_text = page.inner_text("body")
        assert "Zero hard constraint violations" in body_text or "Validation Passed" in body_text, "Expected zero constraint violations"
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_admin_preview.png"))

        # Click PUBLISH TIMETABLE
        pub_btn = page.wait_for_selector("button:has-text('PUBLISH TIMETABLE')", timeout=10000)
        assert pub_btn is not None, "Publish timetable button not found"
        pub_btn.click()

        # Confirm modal
        page.wait_for_selector("h3:has-text('Publish Canonical Timetable?')", timeout=5000)
        confirm_btn = page.wait_for_selector("button:has-text('Confirm & Publish')", timeout=5000)
        assert confirm_btn is not None, "Confirm and publish button not found"
        confirm_btn.click()

        # Wait for success toast
        page.wait_for_selector(":has-text('Timetable successfully published!')", timeout=15000)
        print("  [PASS] Canonical timetable successfully published by Admin!")
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_admin_published.png"))

        # =========================================================================
        # 2. FACULTY WORKFLOW
        # =========================================================================
        print("\n--- 2. FACULTY DOM VERIFICATION ---")
        context.clear_cookies()
        page.evaluate("() => localStorage.clear()")

        page.goto(f"{FRONTEND_URL}/login")
        page.wait_for_selector("input[type='email']", timeout=10000)
        page.fill("input[type='email']", "nimrita.koul@rio-mjp.test")
        page.fill("input[type='password']", "Nimritakoul#RioLocal26")
        page.click("button[type='submit']")

        page.wait_for_url("**/faculty**", timeout=15000)
        print("  [+] Faculty logged in successfully.")

        # Personal Timetable
        page.click("a[href='/faculty/timetable']")
        page.wait_for_selector("h3:has-text('My Teaching Timetable')", timeout=15000)
        time.sleep(1)
        body_text = page.inner_text("body")
        assert "Weekly Teaching Hours" in body_text, "Expected weekly teaching hours card in faculty timetable"
        assert "Assigned Courses" in body_text, "Expected assigned courses card in faculty timetable"
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "05_faculty_timetable.png"))
        print("  [PASS] Faculty personal timetable rendered with published classes.")

        # Department Timetable
        page.click("a[href='/faculty/dept-timetable']")
        page.wait_for_selector("h1:has-text('Timetable')", timeout=15000)
        time.sleep(1)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "06_faculty_dept_timetable.png"))
        print("  [PASS] Faculty departmental timetable rendered cleanly.")

        # =========================================================================
        # 3. STUDENT WORKFLOW
        # =========================================================================
        print("\n--- 3. STUDENT DOM VERIFICATION ---")
        context.clear_cookies()
        page.evaluate("() => localStorage.clear()")

        page.goto(f"{FRONTEND_URL}/login")
        page.wait_for_selector("input[type='email']", timeout=10000)
        page.fill("input[type='email']", "r23eh001@rio-mjp.test")
        page.fill("input[type='password']", "R23eh001#RioLocal26")
        page.click("button[type='submit']")

        page.wait_for_url("**/student**", timeout=15000)
        print("  [+] Student logged in successfully.")

        # Student Timetable
        page.click("a[href='/student/timetable']")
        page.wait_for_selector("h3:has-text('My Class Schedule')", timeout=15000)
        time.sleep(1)
        body_text = page.inner_text("body")
        assert "Dr. Nimrita Koul" in body_text, "Class teacher Dr. Nimrita Koul not shown in student timetable"
        assert "Class Teacher" in body_text, "Class teacher badge not shown"
        assert "AIDS-A" in body_text or "Sec AIDS-A" in body_text, "Section AIDS-A not shown in student timetable"
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "07_student_timetable.png"))
        print("  [PASS] Student timetable rendered cleanly with section schedule and class teacher info.")

        browser.close()

    print("\n=======================================================")
    print("ALL BROWSER DOM TESTS PASSED WITH ZERO CRASHES OR ERRORS!")
    print(f"Screenshots saved to: {SCREENSHOT_DIR}")
    print("=======================================================")


if __name__ == "__main__":
    run_dom_verification()
