from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto("http://localhost:5173/login")
    pg.fill("input[type='email']", "admin@campus.edu")
    pg.fill("input[type='password']", "Admin#RioLocal26")
    pg.click("button[type='submit']")
    pg.wait_for_url("**/admin**", timeout=10000)
    cookies = ctx.cookies()
    print("Cookies in browser context:")
    for c in cookies:
        print(f"  {c['name']} (domain={c['domain']}, path={c['path']}, httpOnly={c['httpOnly']})")
    browser.close()
