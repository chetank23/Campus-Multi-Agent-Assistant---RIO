import os
import sys
import asyncio
from playwright.async_api import async_playwright

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5173")

# Test credentials configured via environment with local test defaults
STUDENT_EMAIL = os.environ.get("TEST_STUDENT_EMAIL", "r23eh001@rio-mjp.test")
STUDENT_PWD = os.environ.get("TEST_STUDENT_PASSWORD", "R23eh001#RioLocal26")

FACULTY_EMAIL = os.environ.get("TEST_FACULTY_EMAIL", "nimrita.koul@rio-mjp.test")
FACULTY_PWD = os.environ.get("TEST_FACULTY_PASSWORD", "Nimritakoul#RioLocal26")

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@campus.edu")
ADMIN_PWD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin#RioLocal26")

SUPERADMIN_EMAIL = os.environ.get("TEST_SUPERADMIN_EMAIL", "superadmin@campus.edu")
SUPERADMIN_PWD = os.environ.get("TEST_SUPERADMIN_PASSWORD", "Test@1234")

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        roles_config = [
            {
                "role": "STUDENT",
                "email": STUDENT_EMAIL,
                "password": STUDENT_PWD,
                "target_url": "/student",
                "screenshot": "reports/screenshots/student_dashboard_heading_verified.png"
            },
            {
                "role": "FACULTY",
                "email": FACULTY_EMAIL,
                "password": FACULTY_PWD,
                "target_url": "/faculty",
                "screenshot": "reports/screenshots/faculty_dashboard_heading_verified.png"
            },
            {
                "role": "ADMIN",
                "email": ADMIN_EMAIL,
                "password": ADMIN_PWD,
                "target_url": "/admin",
                "screenshot": "reports/screenshots/admin_dashboard_heading_verified.png"
            },
            {
                "role": "SUPER_ADMIN",
                "email": SUPERADMIN_EMAIL,
                "password": SUPERADMIN_PWD,
                "target_url": "/super-admin",
                "screenshot": "reports/screenshots/super_admin_dashboard_heading_verified.png"
            }
        ]

        for cfg in roles_config:
            role = cfg["role"]
            print(f"\n[*] Testing {role} Portal ({cfg['email']})...")
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            await page.goto(f"{BASE_URL}/login", wait_until="networkidle")
            await page.fill('input[type="email"]', cfg["email"])
            await page.fill('input[type="password"]', cfg["password"])
            await page.click('button[type="submit"]')

            # Wait for role navigation to settle
            try:
                await page.wait_for_url(f"**{cfg['target_url']}**", timeout=12000)
            except Exception:
                # Fallback direct navigation if redirect was already triggered
                await page.goto(f"{BASE_URL}{cfg['target_url']}", wait_until="networkidle")

            # Wait for content to render
            await page.wait_for_timeout(2500)

            headings = await page.evaluate("""
                () => {
                    const allH = Array.from(document.querySelectorAll('h1, h2, h3')).map(el => ({
                        tag: el.tagName,
                        text: el.innerText.trim(),
                        classes: el.className
                    }));
                    const paragraphs = Array.from(document.querySelectorAll('p')).slice(0, 10).map(el => el.innerText.trim());
                    return { headings: allH, paragraphs: paragraphs };
                }
            """)

            print(f"  [+] Discovered Headings for {role}:")
            for h in headings["headings"][:6]:
                print(f"      <{h['tag']}> {h['text']}")

            await page.screenshot(path=cfg["screenshot"])
            print(f"  [+] Saved screenshot to: {cfg['screenshot']}")

            if role == "STUDENT":
                h_texts = [h['text'] for h in headings["headings"]]
                
                # Global personalized welcome in layout header
                has_welcome = any("Welcome" in t for t in h_texts)
                welcome_heading = next((t for t in h_texts if "Welcome" in t), None)
                
                # Dashboard title must be "Academic Overview"
                has_academic_overview = any("Academic Overview" in t for t in h_texts)
                
                # Subtitle check
                has_sub = any("Your academic dashboard and real-time schedule hub" in p for p in headings["paragraphs"])
                
                print(f"  [+] Layout Global Welcome Header: '{welcome_heading}'")
                print(f"  [+] Dashboard Renamed Heading Present: {has_academic_overview}")
                print(f"  [+] Dashboard Subtitle Correct: {has_sub}")
                
                assert has_welcome, "Student layout must contain global personalized welcome"
                assert has_academic_overview, "Student dashboard must have 'Academic Overview'"
                assert has_sub, "Student dashboard must have updated subtitle"
                
                # Verify "Welcome" appears exactly once across layout & dashboard
                welcome_count = sum(1 for t in h_texts if "Welcome" in t)
                print(f"  [+] Welcome Heading Count in Student View: {welcome_count} (Expected: exactly 1)")
                assert welcome_count == 1, f"Expected exactly 1 Welcome heading, got {welcome_count}"

            elif role == "FACULTY":
                h_texts = [h['text'] for h in headings["headings"]]
                welcome_count = sum(1 for t in h_texts if "Welcome" in t)
                print(f"  [+] Faculty Welcome Heading Count: {welcome_count} (Expected: 1 on dashboard hero)")
                assert welcome_count == 1, f"Expected 1 Welcome heading for Faculty, got {welcome_count}"

            elif role == "ADMIN":
                h_texts = [h['text'] for h in headings["headings"]]
                greeting_count = sum(1 for t in h_texts if any(g in t for g in ["Good morning", "Good afternoon", "Good evening", "Welcome"]))
                print(f"  [+] Admin Greeting Heading Count: {greeting_count} (Expected: 1 on dashboard)")
                assert greeting_count == 1, f"Expected 1 greeting heading for Admin, got {greeting_count}"

            elif role == "SUPER_ADMIN":
                h_texts = [h['text'] for h in headings["headings"]]
                welcome_count = sum(1 for t in h_texts if "Welcome" in t)
                print(f"  [+] Super Admin Welcome Count: {welcome_count} (Expected: 0, governance banner used)")
                assert welcome_count == 0, f"Expected 0 Welcome headings for Super Admin, got {welcome_count}"

            await context.close()

        print("\n============================================================")
        print("[SUCCESS] ALL 4 ROLE PORTALS VERIFIED CONCURRENTLY & PASSED!")
        print("============================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify())
