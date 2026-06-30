"""
Amazon Product Search and Extract Flow

Goal: Search for a mechanical keyboard, filter by free shipping, select the first result, and extract details.
Success criteria: Extracts product title and price on detail page.
"""

import sys
import os
import time

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "amazon_search"

def search(url: str) -> str:
    """
    Returns: 'success' | 'skipped:<reason>' | 'failed'
    """
    # Navigate to Amazon Saudi Arabia in English
    browser.navigate("https://www.amazon.sa/?language=en_AE")
    clicker.short_wait(4, 2)

    page = browser.get_page()

    # Step 1: Find search input and search for "mechanical keyboard"
    print("[AMAZON] Step 1: Locating search bar...")
    search_input_btn = page.locator("input#twotabsearchtextbox").first
    if search_input_btn.count() > 0:
        search_input_btn.click()
        print("[AMAZON] Clicked search bar via DOM")
    else:
        # Fallback to OCR
        result = runner.ocr_find_and_click("Search Amazon.sa", "https://www.amazon.sa", FLOW_KEY)
        if result == "failed":
            result = runner.ocr_find_and_click("Search", "https://www.amazon.sa", FLOW_KEY)
        if result == "failed":
            return "failed"

    clicker.short_wait(1, 1)
    clicker.type_text("mechanical keyboard")
    clicker.press("Enter")
    clicker.short_wait(4, 2)

    # Step 2: Click the "Free Shipping" filter on the left sidebar
    print("[AMAZON] Step 2: Applying Free Shipping filter...")
    page_url = page.url
    # We look for "Free Shipping by Amazon" or "Free Shipping" in OCR
    # If it fails, we will trigger the self-healing strategy tree / AGENT_NEEDED
    result = runner.ocr_find_and_click("Free Shipping by Amazon", page_url, FLOW_KEY, retry=True)
    if result == "failed":
        print("[AMAZON] Free Shipping by Amazon not found, trying Free Shipping...")
        result = runner.ocr_find_and_click("Free Shipping", page_url, FLOW_KEY, retry=True)
    
    # If the filter was clicked, wait for reload
    clicker.short_wait(4, 2)

    # Step 3: Find and click the first product result
    # We can look for "SAR" (Saudi Riyal) which is always next to the price of results
    print("[AMAZON] Step 3: Clicking first product result...")
    page_url = page.url
    img_path = browser.screenshot()
    all_items = ocr.find_all(img_path)
    
    # Amazon search results have prices starting with SAR. Let's find "SAR" matches.
    sar_matches = [i for i in all_items if "sar" in i["text"].lower() and i["y"] > 250 and i["x"] > 200]
    if sar_matches:
        # Sort by y, then x to get the topmost, leftmost product result
        sar_matches.sort(key=lambda i: (i["y"], i["x"]))
        first_price = sar_matches[0]
        print(f"[AMAZON] Found price anchor '{first_price['text']}' at ({first_price['x']}, {first_price['y']})")
        # Click slightly above the price (e.g. Y offset of -60px) to hit the product title link
        clicker.click(first_price["x"], first_price["y"] - 60)
        clicker.short_wait(5, 2)
    else:
        # Fallback to clicking using OCR search for "Keyboard"
        result = runner.ocr_find_and_click("keyboard", page_url, FLOW_KEY, exact=False)
        if result == "failed":
            # Escalate
            ss = browser.screenshot(save_path=os.path.join(runner.FAILURES_DIR, "amazon_no_results.png"))
            fix = runner._signal_agent("find_first_product", page_url, ocr.summarize(ss) if ss else [], ss or "")
            if fix.get("action") == "skip":
                return "skipped:no_products_found"
            return "failed"

    # Step 4: Extract product title and price on detail page
    print("[AMAZON] Step 4: Extracting details...")
    clicker.short_wait(4, 2)
    detail_url = page.url
    img_detail = browser.screenshot()
    detail_text = ocr.summarize(img_detail)
    
    # Extract price (look for SAR in the text)
    prices = [t for t in detail_text if "sar" in t.lower()]
    extracted_price = prices[0] if prices else "Price not found"
    
    # Save the product details to logs/amazon_leads.txt
    log_path = os.path.join(PROJECT_ROOT, "logs", "amazon_leads.txt")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"\n--- Amazon Product Found ---\n")
        f.write(f"URL: {detail_url}\n")
        f.write(f"Extracted Price Info: {extracted_price}\n")
        f.write(f"OCR snippet: {' '.join(detail_text[:30])}...\n")
        
    print(f"[AMAZON] ✅ Extracted price details: '{extracted_price}'. Saved to logs/amazon_leads.txt")
    return "success"
