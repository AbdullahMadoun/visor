from playwright.sync_api import sync_playwright

def search_haraj():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating to Haraj...")
        page.goto("https://haraj.com.sa/")
        page.wait_for_timeout(3000)
        
        # We need to search for "كرسي مكتب" in "الرياض"
        print("Typing search query...")
        search_input = page.get_by_placeholder("ابحث عن سلعة").first
        if not search_input.is_visible():
            search_input = page.locator('input[type="text"]').first
        
        search_input.fill("كرسي مكتب الرياض")
        search_input.press("Enter")
        page.wait_for_timeout(5000)
        
        page.screenshot(path="/tmp/haraj_after_search.png")
        print("Scraping results...")
        items = page.locator('div[data-testid="post-card"] a, a[data-testid="post-card"], a[href*="/111"]').all()
        if not items:
            # Fallback to any link containing /111 (Haraj post IDs usually start with 111)
            items = page.locator('a').all()
            
        count = len(items)
        print(f"Found {count} candidate links")
        
        valid_posts = []
        for item in items:
            href = item.get_attribute("href")
            text = item.inner_text().strip()
            if href and "/11" in href and len(text) > 5:
                valid_posts.append((text.replace('\n', ' - '), href))
                
        for i, (text, href) in enumerate(valid_posts[:5]):
            print(f"--- Deal {i+1} ---\n{text}\nRAW Href: {href}")
            
        browser.close()

if __name__ == "__main__":
    search_haraj()
