import time
from playwright.sync_api import sync_playwright

def main():
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
        
        # Navigate to Google Maps search with hl=en
        url = "https://www.google.com/maps/search/best+coffee+in+Sulimaniyah+Riyadh/?hl=en"
        print(f"Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        # Click on Joe Barrel Coffee
        print("Clicking on Joe Barrel Coffee...")
        joe_barrel_link = page.locator('a[aria-label="Joe Barrel Coffee"]')
        if joe_barrel_link.count() > 0:
            joe_barrel_link.first.click()
            print("Clicked!")
        else:
            print("Joe Barrel Coffee link not found!")
            
        page.wait_for_timeout(5000)
        page.screenshot(path="maps_detail.png")
        print("Screenshot saved to maps_detail.png")
        
        # Dump tabs text
        tabs = page.locator('button[role="tab"]').all()
        print(f"Found {len(tabs)} tabs:")
        for tab in tabs:
            print(f"Tab text: {repr(tab.inner_text())} | aria-label: {tab.get_attribute('aria-label')}")
            
        browser.close()

if __name__ == "__main__":
    main()
