import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    page = context.pages[0]
    page.screenshot(path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "answer1.png"), full_page=True)
