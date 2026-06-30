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
        
        # Take a screenshot to verify English
        page.screenshot(path="maps_search_en.png")
        print("Screenshot saved to maps_search_en.png")
        
        # Find the feed container and list places
        feed = page.locator('div[role="feed"]')
        print(f"Feed count: {feed.count()}")
        
        # Find place elements
        # Usually each card is a div containing the link and info
        # Let's inspect the page content for place elements
        # Let's extract all a[href*="/maps/place/"] links and dump their outerHTML
        places = page.locator('a[href*="/maps/place/"]').all()
        print(f"Found {len(places)} places")
        for i, place in enumerate(places[:5]):
            html = place.evaluate("el => el.outerHTML")
            text = place.evaluate("el => el.innerText")
            print(f"\n--- Place {i} ---")
            print(f"Text: {repr(text)}")
            print(f"HTML: {html[:400]}")
            
        browser.close()

if __name__ == "__main__":
    main()
