import sys
from playwright.sync_api import sync_playwright
import os
import time

with sync_playwright() as p:
    user_data_dir = os.path.expanduser("~/visor_chrome_profile")
    browser = p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    page = browser.new_page()
    page.goto("https://www.linkedin.com/feed/")
    time.sleep(5)
    print("Page Title:", page.title())
    
    cookies = browser.cookies()
    li_cookie = next((c for c in cookies if c['name'] == 'li_at'), None)
    if li_cookie:
        print("Logged in: li_at cookie found")
    else:
        print("Not logged in: li_at cookie missing")
        
    browser.close()
