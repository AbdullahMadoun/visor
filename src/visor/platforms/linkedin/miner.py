"""
LinkedIn Hiring Posts Miner Flow

Goal: Find hiring posts in a target region matching specific criteria (e.g. email drops).
Success criteria: Extracts posts and returns them.
"""

import sys
import os
import re
import time

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "linkedin_miner"

def miner(query: str) -> str:
    encoded_query = query.replace(" ", "%20")
    url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=FACETED_SEARCH"
    
    browser.navigate(url)
    clicker.short_wait(3, 2)
    
    ss = browser.screenshot()
    all_text = ocr.summarize(ss)
    text_joined = " ".join(all_text).lower()
    
    # 1. Login Wall Check (Try to Dismiss)
    if "sign in" in text_joined or "session_key" in text_joined:
        print("[MINER] Hit the LinkedIn login wall. Attempting to dismiss modal...")
        try:
            page = browser.get_page()
            # Most simple modals can be closed by pressing Escape
            page.keyboard.press("Escape")
            time.sleep(1)
            page.keyboard.press("Escape")
            time.sleep(2)
            
            # Re-read OCR to see if the wall is gone
            ss = browser.screenshot()
            new_text = " ".join(ocr.summarize(ss)).lower()
            if "sign in" not in new_text and "session_key" not in new_text:
                print("[MINER] ✅ Successfully dismissed the login wall modal using Escape!")
            else:
                print("[MINER] ❌ Could not dismiss the wall. It is a hard lock. Please log in.")
                return "failed:auth_required"
        except Exception as e:
            print(f"[MINER] ❌ Failed to dismiss login wall: {e}")
            return "failed:auth_required"
            
    # 2. No Results Check
    if "no matching results" in text_joined or "no results found" in text_joined:
        print("[MINER] NO_RESULTS: No hiring posts found for this query.")
        return "success:no_results"
        
    # 3. Click 'more' buttons using JS and extract full post text
    page = browser.get_page()
    try:
        page.wait_for_timeout(3000)
        # OCR-First Architecture: Visually identify and expand truncated posts via scrolling
        ss_path = os.path.join(os.getcwd(), "temp_miner_ss.png")
        
        for _ in range(3):
            page.screenshot(path=ss_path)
            all_text_boxes = ocr.find_all(ss_path)
            for item in all_text_boxes:
                text_str = item["text"].lower().strip()
                if text_str in ["see more", "…more", "...more", "more"] and item["x"] < 1200:
                    print(f"[MINER] OCR Intelligence found truncated post at ({item['x']}, {item['y']}). Clicking natively.")
                    clicker.click(item["x"], item["y"])
                    time.sleep(0.5)
            # Scroll to load and expand next posts
            page.mouse.wheel(0, 800)
            time.sleep(2)
                
        # Return the entire text of all posts now that they are visually expanded
        text_joined = page.evaluate('''() => {
            let text = "";
            document.querySelectorAll('.update-components-actor__name, .feed-shared-actor__name').forEach(el => {
                let container = el.closest('li') || el.closest('div[data-urn]') || el.closest('.feed-shared-update-v2') || el.parentElement.parentElement.parentElement;
                if(container) text += container.innerText + " ";
            });
            return text;
        }''')
        
        # Fallback to body text if container extraction fails
        if not text_joined or len(text_joined) < 50:
            text_joined = page.evaluate('document.body.innerText')
            
        page.wait_for_timeout(1000)
    except Exception:
        text_joined = ""
    
    # 4. Extract emails
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_joined)
    
    if emails:
        emails = list(set(emails)) # deduplicate
        log_path = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "miner_leads.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"\n--- Leads for query: {query} ---\n")
            f.write(f"Raw OCR snippet: {text_joined[:300]}...\n")
            f.write(f"Found Emails: {', '.join(emails)}\n\n")
            
        print(f"[MINER] ✅ Extracted {len(emails)} unique email(s) via JS extraction! Saved to logs/miner_leads.txt")
        return "success:found_leads"
    else:
        print("[MINER] ✅ No emails found in page text.")
        return "success:no_emails_found"


if __name__ == "__main__":
    miner('"AI Engineer" "hiring" "@gmail.com"')
