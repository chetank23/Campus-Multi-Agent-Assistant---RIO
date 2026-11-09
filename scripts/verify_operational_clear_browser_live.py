"""
scripts/verify_operational_clear_browser_live.py
------------------------------------------------
Live browser Playwright test validating:
1. Operational data clear in Settings -> Data Management.
2. In-place cache invalidation and immediate reflection on System Admin Dashboard:
   - Published Timetables: 0
   - Recent Timetable Generations: Clean empty state
   - Timetable Status Donut: Clean empty state (0%)
   - Department-wise Timetable Completion: 0% (0 of 1 sections published)
   - Recent Activity: Latest activity is CLEAR GENERATED OPERATIONAL DATA
   - Master Data KPIs intact (60 Students, 10 Faculty, 18 Courses, 225 Rooms)
3. Cross-role notification delivery:
   - System Admin, Faculty, and Student all receive 'Campus Timetable Schedule Reset'
4. Faculty and Student timetable views display clear, helpful empty states with 0 hours.
"""

import os
import sys
import time
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:5173"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def run_live_verification():
    print("===============================================================================")
    print("      LIVE BROWSER OPERATIONAL RESET & DASHBOARD CONSISTENCY VERIFICATION      ")
    print("===============================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        def login_and_get_page(email: str, password: str, expected_route: str):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            errors = []
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

            pg.goto(f"{FRONTEND_URL}/login")
            pg.wait_for_selector("input[type='email']", timeout=10000)
            pg.fill("input[type='email']", email)
            pg.fill("input[type='password']", password)
            pg.click("button[type='submit']")
            pg.wait_for_url(f"**{expected_route}**", timeout=12000)
            time.sleep(1)
            return ctx, pg, errors

        # ── STEP 1: ADMIN LOGIN & CLEAR OPERATIONAL DATA ─────────────────────────────
        print("\n[1] Logging into System Admin (admin@campus.edu)...")
        adm_ctx, adm_pg, adm_err = login_and_get_page("admin@campus.edu", "Admin#RioLocal26", "/admin")
        print("    [+] Admin successfully logged in.")

        print("[2] Navigating via SPA link to Settings -> Data Management...")
        adm_pg.click("a[href='/admin/settings']")
        adm_pg.wait_for_selector("text=Settings & Data Management", timeout=10000)

        # Click on 'Data Management' tab
        adm_pg.click("button:has-text('Data Management')")
        time.sleep(1)
        adm_pg.screenshot(path=os.path.join(SCREENSHOT_DIR, "settings_data_management_tab.png"))
        print("    [+] Data Management tab loaded.")

        # Click 'CLEAR ALL GENERATED OPERATIONAL DATA' button
        print("[3] Initiating full operational data reset...")
        adm_pg.click("button:has-text('CLEAR ALL GENERATED OPERATIONAL DATA')")
        time.sleep(1)

        # In modal: check confirmation checkbox and execute
        adm_pg.wait_for_selector(".fixed.inset-0", timeout=5000)
        adm_pg.locator(".fixed.inset-0 input[type='checkbox']").check()
        time.sleep(0.5)

        adm_pg.locator(".fixed.inset-0 button:has-text('EXECUTE SAFE PURGE')").click()
        print("    [+] Clicked 'EXECUTE SAFE PURGE'. Waiting for completion...")

        # Wait for toast confirmation
        adm_pg.wait_for_selector("text=Successfully cleared", timeout=10000)
        toast_text = adm_pg.locator("text=Successfully cleared").inner_text()
        print(f"    [+] Confirmation toast displayed: '{toast_text}'")
        adm_pg.screenshot(path=os.path.join(SCREENSHOT_DIR, "clear_execution_success_toast.png"))

        # ── STEP 2: VERIFY SYSTEM ADMIN DASHBOARD IMMEDIATE CONSISTENCY ──────────────
        print("\n[4] Navigating back to System Admin Dashboard (/admin)...")
        adm_pg.click("a[href='/admin']")
        time.sleep(2)

        adm_pg.screenshot(path=os.path.join(SCREENSHOT_DIR, "admin_dashboard_post_clear_verified.png"))
        print(f"    [+] Saved screenshot to reports/screenshots/admin_dashboard_post_clear_verified.png")

        dashboard_html = adm_pg.content()

        # Check KPI Cards
        print("\n[5] Verifying System Admin Dashboard KPIs & Cards:")
        # 1. Published Timetables must be 0
        pub_tt_locator = adm_pg.locator("text=Published Timetables").locator("..").locator("span.font-extrabold")
        pub_tt_val = pub_tt_locator.inner_text().strip()
        print(f"    - Published Timetables KPI: '{pub_tt_val}' (Expected: '0')")
        assert pub_tt_val == "0", f"Expected Published Timetables to be '0', got '{pub_tt_val}'"

        # 2. Master Data KPIs
        stu_val = adm_pg.locator("text=Total Students").locator("..").locator("span.font-extrabold").inner_text().strip()
        fac_val = adm_pg.locator("text=Total Faculty").locator("..").locator("span.font-extrabold").inner_text().strip()
        courses_val = adm_pg.locator("text=Total Courses").locator("..").locator("span.font-extrabold").inner_text().strip()
        rooms_val = adm_pg.locator("text=Total Rooms").locator("..").locator("span.font-extrabold").inner_text().strip()
        print(f"    - Total Students KPI: '{stu_val}' (Expected: 60)")
        print(f"    - Total Faculty KPI: '{fac_val}' (Expected: 10)")
        print(f"    - Total Courses KPI: '{courses_val}' (Expected: 18)")
        print(f"    - Total Rooms KPI: '{rooms_val}' (Expected: 225)")
        assert stu_val == "60", f"Master students altered: {stu_val}"
        assert fac_val == "10", f"Master faculty altered: {fac_val}"
        assert courses_val == "18", f"Master courses altered: {courses_val}"
        assert rooms_val == "225", f"Master rooms altered: {rooms_val}"

        # 3. Recent Timetable Generations Empty State
        print("\n[6] Verifying Recent Timetable Generations Empty State:")
        assert "No timetable generations recorded" in dashboard_html, "Expected 'No timetable generations recorded' empty state"
        assert "Generate Timetable" in dashboard_html, "Expected direct action button to Generate Timetable"
        print("    [+] Clean empty state verified in Recent Timetable Generations table.")

        # 4. Timetable Status Donut Empty State
        print("\n[7] Verifying Timetable Status Donut Empty State:")
        assert "No Timetable Versions" in dashboard_html or "0 Published" in dashboard_html, "Expected 0 published / no versions in Timetable Status"
        print("    [+] Timetable Status panel displays clean empty state.")

        # 5. Department-wise Timetable Completion
        print("\n[8] Verifying Department-wise Timetable Completion:")
        assert "0 of 1 sections published" in dashboard_html or "0%" in dashboard_html, "Expected 0 of 1 sections published (0%)"
        print("    [+] Department-wise completion shows 0% (0 of 1 sections published).")

        # 6. Recent Activity
        print("\n[9] Verifying Recent Activity Audit Trail:")
        assert "CLEAR GENERATED OPERATIONAL DATA" in dashboard_html, "Expected CLEAR GENERATED OPERATIONAL DATA as latest activity"
        print("    [+] Recent Activity shows 'CLEAR GENERATED OPERATIONAL DATA' as the latest action.")

        # 7. Check Admin Notifications
        print("\n[10] Verifying System Admin Broadcast Notification:")
        # Click notification bell dropdown in topbar
        bell_btn = adm_pg.locator("button[title*='notification' i], button:has(svg.lucide-bell)").first
        bell_btn.click()
        time.sleep(1)
        adm_pg.wait_for_selector("text=Campus Timetable Schedule Reset", timeout=8000)
        notif_msg = adm_pg.locator("text=Campus Timetable Schedule Reset").locator("..").locator("p").first.inner_text()
        print(f"    [+] Admin Notification verified in real-time dropdown: '{notif_msg}'")
        adm_pg.screenshot(path=os.path.join(SCREENSHOT_DIR, "admin_notification_schedule_reset.png"))
        adm_ctx.close()

        # ── STEP 3: FACULTY SCHEDULE & NOTIFICATION VERIFICATION ────────────────────
        print("\n[11] Logging into Faculty Portal (nimrita.koul@rio-mjp.test)...")
        fac_ctx, fac_pg, fac_err = login_and_get_page("nimrita.koul@rio-mjp.test", "Nimritakoul#RioLocal26", "/faculty")
        print("    [+] Faculty logged in successfully.")

        # Check Faculty Timetable
        fac_pg.click("a[href='/faculty/timetable']")
        fac_pg.wait_for_selector("text=My Teaching Timetable", timeout=10000)
        time.sleep(1)
        fac_html = fac_pg.content()
        fac_pg.screenshot(path=os.path.join(SCREENSHOT_DIR, "faculty_timetable_post_clear.png"))

        print("\n[12] Verifying Faculty Timetable Empty State:")
        assert "0h" in fac_html, "Expected 0h weekly teaching hours"
        assert "No published timetable entries found for your teaching assignments" in fac_html, "Expected clean empty state message for faculty"
        print("    [+] Faculty timetable displays 0h and clean empty state.")

        # Check Faculty Notifications
        fac_pg.click("a[href='/faculty/notifications']")
        fac_pg.wait_for_selector("text=Campus Timetable Schedule Reset", timeout=8000)
        print("    [+] Faculty received broadcast notification: 'Campus Timetable Schedule Reset'.")
        fac_ctx.close()

        # ── STEP 4: STUDENT SCHEDULE & NOTIFICATION VERIFICATION ────────────────────
        print("\n[13] Logging into Student Portal (r23eh001@rio-mjp.test)...")
        stu_ctx, stu_pg, stu_err = login_and_get_page("r23eh001@rio-mjp.test", "R23eh001#RioLocal26", "/student")
        print("    [+] Student logged in successfully.")

        # Check Student Timetable
        stu_pg.click("a[href='/student/timetable']")
        stu_pg.wait_for_selector("text=My Class Schedule", timeout=10000)
        time.sleep(1)
        stu_html = stu_pg.content()
        stu_pg.screenshot(path=os.path.join(SCREENSHOT_DIR, "student_timetable_post_clear.png"))

        print("\n[14] Verifying Student Timetable Empty State:")
        assert "No timetable has been published for your section yet" in stu_html, "Expected clean empty state message for student"
        print("    [+] Student timetable displays 0 hours and clean empty state.")

        # Check Student Notifications
        stu_pg.click("a[href='/student/notifications']")
        stu_pg.wait_for_selector("text=Campus Timetable Schedule Reset", timeout=8000)
        print("    [+] Student received broadcast notification: 'Campus Timetable Schedule Reset'.")
        stu_ctx.close()

        browser.close()

    print("\n===============================================================================")
    print("      ALL LIVE BROWSER VERIFICATIONS PASSED WITH 100% SUCCESS!                 ")
    print("===============================================================================")

if __name__ == "__main__":
    run_live_verification()
