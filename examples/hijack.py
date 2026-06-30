import sys
from playwright.sync_api import sync_playwright
import time
import os

def hijack_session():
    print("Launching browser for you to log in...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.linkedin.com/login")
        
        print("Please log in. Waiting for 'li_at' cookie...")
        
        while True:
            cookies = context.cookies()
            if any(c['name'] == 'li_at' for c in cookies):
                project_root = os.path.dirname(os.path.abspath(__file__))
                session_path = os.path.join(project_root, "session.json")
                print(f"Session detected! Saving to {session_path}")
                context.storage_state(path=session_path)
                break
            time.sleep(2)
            
        browser.close()
        print("Done! Session info hijacked and saved persistently.")

if __name__ == "__main__":
    hijack_session()
