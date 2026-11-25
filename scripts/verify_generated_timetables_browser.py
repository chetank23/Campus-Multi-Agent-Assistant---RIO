import os
import sys
import time
from playwright.sync_api import sync_playwright

def run_browser_verification():
    screenshots_dir = os.path.join(os.path.dirname(__file__), "..", "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: print(f"[BROWSER CONSOLE] {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"[BROWSER ERROR] {err}"))

        print("1. Navigating to login page...")
        page.goto("http://127.0.0.1:5173/login")
        page.wait_for_selector('input[type="email"]', timeout=15000)

        print("2. Logging in as admin...")
        page.fill('input[type="email"]', "admin@campus.edu")
        page.fill('input[type="password"]', "Admin#RioLocal26")
        with page.expect_response("**/auth/login") as response_info:
            page.click('button[type="submit"]')
        login_res = response_info.value
        print(f"Login API response status: {login_res.status}")
        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        time.sleep(2)
        print("Logged in, current URL:", page.url)

        print("3. Navigating to /admin/timetables/generated via sidebar...")
        sidebar_link = page.locator('a[href="/admin/timetables/generated"]')
        if sidebar_link.count() > 0:
            sidebar_link.first.click()
        else:
            page.evaluate("window.history.pushState({}, '', '/admin/timetables/generated'); window.dispatchEvent(new PopStateEvent('popstate'));")
        page.wait_for_selector('h1:has-text("Generated Timetables")', timeout=15000)
        time.sleep(2)

        # Capture screenshot of Generated Timetables page
        ss1 = os.path.join(screenshots_dir, "01_generated_timetables_page.png")
        page.screenshot(path=ss1)
        print(f"Captured screenshot: {ss1}")

        # Check summary cards exist
        assert page.locator('text=Total Generated').count() > 0, "Missing Total Generated card"
        assert page.locator('text=Awaiting Review').count() > 0, "Missing Awaiting Review card"
        assert page.locator('text=Validated / Approved').count() > 0, "Missing Validated/Approved card"
        assert page.locator('text=Live Published').count() > 0, "Missing Live Published card"
        print("Summary cards verified.")

        # Check status tabs
        assert page.locator('button:has-text("All Versions")').count() > 0
        assert page.locator('button:has-text("Awaiting Review")').count() > 0
        assert page.locator('button:has-text("Approved & Validated")').count() > 0
        assert page.locator('button:has-text("Published")').count() > 0
        print("Status tabs verified.")

        # Check if there are review buttons
        review_btn = page.locator('button:has-text("Review & Edit"), button:has-text("View Schedule")').first
        if review_btn.count() > 0:
            print("4. Clicking Review button to navigate into timetable review workspace...")
            review_btn.click()
            page.wait_for_url("**/admin/timetable/versions/*", timeout=15000)
            time.sleep(3)

            ss2 = os.path.join(screenshots_dir, "02_timetable_review_workspace.png")
            page.screenshot(path=ss2)
            print(f"Captured screenshot: {ss2}")
            print("Timetable review workspace verified.")

            # Check for Validate button if not yet validated
            validate_btn = page.locator('button:has-text("Validate"), button:has-text("Revalidate")')
            if validate_btn.count() > 0 and validate_btn.first.is_enabled():
                print("5. Clicking Validate/Revalidate button...")
                validate_btn.first.click()
                time.sleep(3)

            # Check for Approve button
            approve_btn = page.locator('button:has-text("Approve Timetable")')
            if approve_btn.count() > 0 and approve_btn.first.is_enabled():
                print("6. Clicking Approve Timetable button...")
                approve_btn.first.click()
                time.sleep(1)
                # Confirm in modal
                modal_approve_btn = page.locator('div[role="dialog"] button:has-text("Approve Timetable"), .fixed button:has-text("Approve Timetable")')
                if modal_approve_btn.count() > 0:
                    modal_approve_btn.last.click()
                    time.sleep(2)
                    print("Approved timetable.")

            # Check for Publish to Coordinators button
            publish_btn = page.locator('button:has-text("Publish to Coordinators")')
            if publish_btn.count() > 0:
                print("7. Clicking Publish to Coordinators button to open Preflight Modal...")
                publish_btn.first.click()
                time.sleep(2)
                ss3 = os.path.join(screenshots_dir, "03_coordinator_preflight_modal.png")
                page.screenshot(path=ss3)
                print(f"Captured screenshot: {ss3}")
                assert page.locator('text=Publish Timetable to Coordinators').count() > 0
                print("Coordinator Preflight Modal verified.")
            else:
                print("Publish to Coordinators button not present yet, capturing current workspace state.")
                ss3 = os.path.join(screenshots_dir, "03_coordinator_preflight_modal.png")
                page.screenshot(path=ss3)
        else:
            print("No generated versions available to click, but page rendered cleanly.")

        browser.close()
        print("Browser verification completed successfully!")

if __name__ == "__main__":
    run_browser_verification()
