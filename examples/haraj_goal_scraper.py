import json
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from visor.core import browser, ocr, clicker

def scrape_haraj_chairs(target_count=40):
    results = []
    
    # 1. Navigate using Visor's native browser to avoid captchas
    browser.navigate("https://haraj.com.sa/search/%D9%83%D8%B1%D8%B3%D9%8A%20%D9%85%D9%83%D8%AA%D8%A8%20%D8%A7%D9%84%D8%B1%D9%8A%D8%A7%D8%B6")
    time.sleep(5)
    
    # We will use JavaScript to scroll and collect links
    page = browser.get_page()
    
    links = set()
    retries = 0
    
    while len(links) < target_count and retries < 15:
        # Find all a tags
        elements = page.query_selector_all('a')
        for el in elements:
            href = el.get_attribute("href")
            # Haraj post links usually start with /11
            if href and href.startswith("/11") and href not in links:
                links.add(href)
        
        print(f"Found {len(links)} links so far...")
        if len(links) < target_count:
            page.evaluate("window.scrollBy(0, 1000)")
            time.sleep(2)
            retries += 1
            
    links = list(links)[:target_count]
    print(f"Proceeding to extract {len(links)} listings...")
    
    for i, link in enumerate(links):
        full_url = f"https://haraj.com.sa{link}"
        print(f"[{i+1}/{len(links)}] Scraping: {full_url}")
        try:
            page.goto(full_url, timeout=15000)
            time.sleep(2)
            
            title_el = page.query_selector('h1')
            title = title_el.inner_text().strip() if title_el else "Unknown"
            
            # The body text is the easiest way to get description if the DOM is weird
            body_el = page.query_selector('body')
            desc = body_el.inner_text().strip() if body_el else ""
            
            results.append({
                "url": full_url,
                "title": title,
                "description": desc[:1000] # Take first 1000 chars to avoid massive JSON
            })
        except Exception as e:
            print(f"Failed to scrape {full_url}: {e}")
            
    with open("haraj_40_listings.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print("Done! Saved to haraj_40_listings.json")

if __name__ == "__main__":
    scrape_haraj_chairs()
