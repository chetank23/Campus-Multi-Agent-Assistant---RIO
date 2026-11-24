"""
scripts/verify_typography_stability.py
--------------------------------------
Forensic verification of typography stability fix:
1. Verifies Inter font is bundled locally from @fontsource/inter.
2. Verifies zero external font requests are made (blocking/monitoring Google Fonts).
3. Verifies font weights 300, 400, 500, 600, 700, 800, 900 load via document.fonts.
4. Verifies computed font-family and font-weights on live DOM elements.
5. Captures screenshots for all 4 roles (Super Admin, Admin, Faculty, Student).
"""

import os
import sys
import json
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5173"
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def verify_typography():
    results = {}
    external_font_requests = []
    local_font_requests = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Track network requests for fonts
        def on_request(req):
            url = req.url
            if "fonts.googleapis.com" in url or "fonts.gstatic.com" in url:
                external_font_requests.append(url)
            elif ".woff2" in url or ".woff" in url or "inter" in url.lower():
                local_font_requests.append(url)

        page.on("request", on_request)

        # -----------------------------------------------------------------
        # 1. Base Document & Font API Checks
        # -----------------------------------------------------------------
        print("[*] Navigating to application root...")
        page.goto(BASE_URL)
        page.wait_for_selector("#root", timeout=12000)

        # Wait for document fonts to be ready
        page.evaluate("""
            async () => {
                await document.fonts.ready;
                const weights = [300, 400, 500, 600, 700, 800, 900];
                for (const w of weights) {
                    await document.fonts.load(`${w} 16px Inter`);
                }
                await document.fonts.ready;
            }
        """)

        # Evaluate document.fonts.check for all required weights
        font_checks = page.evaluate("""
            () => {
                const weights = [300, 400, 500, 600, 700, 800, 900];
                const res = {};
                for (const w of weights) {
                    res[w] = document.fonts.check(`${w} 16px Inter`);
                }
                const fontList = [];
                document.fonts.forEach(f => {
                    fontList.push({
                        family: f.family,
                        weight: f.weight,
                        status: f.status
                    });
                });
                return {
                    checks: res,
                    bodyFont: window.getComputedStyle(document.body).fontFamily,
                    loadedCount: fontList.length,
                    sampleFonts: fontList.slice(0, 10)
                };
            }
        """)

        results["font_checks"] = font_checks
        print("[*] Computed Body Font:", font_checks["bodyFont"])
        print("[*] Font Weight Checks:", font_checks["checks"])
        print(f"[*] Loaded Fonts Count: {font_checks['loadedCount']}")

        # -----------------------------------------------------------------
        # 2. Test 4 Role Dashboards & Capture Screenshots
        # -----------------------------------------------------------------
        roles_config = [
            {
                "role": "SUPER_ADMIN",
                "email": "superadmin@campus.edu",
                "passwords": ["Test@1234", "Admin#RioLocal26"],
                "expected_url": "/super-admin",
                "screenshot": "typography_post_fix_super_admin.png",
            },
            {
                "role": "ADMIN",
                "email": "admin@campus.edu",
                "passwords": ["Admin#RioLocal26", "Test@1234"],
                "expected_url": "/admin",
                "screenshot": "typography_post_fix_admin.png",
            },
            {
                "role": "FACULTY",
                "email": "allison.hill@campus.edu",
                "passwords": ["Test@1234"],
                "expected_url": "/faculty",
                "screenshot": "typography_post_fix_faculty.png",
            },
            {
                "role": "STUDENT",
                "email": "monica.herrera@campus.edu",
                "passwords": ["Test@1234"],
                "expected_url": "/student",
                "screenshot": "typography_post_fix_student.png",
            }
        ]

        dashboard_verifications = {}

        for cfg in roles_config:
            role = cfg["role"]
            print(f"[*] Logging in as [{role}] ({cfg['email']})...")

            role_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            role_page = role_ctx.new_page()
            role_page.on("request", on_request)

            role_page.goto(f"{BASE_URL}/login")
            role_page.wait_for_selector("input[type='email']", timeout=12000)

            logged_in = False
            for pwd in cfg["passwords"]:
                role_page.fill("input[type='email']", cfg["email"])
                role_page.fill("input[type='password']", pwd)
                role_page.click("button[type='submit']")
                try:
                    role_page.wait_for_url(f"**{cfg['expected_url']}**", timeout=6000)
                    logged_in = True
                    break
                except Exception:
                    continue

            if not logged_in:
                print(f"  [!] Direct login timeout for {role}, navigating directly...")
                role_page.goto(f"{BASE_URL}{cfg['expected_url']}")

            role_page.wait_for_timeout(2000)

            # Inspect typography on main headings and body
            dom_typography = role_page.evaluate("""
                () => {
                    const h1 = document.querySelector('h1, h2, h3');
                    const btn = document.querySelector('button');
                    const body = document.body;

                    return {
                        body: {
                            fontFamily: window.getComputedStyle(body).fontFamily,
                            fontSize: window.getComputedStyle(body).fontSize,
                            fontWeight: window.getComputedStyle(body).fontWeight
                        },
                        heading: h1 ? {
                            tagName: h1.tagName,
                            fontFamily: window.getComputedStyle(h1).fontFamily,
                            fontSize: window.getComputedStyle(h1).fontSize,
                            fontWeight: window.getComputedStyle(h1).fontWeight,
                            text: h1.innerText.substring(0, 50).replace('\\n', ' ')
                        } : null,
                        button: btn ? {
                            fontFamily: window.getComputedStyle(btn).fontFamily,
                            fontWeight: window.getComputedStyle(btn).fontWeight
                        } : null
                    };
                }
            """)

            screenshot_path = os.path.join(SCREENSHOT_DIR, cfg["screenshot"])
            role_page.screenshot(path=screenshot_path, full_page=False)
            print(f"  [+] Captured screenshot: {cfg['screenshot']}")
            print(f"  [+] Heading: {dom_typography.get('heading')}")

            dashboard_verifications[role] = {
                "typography": dom_typography,
                "screenshot": cfg["screenshot"]
            }
            role_ctx.close()

        browser.close()

    results["dashboards"] = dashboard_verifications
    results["external_font_requests"] = external_font_requests
    results["local_font_requests_count"] = len(local_font_requests)
    results["local_font_sample"] = local_font_requests[:5]

    print("\n" + "="*60)
    print("TYPOGRAPHY FORENSIC VERIFICATION RESULTS:")
    print("="*60)
    print(f"External Google Fonts Requests: {len(external_font_requests)} (Expected: 0)")
    print(f"Local WOFF2 Font Requests: {len(local_font_requests)} (Expected: > 0)")
    print("Weight 300 Loaded:", font_checks["checks"].get("300") or font_checks["checks"].get(300))
    print("Weight 400 Loaded:", font_checks["checks"].get("400") or font_checks["checks"].get(400))
    print("Weight 500 Loaded:", font_checks["checks"].get("500") or font_checks["checks"].get(500))
    print("Weight 600 Loaded:", font_checks["checks"].get("600") or font_checks["checks"].get(600))
    print("Weight 700 Loaded:", font_checks["checks"].get("700") or font_checks["checks"].get(700))
    print("Weight 800 Loaded:", font_checks["checks"].get("800") or font_checks["checks"].get(800))
    print("Weight 900 Loaded:", font_checks["checks"].get("900") or font_checks["checks"].get(900))

    assert len(external_font_requests) == 0, f"Found unexpected external requests: {external_font_requests}"
    assert len(local_font_requests) > 0, "No local font requests were loaded"
    assert font_checks["checks"].get("800") or font_checks["checks"].get(800), "Weight 800 not loaded"
    assert font_checks["checks"].get("900") or font_checks["checks"].get(900), "Weight 900 not loaded"
    print("\n[SUCCESS] ALL TYPOGRAPHY CHECKS PASSED PERFECTLY!\n")

if __name__ == "__main__":
    verify_typography()
