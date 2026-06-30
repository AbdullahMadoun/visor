import time
from visor.core import browser, clicker, ocr, runner

FLOW_KEY = "linkedinfeed"

def main(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(4, 4)
    page = browser.get_page()
    
    connections_made = 0
    visited_y = set()
    scroll_attempts = 0
    
    print(f"[{FLOW_KEY}] Scanning feed for job posters...")
    
    while connections_made < 3 and scroll_attempts < 20:
        img_path = browser.screenshot()
        if not img_path: return "failed"
        
        matches = ocr.find_all(img_path)
        
        # Look for the small degree texts like "2nd", "3rd", "3rd+", etc.
        # Note: EasyOCR commonly misreads "2nd" as "Znd"
        authors = [m for m in matches if any(x in m["text"].lower() for x in ["3rd", "2nd", "znd"])]
        
        found_new_author = False
        for author in authors:
            if connections_made >= 3:
                break
                
            if any(abs(author["y"] - vy) < 50 for vy in visited_y):
                continue
                
            visited_y.add(author["y"])
            found_new_author = True
            
            print(f"[{FLOW_KEY}] Clicking on poster profile (Degree label: '{author['text']}') at ({author['x']}, {author['y']})...")
            clicker.click(author["x"], author["y"])
            clicker.short_wait(4, 4)
            
            # Now we are on their profile! Find the Connect button.
            # Use ocr_find_and_click to leverage self-healing
            result = runner.ocr_find_and_click("Connect", url, FLOW_KEY)
            
            if result == "success" or result == "agent_fixed":
                clicker.short_wait(2, 2)
                
                # Check for "Send without a note" or "Send"
                modal_result = runner.ocr_find_and_click("Send without a note", url, FLOW_KEY, retry=False)
                if modal_result == "failed":
                    runner.ocr_find_and_click("Send", url, FLOW_KEY, retry=False)
                
                clicker.short_wait(2, 2)
                
                # Verify "Pending"
                if runner.verify_ocr("Pending"):
                    connections_made += 1
                    print(f"[{FLOW_KEY}] Success! Connected to {connections_made}/3.")
                else:
                    print(f"[{FLOW_KEY}] Failed to verify Pending state.")
            else:
                print(f"[{FLOW_KEY}] Couldn't find Connect on profile.")
            
            # Go back to the feed
            print(f"[{FLOW_KEY}] Navigating back to feed...")
            page.go_back()
            clicker.short_wait(4, 4)
            # Re-verify we are back by letting it screenshot on the next loop
            break
            
        if not found_new_author:
            print(f"[{FLOW_KEY}] No new posters found in viewport. Scrolling...")
            page.mouse.wheel(0, 1000)
            clicker.short_wait(3, 3)
            scroll_attempts += 1
            # Clear visited_y because coordinates changed
            visited_y.clear()

    if connections_made >= 3:
        return "success"
    return f"skipped:only_connected_{connections_made}"
