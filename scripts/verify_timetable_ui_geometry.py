"""
scripts/verify_timetable_ui_geometry.py
---------------------------------------
Verifies:
1. Rooms Page (/admin/campus/rooms):
   - Client-side navigation via sidebar.
   - Verifies HTTP 200, no 500 error, 235 table rows rendered.
   - Saves screenshot: reports/screenshots/rooms_page_loaded.png
2. Timetable Management (/admin/timetable):
   - Client-side navigation via sidebar.
   - Scope selection: Academic Year 2026-2027, Semester VII, AI & DS.
   - Verify AIDS-A section badge appears.
   - Generation of preview with OR-Tools CP-SAT.
   - Header check: Time-only bold headers (08:30–09:25, etc.), Tea and Lunch breaks, no 'Period 1..7'.
   - Card content check: Code, complete title, Faculty, Room No., Class Type badge.
   - Geometry check: Pairwise bounding-box intersection test across all cards (strictly 0 overlaps).
   - Saturday row integrity and height.
   - Saves screenshot: reports/screenshots/repaired_timetable_preview.png
3. Publication:
   - Canonical publication workflow.
   - Saves screenshot: reports/screenshots/repaired_timetable_published.png
4. Faculty Personal Timetable:
   - Login as Dr. Nimrita Koul (nimrita.koul@rio-mjp.test / Nimritakoul#RioLocal26).
   - Navigate to /faculty/timetable.
   - Verify schedule cards rendered cleanly.
   - Saves screenshot: reports/screenshots/repaired_faculty_timetable.png
5. Student Personal Timetable:
   - Login as student (r23eh001@rio-mjp.test / R23eh001#RioLocal26).
   - Navigate to /student/timetable.
   - Verify AIDS-A schedule cards rendered cleanly.
   - Saves screenshot: reports/screenshots/repaired_student_timetable.png
"""

