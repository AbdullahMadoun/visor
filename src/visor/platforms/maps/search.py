"""
Google Maps Business Scraper Flow

Goal: Navigate to Google Maps, search for coffee shops in Riyadh, click the first result, and extract details.
Success criteria: Extracts name, rating, and prints them.
"""

import sys
import os
import time

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "maps_search"

def search(url: str) -> str:
    """
    Returns: 'success' | 'skipped:<reason>' | 'failed'
    """
    # Navigate to Google Maps in English
    browser.navigate("https://www.google.com/maps?hl=en")
    clicker.short_wait(5, 2)

    page = browser.get_page()

    # Step 1: Click search box and search for "coffee shop Riyadh"
    print("[MAPS] Step 1: Finding search box...")
    search_input = page.locator("input#searchboxinput").first
    if search_input.count() > 0:
        search_input.click()
        print("[MAPS] Clicked search box via DOM")
    else:
        # Fallback to OCR search
        result = runner.ocr_find_and_click("Search Google Maps", "https://www.google.com/maps?hl=en", FLOW_KEY)
        if result == "failed":
            result = runner.ocr_find_and_click("Search", "https://www.google.com/maps?hl=en", FLOW_KEY)
        if result == "failed":
            return "failed"

    clicker.short_wait(1, 1)
    clicker.type_text("coffee shop Riyadh")
    clicker.press("Enter")
    # Google maps search takes a few seconds to load results
    clicker.short_wait(6, 2)

    # Step 2: Click the first business listing
    print("[MAPS] Step 2: Clicking the first coffee shop result...")
    clicked = False
    try:
        # Google Maps results list items always have links containing /maps/place/
        first_result = page.locator("a[href*='/maps/place/']").first
        if first_result.count() > 0:
            first_result.click(timeout=5000)
            print("[MAPS] Clicked first result via DOM link")
            clicked = True
    except Exception as e:
        print(f"[MAPS] DOM click failed ({e}), falling back to OCR coordinates")

    if not clicked:
        # Fallback to OCR: look for common rating decimal points or "stars" or review count
        img_path = browser.screenshot()
        all_text = ocr.summarize(img_path)
        print(f"[MAPS] OCR visible text: {all_text[:30]}")
        # Click on the first element in results area (e.g. click "coffee" or "Shop" or first matched text)
        result = runner.ocr_find_and_click("Riyadh", "https://www.google.com/maps?hl=en", FLOW_KEY, exact=False)
        if result == "failed":
            ss = browser.screenshot(save_path=os.path.join(runner.FAILURES_DIR, "maps_no_results.png"))
            fix = runner._signal_agent("click_first_business", "https://www.google.com/maps?hl=en", all_text, ss)
            if fix.get("action") == "skip":
                return "skipped:no_results_found"
            return "failed"

    # Wait for the detail panel to animate open
    clicker.short_wait(5, 2)

    # Step 3: Extract business name and rating from detail panel
    print("[MAPS] Step 3: Scraped info extraction...")
    detail_url = page.url
    img_detail = browser.screenshot()
    detail_text = ocr.summarize(img_detail)
    
    print(f"[MAPS] Business detail text: {detail_text[:30]}")
    
    # Simple heuristic to extract rating: a decimal number between 3.0 and 5.0
    import re
    ratings = []
    for t in detail_text:
        match = re.search(r'\b([3-5]\.[0-9])\b', t)
        if match:
            ratings.append(match.group(1))
            
    extracted_rating = ratings[0] if ratings else "Rating not found"
    
    # Save the scraped coffee shops to logs/coffee_shops.txt
    log_path = os.path.join(PROJECT_ROOT, "logs", "coffee_shops.txt")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"\n--- Coffee Shop Found ---\n")
        f.write(f"URL: {detail_url}\n")
        f.write(f"Extracted Rating: {extracted_rating}\n")
        f.write(f"OCR snippet: {' '.join(detail_text[:30])}...\n")
        
    print(f"[MAPS] ✅ Extracted coffee shop rating details: '{extracted_rating}'. Saved to logs/coffee_shops.txt")
    return "success"
