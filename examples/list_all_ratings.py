import json
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
        
        url = "https://www.google.com/maps/search/best+coffee+in+Sulimaniyah+Riyadh/?hl=en"
        print(f"Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        # Scroll the feed a bit to load more results
        feed = page.locator('div[role="feed"]')
        if feed.count() > 0:
            print("Scrolling feed...")
            for _ in range(3):
                feed.first.evaluate("el => el.scrollTop = el.scrollHeight")
                page.wait_for_timeout(2000)
        
        # Evaluate script to get card info
        js_code = """
        () => {
            const results = [];
            const links = document.querySelectorAll('a.hfpxzc');
            for (const link of links) {
                const name = link.getAttribute('aria-label');
                const href = link.getAttribute('href');
                let parent = link.parentElement;
                for (let i = 0; i < 6; i++) {
                    if (parent && parent.innerText && parent.innerText.includes(name)) {
                        // Found a parent container with the text
                    }
                    if (parent && parent.parentElement) {
                        parent = parent.parentElement;
                    }
                }
                const cardText = parent ? parent.innerText : '';
                results.push({ name, href, cardText });
            }
            return results;
        }
        """
        cards = page.evaluate(js_code)
        print(f"Scraped {len(cards)} cards:")
        print(json.dumps(cards, indent=2, ensure_ascii=False))
        
        browser.close()

if __name__ == "__main__":
    main()
