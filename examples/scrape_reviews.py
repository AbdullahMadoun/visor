import time
import json
import sys
from playwright.sync_api import sync_playwright

def scrape_coffee_shop_reviews(headless=True):
    results = {}
    with sync_playwright() as p:
        print("[INFO] Launching browser...")
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Navigate to Google Maps search
        query = "best coffee in Sulimaniyah Riyadh"
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}/?hl=en"
        print(f"[INFO] Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        # Scroll feed to load more results
        feed = page.locator('div[role="feed"]')
        if feed.count() > 0:
            print("[INFO] Scrolling feed to load more places...")
            for _ in range(3):
                feed.first.evaluate("el => el.scrollTop = el.scrollHeight")
                page.wait_for_timeout(2000)
                
        # Scrape all visible places
        js_get_cards = """
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
        cards = page.evaluate(js_get_cards)
        
        parsed_places = []
        for card in cards:
            name = card['name']
            text = card['cardText']
            href = card['href']
            
            # Exclude places in Al Bathaa/Batha (different neighborhood)
            if "al bathaa" in text.lower() or "batha" in text.lower():
                continue
                
            # Parse rating
            lines = text.split('\n')
            rating = 0.0
            reviews_count = 0
            
            import re
            for line in lines:
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
                m3 = re.search(r'(\d\.\d)', text)
                if m3:
                    rating = float(m3.group(1))
                    
            parsed_places.append({
                "name": name,
                "rating": rating,
                "reviews_count": reviews_count,
                "href": href
            })
            
        if not parsed_places:
            print("[ERROR] No coffee shops found!")
            browser.close()
            return None
            
        # Select the top-rated coffee shop
        top_shop = max(parsed_places, key=lambda x: (x['rating'], x['reviews_count']))
        print(f"[INFO] Selected Top-Rated Shop: {top_shop['name']} | Rating: {top_shop['rating']}")
        
        results['shop_name'] = top_shop['name']
        results['shop_rating'] = top_shop['rating']
        
        # Click on the top-rated coffee shop
        page.locator(f'a[aria-label="{top_shop["name"]}"]').first.click()
        page.wait_for_timeout(5000)
        
        # Click on the "Reviews" tab
        reviews_tab = page.locator('button[role="tab"]:has-text("Reviews")')
        if reviews_tab.count() == 0:
            reviews_tab = page.locator('button[aria-label*="Reviews"]')
            
        if reviews_tab.count() > 0:
            reviews_tab.first.click()
            page.wait_for_timeout(3000)
        else:
            print("[ERROR] Reviews tab not found!")
            browser.close()
            return None
            
        # Helper to extract reviews from current view
        extract_js = """
        async () => {
            const cards = document.querySelectorAll('div.jftiEf');
            
            // Expand all visible reviews by clicking 'See more'
            for (const card of cards) {
                const moreBtn = card.querySelector('button.w8nwRe, button[aria-label="See more"]');
                if (moreBtn) {
                    moreBtn.click();
                }
            }
            await new Promise(resolve => setTimeout(resolve, 500));
            
            const list = [];
            for (const card of cards) {
                // Get Author Name
                const nameEl = card.querySelector('.d1z77');
                let name = nameEl ? nameEl.innerText.trim() : '';
                if (!name) {
                    const firstDiv = card.querySelector('div');
                    if (firstDiv) {
                        name = firstDiv.innerText.split('\\n')[0];
                    }
                }
                
                // Get Rating (stars)
                const ratingEl = card.querySelector('.kvMYJc, [aria-label*="star"]');
                const rating = ratingEl ? ratingEl.getAttribute('aria-label') : '';
                
                // Get Review Text
                const textEl = card.querySelector('span.wiI7pd');
                const text = textEl ? textEl.innerText.trim() : '';
                
                list.push({
                    author: name || 'Anonymous',
                    rating: rating || 'Unknown',
                    text: text
                });
            }
            return list;
        }
        """
        
        # 1. Sort by Highest rating (Positive reviews)
        print("[INFO] Sorting by Highest rating...")
        sort_button = page.locator('button[aria-label="Sort reviews"]')
        if sort_button.count() == 0:
            sort_button = page.locator('button:has-text("Sort")')
        sort_button.first.click()
        page.wait_for_timeout(1500)
        
        highest_option = page.locator('div[role="menuitemradio"]').filter(has_text="Highest rating")
        highest_option.first.click()
        page.wait_for_timeout(3000)
        
        positive_reviews = page.evaluate(extract_js)
        # Filter reviews that have actual text
        positive_with_text = [r for r in positive_reviews if r['text'].strip()][:3]
        results['positive_reviews'] = positive_with_text
        print(f"[INFO] Scraped {len(positive_with_text)} positive reviews.")
        
        # 2. Sort by Lowest rating (Negative reviews)
        print("[INFO] Sorting by Lowest rating...")
        sort_button.first.click()
        page.wait_for_timeout(1500)
        
        lowest_option = page.locator('div[role="menuitemradio"]').filter(has_text="Lowest rating")
        lowest_option.first.click()
        page.wait_for_timeout(3000)
        
        negative_reviews = page.evaluate(extract_js)
        # Filter reviews that have actual text
        negative_with_text = [r for r in negative_reviews if r['text'].strip()][:3]
        results['negative_reviews'] = negative_with_text
        print(f"[INFO] Scraped {len(negative_with_text)} negative reviews.")
        
        browser.close()
        return results

if __name__ == "__main__":
    headless_mode = True
    if len(sys.argv) > 1 and sys.argv[1].lower() == "headful":
        headless_mode = False
        
    print(f"[INFO] Starting scraper (headless={headless_mode})...")
    data = scrape_coffee_shop_reviews(headless=headless_mode)
    
    if data:
        output_file = "coffee_reviews_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n[SUCCESS] Extracted reviews saved to {output_file}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("[ERROR] Scrape failed.")
