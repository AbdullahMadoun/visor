import time
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
        
        # Navigate to Google Maps search with hl=en
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
        
        # Get all cards
        js_code = """
        () => {
            const results = [];
            const links = document.querySelectorAll('a.hfpxzc');
            for (const link of links) {
                const name = link.getAttribute('aria-label');
                const href = link.getAttribute('href');
                const parent = link.parentElement;
                const cardText = parent ? parent.innerText : '';
                results.push({ name, href, cardText });
            }
            return results;
        }
        """
        cards = page.evaluate(js_code)
        
        parsed_places = []
        for card in cards:
            name = card['name']
            text = card['cardText']
            href = card['href']
            
            # Simple parser for rating
            lines = text.split('\n')
            rating = 0.0
            reviews_count = 0
            
            # Exclude places in Al Bathaa
            if "al bathaa" in text.lower() or "batha" in text.lower():
                print(f"Skipping {name} (located in Al Bathaa)")
                continue
                
            for line in lines:
                import re
                m = re.match(r'^(\d\.\d)\(([\d,]+)\)', line.replace(" ", ""))
                if m:
                    rating = float(m.group(1))
                    reviews_count = int(m.group(2).replace(",", ""))
                    break
                m2 = re.match(r'^(\d\.\d)$', line.strip())
                if m2:
                    rating = float(m2.group(1))
                    break
            
            if rating == 0.0:
                # Try finding any float in text
                m3 = re.search(r'(\d\.\d)', text)
                if m3:
                    rating = float(m3.group(1))
                    
            parsed_places.append({
                "name": name,
                "rating": rating,
                "reviews_count": reviews_count,
                "href": href
            })
            
        print("\nParsed Coffee Shops:")
        for idx, p_item in enumerate(parsed_places):
            print(f"{idx}: {p_item['name']} | Rating: {p_item['rating']} | Reviews: {p_item['reviews_count']}")
            
        if not parsed_places:
            print("No coffee shops found!")
            browser.close()
            return
            
        # Select the top-rated coffee shop
        top_shop = max(parsed_places, key=lambda x: (x['rating'], x['reviews_count']))
        print(f"\nTop-rated coffee shop: {top_shop['name']} with rating {top_shop['rating']}")
        
        # Click on the top-rated coffee shop link
        print(f"Clicking on {top_shop['name']}...")
        page.locator(f'a[aria-label="{top_shop["name"]}"]').first.click()
        page.wait_for_timeout(5000)
        
        page.screenshot(path="top_shop_detail.png")
        print("Screenshot saved to top_shop_detail.png")
        
        # Find reviews tab
        reviews_tab = page.locator('button[role="tab"]:has-text("Reviews")')
        if reviews_tab.count() == 0:
            reviews_tab = page.locator('button[aria-label*="Reviews"]')
            
        if reviews_tab.count() > 0:
            print("Found Reviews tab! Clicking it...")
            reviews_tab.first.click()
            page.wait_for_timeout(3000)
            page.screenshot(path="top_shop_reviews.png")
            print("Screenshot saved to top_shop_reviews.png")
            
            # Print some text from the reviews panel to see the structure
            # Let's extract buttons to find the Sort button
            buttons = page.locator('button').all()
            print(f"Found {len(buttons)} buttons on details pane. Printing some with text/aria-label:")
            for b in buttons:
                txt = b.inner_text().strip()
                label = b.get_attribute("aria-label") or ""
                if txt or label:
                    if "sort" in txt.lower() or "sort" in label.lower() or "latest" in txt.lower() or "rating" in txt.lower():
                        print(f"Button - Text: {repr(txt)} | Aria-label: {repr(label)}")
        else:
            print("Reviews tab not found!")
            
        browser.close()

if __name__ == "__main__":
    main()
