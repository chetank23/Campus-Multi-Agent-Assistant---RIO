import os
import sys
import time
from playwright.sync_api import sync_playwright

def verify_sidebar_and_navigation():
    screenshots_dir = os.path.join(os.path.dirname(__file__), "..", "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: print(f"[CONSOLE] {msg.type}: {msg.text}"))

        print("1. Logging in as admin...")
        page.goto("http://127.0.0.1:5173/login")
        page.wait_for_selector('input[type="email"]', timeout=15000)
        page.fill('input[type="email"]', "admin@campus.edu")
        page.fill('input[type="password"]', "Admin#RioLocal26")

        with page.expect_response("**/auth/login") as res_info:
            page.click('button[type="submit"]')
        assert res_info.value.status == 200, f"Login failed: {res_info.value.status}"

        page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        time.sleep(2)
        print("Logged in, current URL:", page.url)

        print("2. Verifying sidebar ordering...")
        # Get all navigation links in the sidebar
        nav_links = page.locator('aside nav a')
        count = nav_links.count()
        print(f"Total sidebar links: {count}")

        # The first link is Dashboard
        link0 = nav_links.nth(0)
        link0_text = link0.inner_text().strip()
        link0_href = link0.get_attribute("href")
        print(f"Option 1: '{link0_text}' -> href: {link0_href}")
        assert "Dashboard" in link0_text, f"Expected Dashboard, got: {link0_text}"
        assert link0_href == "/admin"

        # The second link must be Timetable Generation
        link1 = nav_links.nth(1)
        link1_text = link1.inner_text().strip()
        link1_href = link1.get_attribute("href")
        print(f"Option 2: '{link1_text}' -> href: {link1_href}")
        assert "Timetable Generation" in link1_text, f"Expected Timetable Generation, got: {link1_text}"
        assert link1_href == "/admin/timetable"

        # The third link must be Generated Timetables
        link2 = nav_links.nth(2)
        link2_text = link2.inner_text().strip()
        link2_href = link2.get_attribute("href")
        print(f"Option 3: '{link2_text}' -> href: {link2_href}")
        assert "Generated Timetables" in link2_text, f"Expected Generated Timetables, got: {link2_text}"
        assert link2_href == "/admin/timetables/generated"

        # Capture screenshot of sidebar top order
        ss_order = os.path.join(screenshots_dir, "04_sidebar_order_top.png")
        page.screenshot(path=ss_order)
        print(f"Saved screenshot: {ss_order}")

        print("3. Testing navigation to Timetable Generation...")
        link1.click()
        page.wait_for_url("**/admin/timetable", timeout=15000)
        time.sleep(1)
        print("URL is now:", page.url)

        # Check active class on Timetable Generation
        link1_class = link1.get_attribute("class") or ""
        link2_class = link2.get_attribute("class") or ""
        assert "bg-[#1D61E7]" in link1_class, "Timetable Generation should be active"
        assert "bg-[#1D61E7]" not in link2_class, "Generated Timetables should not be active"
        print("Active state verified for Timetable Generation.")

        ss_gen = os.path.join(screenshots_dir, "05_timetable_generation_active.png")
        page.screenshot(path=ss_gen)
        print(f"Saved screenshot: {ss_gen}")

        print("4. Testing navigation to Generated Timetables...")
        link2.click()
        page.wait_for_url("**/admin/timetables/generated", timeout=15000)
        time.sleep(1)
        print("URL is now:", page.url)

        # Check active class on Generated Timetables
        link1_class = link1.get_attribute("class") or ""
        link2_class = link2.get_attribute("class") or ""
        assert "bg-[#1D61E7]" not in link1_class, "Timetable Generation should not be active"
        assert "bg-[#1D61E7]" in link2_class, "Generated Timetables should be active"
        print("Active state verified for Generated Timetables.")

        ss_gen_tt = os.path.join(screenshots_dir, "06_generated_timetables_active.png")
        page.screenshot(path=ss_gen_tt)
        print(f"Saved screenshot: {ss_gen_tt}")

        print("5. Testing collapsed sidebar behavior...")
        collapse_btn = page.locator('button[aria-label="Collapse sidebar"]')
        if collapse_btn.count() > 0:
            collapse_btn.click()
            time.sleep(1)
            ss_collapsed = os.path.join(screenshots_dir, "07_sidebar_collapsed.png")
            page.screenshot(path=ss_collapsed)
            print(f"Saved screenshot: {ss_collapsed}")
            print("Collapsed sidebar verified.")

        browser.close()
        print("All sidebar prioritization tests PASSED!")

if __name__ == "__main__":
    verify_sidebar_and_navigation()
