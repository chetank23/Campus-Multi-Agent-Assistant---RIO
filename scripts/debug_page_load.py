import os
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()

    console_msgs = []
    failed_reqs = []
    pg.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
    pg.on("response", lambda r: failed_reqs.append(f"{r.status} {r.url}") if r.status >= 400 else None)

    pg.goto("http://localhost:5173/login")
    pg.fill("input[type='email']", "admin@campus.edu")
    pg.fill("input[type='password']", "Admin#RioLocal26")
    pg.click("button[type='submit']")
    pg.wait_for_url("**/admin**", timeout=10000)
    print("Logged in. Current URL:", pg.url)

    # Client-side SPA navigation via sidebar link
    pg.click("a[href='/admin/settings']")
    time.sleep(2)
    print("Navigated via SPA link to /admin/settings. Current URL:", pg.url)
    pg.screenshot(path="reports/screenshots/debug_settings.png")
    print("Page title:", pg.title())
    print("Has Settings header:", "Settings & Data Management" in pg.content())

    print("\nConsole messages:")
    for m in console_msgs:
        print("  ", m)

    print("\nFailed network requests:")
    for f in failed_reqs:
        print("  ", f)

    browser.close()
