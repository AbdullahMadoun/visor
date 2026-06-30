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
        
        url = "https://www.google.com/maps/search/best+coffee+in+Sulimaniyah+Riyadh/?hl=en"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        page.locator('a[aria-label="Joe Barrel Coffee"]').first.click()
        page.wait_for_timeout(5000)
        
        # Click reviews tab
        reviews_tab = page.locator('button[role="tab"]:has-text("Reviews")')
        if reviews_tab.count() == 0:
            reviews_tab = page.locator('button[aria-label*="Reviews"]')
        reviews_tab.first.click()
        page.wait_for_timeout(3000)
        
        # Sort by Highest Rating
        sort_button = page.locator('button[aria-label="Sort reviews"]')
        if sort_button.count() == 0:
            sort_button = page.locator('button:has-text("Sort")')
        sort_button.first.click()
        page.wait_for_timeout(2000)
        
        highest_option = page.locator('div[role="menuitemradio"]').filter(has_text="Highest rating")
        highest_option.first.click()
        print("Clicked Sort by Highest rating, waiting for update...")
        page.wait_for_timeout(3000)
        
        # Extract reviews
        js_code = """
        async () => {
            const cards = document.querySelectorAll('div.jftiEf');
            
            // Expand all reviews
            for (const card of cards) {
                const moreBtn = card.querySelector('button.w8nwRe, button[aria-label="See more"]');
                if (moreBtn) {
                    moreBtn.click();
                }
            }
            // Wait for expansion to complete
            await new Promise(resolve => setTimeout(resolve, 500));
            
            const results = [];
            for (const card of cards) {
                // Let's get the author name
                // Let's query common classes or get the first text line
                const nameEl = card.querySelector('.d1z77');
                let name = nameEl ? nameEl.innerText.trim() : '';
                
                if (!name) {
                    // Fallback to searching first div inside header
                    const firstDiv = card.querySelector('div');
                    if (firstDiv) {
                        name = firstDiv.innerText.split('\\n')[0];
                    }
                }
                
                // Get rating
                const ratingEl = card.querySelector('.kvMYJc, [aria-label*="star"]');
                const rating = ratingEl ? ratingEl.getAttribute('aria-label') : '';
                
                // Get review text
                const textEl = card.querySelector('span.wiI7pd');
                const text = textEl ? textEl.innerText.trim() : '';
                
                results.push({ name, rating, text });
            }
            return results;
        }
        """
        reviews = page.evaluate(js_code)
        import json
        print("Highest Rating Reviews extracted:")
        print(json.dumps(reviews[:5], indent=2))
        
        browser.close()

if __name__ == "__main__":
    main()
