import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
    pg = ctx.new_page()

    pg.goto('http://localhost:5173/login')
    pg.fill("input[type='email']", 'admin@campus.edu')
    pg.fill("input[type='password']", 'Admin#RioLocal26')
    pg.click("button[type='submit']")
    pg.wait_for_url('**/admin**', timeout=10000)
    print("Logged in. Navigating to settings...")

    pg.click("a[href='/admin/settings']")
    time.sleep(3)
    text = pg.locator('body').inner_text()
    print("--- BODY TEXT ---\n", text[:1200])

    buttons = pg.locator('button').all_inner_texts()
    print("--- BUTTONS ---", buttons)

    browser.close()
