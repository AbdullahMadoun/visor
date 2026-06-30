import time
import os
from playwright.sync_api import sync_playwright

def main():
    print("Starting Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Navigate to Google Maps search
        query = "best coffee in Sulimaniyah Riyadh"
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}/"
        print(f"Navigating to: {url}")
        
        page.goto(url, wait_until="domcontentloaded")
        print("Waiting for page to settle...")
        page.wait_for_timeout(5000)
        
        # Capture screenshot to check what was loaded
        screenshot_path = "maps_search.png"
        page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")
        
        # Dump some elements info
        links = page.locator('a[href*="/maps/place/"]').all()
        print(f"Found {len(links)} links containing '/maps/place/'")
        for i, link in enumerate(links[:10]):
            text = link.inner_text()
            href = link.get_attribute("href")
            print(f"[{i}] Text: {repr(text)} | Href: {href[:60]}...")
            
        browser.close()

if __name__ == "__main__":
    main()
