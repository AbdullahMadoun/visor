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
        
        # Navigate directly to search
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
        
        # Locate and click Sort button
        sort_button = page.locator('button[aria-label="Sort reviews"]')
        if sort_button.count() == 0:
            sort_button = page.locator('button:has-text("Sort")')
            
        print("Clicking Sort button...")
        sort_button.first.click()
        page.wait_for_timeout(2000)
        
        # Save screenshot of the dropdown menu
        page.screenshot(path="sort_menu.png")
        print("Screenshot of sort menu saved to sort_menu.png")
        
        # Print menu elements
        js_code = """
        () => {
            const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], [role="menuitemradio"], button, div'));
            const matches = [];
            for (const item of items) {
                const text = item.innerText ? item.innerText.trim() : '';
                if (text === 'Highest rating' || text === 'Lowest rating' || text === 'Newest' || text === 'Most relevant') {
                    matches.push({
                        tagName: item.tagName,
                        className: item.className,
                        role: item.getAttribute('role'),
                        innerText: text
                    });
                }
            }
            return matches;
        }
        """
        menu_items = page.evaluate(js_code)
        import json
        print("Menu items found:")
        print(json.dumps(menu_items, indent=2))
        
        browser.close()

if __name__ == "__main__":
    main()
