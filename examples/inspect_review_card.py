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
        
        # Navigate directly to the place URL if we have it, or go via search
        # Since we know Joe Barrel Coffee is the top one, we can go to search and click
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
        
        # Find review elements
        # Let's inspect elements with data-review-id or search for divs containing the review text
        js_code = """
        () => {
            const elements = document.querySelectorAll('[data-review-id]');
            const results = [];
            for (let i = 0; i < Math.min(elements.length, 3); i++) {
                const el = elements[i];
                results.push({
                    reviewId: el.getAttribute('data-review-id'),
                    tagName: el.tagName,
                    className: el.className,
                    innerText: el.innerText.substring(0, 300)
                });
            }
            return {
                count: elements.length,
                samples: results
            };
        }
        """
        review_info = page.evaluate(js_code)
        import json
        print("Review Info with [data-review-id]:")
        print(json.dumps(review_info, indent=2))
        
        # Let's also check elements with class containing 'wi376c' or similar text containers
        js_code_2 = """
        () => {
            const divs = Array.from(document.querySelectorAll('div'));
            // Find divs that contain a review text (e.g. have class MyEned or MyEned's parent)
            const myened = document.querySelectorAll('.MyEned');
            const results = [];
            for (let i = 0; i < Math.min(myened.length, 3); i++) {
                const el = myened[i];
                results.push({
                    className: el.className,
                    innerText: el.innerText,
                    parentHTML: el.parentElement.outerHTML.substring(0, 300)
                });
            }
            return {
                myenedCount: myened.length,
                samples: results
            };
        }
        """
        myened_info = page.evaluate(js_code_2)
        print("MyEned Info:")
        print(json.dumps(myened_info, indent=2))
        
        browser.close()

if __name__ == "__main__":
    main()
