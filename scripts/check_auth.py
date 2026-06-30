import time, os
from playwright.sync_api import sync_playwright

def main():
    p = sync_playwright().start()
    browser = p.chromium.launch_persistent_context(os.path.expanduser("~/visor_chrome_profile"), headless=True, viewport={"width":1440,"height":900})
    page = browser.pages[0]
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    time.sleep(3)
    
    title = page.title().lower()
    text = page.evaluate("document.body.innerText").lower()
    print(f"TITLE: {title}")
    
    if "sign in" in title or "session_key" in text:
        print("AUTH_STATE: LOGGED_OUT")
    else:
        print("AUTH_STATE: LOGGED_IN")
        
    browser.close()
    p.stop()

if __name__ == "__main__":
    main()