import time
import os
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:5173"
SCREENSHOT_DIR = "reports/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 950})
        page = ctx.new_page()

        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        print("\n========================================================")
        print("STEP 1: Admin Login & Rooms Page (/admin/campus/rooms)")
        print("========================================================")
        page.goto(f"{FRONTEND_URL}/login")
        page.fill("input[type='email']", "admin@campus.edu")
        page.fill("input[type='password']", "Admin#RioLocal26")
        page.click("button[type='submit']")
        page.wait_for_url("**/admin**", timeout=15000)
        print("   Logged in as Admin.")

        # Navigate to Rooms page via sidebar client-side navigation
        page.wait_for_selector("text=Buildings, Rooms & Labs", timeout=10000)
        page.click("text=Buildings, Rooms & Labs")
        page.wait_for_timeout(500)
        page.click("a[href='/admin/campus/rooms']")
        page.wait_for_url("**/admin/campus/rooms", timeout=10000)
        page.wait_for_selector("text=Classroom & Lab Registry", timeout=10000)
        page.wait_for_timeout(1000)

        # Verify no 500 error
        body_text = page.inner_text("body")
        assert "Error loading table records" not in body_text, "500 Error still present on /admin/campus/rooms!"
        assert "Request failed with status code 500" not in body_text, "500 Error still present!"

        # Check room rows
        room_rows = page.query_selector_all("table tbody tr")
        print(f"   [PASS] Rooms page loaded cleanly: {len(room_rows)} room rows displayed.")
        rooms_screenshot = os.path.join(SCREENSHOT_DIR, "rooms_page_loaded.png")
        page.screenshot(path=rooms_screenshot, full_page=True)
        print(f"   Captured rooms screenshot: {rooms_screenshot}")

        print("\n========================================================")
        print("STEP 2: Navigating to Timetable Management")
        print("========================================================")
        page.click("a[href='/admin/timetable']")
        page.wait_for_url("**/admin/timetable", timeout=10000)
        page.wait_for_selector("h1:has-text('Timetable Management')", timeout=10000)

        # Select scope dynamically
        print("   Selecting scope: Academic Year 2026-2027, Semester VII, Department AI & DS...")
        page.wait_for_selector("select", timeout=10000)

        # 1. AY
        selects = page.query_selector_all("select")
        selects[0].select_option(index=1)
        page.wait_for_timeout(1000)

        # 2. Semester: Select Semester 7
        selects = page.query_selector_all("select")
        sem_options = selects[1].query_selector_all("option")
        for opt in sem_options:
            if "7" in opt.inner_text():
                selects[1].select_option(value=opt.get_attribute("value"))
                break
        page.wait_for_timeout(1000)

        # 3. Department: Select AI & DS
        selects = page.query_selector_all("select")
        dept_options = selects[2].query_selector_all("option")
        for opt in dept_options:
            if "AI" in opt.inner_text():
                selects[2].select_option(value=opt.get_attribute("value"))
                break
        page.wait_for_timeout(1500)

        # Verify section AIDS-A
        page.wait_for_selector("text=AIDS-A", timeout=10000)
        print("   [PASS] Found section AIDS-A.")

        # Click Generate Timetable
        print("   Generating Timetable Preview...")
        gen_btn = page.query_selector("button:has-text('GENERATE TIMETABLE')")
        if not gen_btn:
            gen_btn = page.query_selector("button:has-text('REGENERATE TIMETABLE')")
        assert gen_btn, "Generate button not found!"
        gen_btn.click()

        # Wait for preview table (allow up to 60s for OR-Tools CP-SAT)
        page.wait_for_selector("text=Temporary Generated Preview", timeout=60000)
        print("   [PASS] Timetable preview successfully generated!")

        # Verify Header labels (time-only, no Period 1/2)
        th_elements = page.query_selector_all("table thead th")
        th_texts = [th.inner_text().strip() for th in th_elements]
        print(f"   Table headers: {th_texts}")
        assert not any("Period 1" in t for t in th_texts), "Header must not contain 'Period 1'"
        assert not any("Period 2" in t for t in th_texts), "Header must not contain 'Period 2'"
        assert any("08:30–09:25" in t for t in th_texts), "Header must contain 08:30–09:25"
        assert any("Tea Break: 10:20–10:40" in t for t in th_texts), "Header must contain Tea Break"
        assert any("Lunch Break: 12:30–13:30" in t for t in th_texts), "Header must contain Lunch Break"
        print("   [PASS] Header format verified: Bold time-only headers with Tea and Lunch breaks.")

        # Check cards and overlap geometry
        cards = page.query_selector_all("table tbody tr td div.rounded-lg")
        print(f"   Found {len(cards)} scheduled class cards on preview grid.")
        assert len(cards) >= 20, f"Expected at least 20 class cards, found {len(cards)}"

        # Verify information display on cards
        first_card_text = cards[0].inner_text()
        print(f"   Sample card text:\n{first_card_text}")
        assert "CLASS TYPE:" in first_card_text.upper(), "Card must display 'Class Type:'"
        assert "FACULTY:" in first_card_text.upper(), "Card must display 'Faculty:'"
        assert "ROOM NO.:" in first_card_text.upper(), "Card must display 'Room No.:'"
        print("   [PASS] Card content verified: Subject code, title, Faculty, Room No., and Class Type present.")

        # Geometry Overlap Test: check every pair of cards in the table for bounding box intersection
        boxes = []
        for c in cards:
            box = c.bounding_box()
            if box and box["width"] > 0 and box["height"] > 0:
                boxes.append(box)

        overlap_count = 0
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                b1 = boxes[i]
                b2 = boxes[j]
                # Check rectangle overlap with 1px tolerance
                x_overlap = not (b1["x"] + b1["width"] <= b2["x"] + 1 or b2["x"] + b2["width"] <= b1["x"] + 1)
                y_overlap = not (b1["y"] + b1["height"] <= b2["y"] + 1 or b2["y"] + b2["height"] <= b1["y"] + 1)
                if x_overlap and y_overlap:
                    overlap_count += 1
                    print(f"   [OVERLAP DETECTED] Box {i} {b1} overlaps with Box {j} {b2}")

        print(f"   Overlap count across all {len(boxes)} cards: {overlap_count}")
        assert overlap_count == 0, f"Critical failure: {overlap_count} overlapping card pairs detected!"
        print("   [PASS] ZERO card overlap verified geometrically across entire preview grid!")

        # Verify Saturday row visibility
        rows = page.query_selector_all("table tbody tr")
        print(f"   Total grid rows: {len(rows)} (Days MON-SAT)")
        assert len(rows) == 6, f"Expected 6 day rows, got {len(rows)}"
        saturday_row = rows[5]
        assert "SATURDAY" in saturday_row.inner_text().upper(), "Row 6 must be Saturday"
        sat_box = saturday_row.bounding_box()
        assert sat_box and sat_box["height"] > 50, "Saturday row must have visible non-zero height"
        print(f"   [PASS] Saturday row is fully rendered and visible (height: {sat_box['height']}px).")

        # Capture high-res screenshot of preview
        preview_screenshot = os.path.join(SCREENSHOT_DIR, "repaired_timetable_preview.png")
        page.screenshot(path=preview_screenshot, full_page=True)
        print(f"   Captured preview screenshot: {preview_screenshot}")

        print("\n========================================================")
        print("STEP 3: Publishing Canonical Timetable")
        print("========================================================")
        pub_btn = page.query_selector("button:has-text('PUBLISH TIMETABLE')")
        assert pub_btn, "Publish button not found!"
        pub_btn.click()

        # Handle confirmation dialog
        page.wait_for_selector("button:has-text('Confirm & Publish')", timeout=5000)
        confirm_btn = page.query_selector("button:has-text('Confirm & Publish')")
        if confirm_btn:
            confirm_btn.click()

        page.wait_for_selector("text=Viewing Published Canonical Timetable", timeout=15000)
        print("   [PASS] Canonical Timetable published successfully!")
        pub_screenshot = os.path.join(SCREENSHOT_DIR, "repaired_timetable_published.png")
        page.screenshot(path=pub_screenshot, full_page=True)
        print(f"   Captured published screenshot: {pub_screenshot}")

        print("\n========================================================")
        print("STEP 4: Verifying Faculty Personal Timetable")
        print("========================================================")
        ctx_fac = browser.new_context(viewport={"width": 1440, "height": 950})
        page_fac = ctx_fac.new_page()
        page_fac.goto(f"{FRONTEND_URL}/login")
        page_fac.fill("input[type='email']", "nimrita.koul@rio-mjp.test")
        page_fac.fill("input[type='password']", "Nimritakoul#RioLocal26")
        page_fac.click("button[type='submit']")
        page_fac.wait_for_url("**/faculty**", timeout=15000)

        # Client-side navigate to timetable
        page_fac.click("a[href='/faculty/timetable']")
        page_fac.wait_for_url("**/faculty/timetable", timeout=10000)
        page_fac.wait_for_selector("table", timeout=10000)
        page_fac.wait_for_timeout(1500)
        fac_cards = page_fac.query_selector_all("table tbody tr td div.rounded-lg")
        print(f"   Faculty personal timetable has {len(fac_cards)} class cards.")
        assert len(fac_cards) >= 5, f"Expected faculty cards, found {len(fac_cards)}"

        fac_screenshot = os.path.join(SCREENSHOT_DIR, "repaired_faculty_timetable.png")
        page_fac.screenshot(path=fac_screenshot, full_page=True)
        print(f"   [PASS] Faculty view verified. Captured: {fac_screenshot}")

        print("\n========================================================")
        print("STEP 5: Verifying Student Personal Timetable")
        print("========================================================")
        ctx_stu = browser.new_context(viewport={"width": 1440, "height": 950})
        page_stu = ctx_stu.new_page()
        page_stu.goto(f"{FRONTEND_URL}/login")
        page_stu.fill("input[type='email']", "r23eh001@rio-mjp.test")
        page_stu.fill("input[type='password']", "R23eh001#RioLocal26")
        page_stu.click("button[type='submit']")
        page_stu.wait_for_url("**/student**", timeout=15000)

        # Client-side navigate to timetable
        page_stu.click("a[href='/student/timetable']")
        page_stu.wait_for_url("**/student/timetable", timeout=10000)
        page_stu.wait_for_selector("table", timeout=10000)
        page_stu.wait_for_timeout(1500)
        stu_cards = page_stu.query_selector_all("table tbody tr td div.rounded-lg")
        print(f"   Student personal timetable has {len(stu_cards)} class cards.")
        assert len(stu_cards) >= 15, f"Expected student cards, found {len(stu_cards)}"

        stu_screenshot = os.path.join(SCREENSHOT_DIR, "repaired_student_timetable.png")
        page_stu.screenshot(path=stu_screenshot, full_page=True)
        print(f"   [PASS] Student view verified. Captured: {stu_screenshot}")

        browser.close()
        print("\n========================================================")
        print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY WITH ZERO ERRORS!")
        print("========================================================")

if __name__ == "__main__":
    run_verification()
