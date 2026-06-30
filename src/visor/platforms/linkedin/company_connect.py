import os
import time
from visor.core import browser, ocr, clicker
from visor.core.runner import ocr_find_and_click

def connect(url: str) -> str:
    print(f"Navigating to company people page: {url}")
    browser.navigate(url)
    time.sleep(4)
    
    page = browser.get_page()
    success_count = 0
    target_count = 5
    consecutive_empty_scrolls = 0
    
    while success_count < target_count and consecutive_empty_scrolls < 10:
        img = browser.screenshot()
        all_items = ocr.find_all(img)
        
        # Find all 'Connect' buttons in current viewport
        connect_buttons = [i for i in all_items if "connect" in i["text"].lower() and i["confidence"] >= 0.6]
        
        # Filter out buttons that are too high up (might be nav bar) or too low
        # ALSO filter out buttons on the far right (x > 900) which are in the sidebar!
        # The main grid of employee cards is always in the main center-left column.
        connect_buttons = [b for b in connect_buttons if b["y"] > 100 and b["x"] < 900]
        
        if not connect_buttons:
            # Check if there is a 'Show more results' button
            show_more = next((i for i in all_items if "show more" in i["text"].lower() and i["confidence"] >= 0.5), None)
            if show_more:
                print("Found 'Show more results' button. Clicking it to load more...")
                clicker.click(show_more["x"], show_more["y"])
                time.sleep(3)
                consecutive_empty_scrolls = 0
                continue
                
            print("No 'Connect' buttons found in this viewport. Scrolling down...")
            page.mouse.wheel(0, 800)
            time.sleep(2)
            consecutive_empty_scrolls += 1
            continue
            
        consecutive_empty_scrolls = 0
        print(f"Found {len(connect_buttons)} 'Connect' buttons in viewport.")
        
        for btn in connect_buttons:
            if success_count >= target_count:
                break
                
            print(f"\n--- Processing Profile {success_count + 1} ---")
            
            # Click the 'Connect' button
            # We add a small offset to ensure we hit the center of the button
            clicker.click(btn["x"], btn["y"])
            time.sleep(2)
            
            # Handle the modal
            # Note: We use flow_key="linkedin_connect" so we inherit its modal knowledge
            # Hybrid DOM+OCR mapping: constrain OCR search to the modal bounding box
            try:
                modal_bounds = page.locator('div[role="dialog"]').first.bounding_box(timeout=2000)
            except:
                modal_bounds = None
            status = ocr_find_and_click("Send without a note", url, "linkedin_connect", retry=False, bounds=modal_bounds)
            
            if status == "success" or status == "agent_fixed":
                success_count += 1
                print(f"Successfully sent request {success_count}/{target_count}!")
                time.sleep(2)
            else:
                print("Modal interaction failed. Dismissing modal...")
                img_modal = browser.screenshot()
                close_match = ocr.find("Dismiss", img_modal, exact=False, min_conf=0.4)
                if not close_match:
                    close_match = ocr.find("Cancel", img_modal, exact=False, min_conf=0.4)
                if close_match:
                    clicker.click(close_match["x"], close_match["y"])
                    time.sleep(1)
                    
        # After processing all buttons in this viewport, scroll down to find more
        if success_count < target_count:
            print("Scrolling down to find more profiles...")
            page.mouse.wheel(0, 800)
            time.sleep(2)
            
    if success_count < target_count:
        print(f"Goal not met! Wanted {target_count}, got {success_count}. Triggering AGENT_NEEDED...")
        from visor.core.runner import _signal_agent, FAILURES_DIR
        ss = browser.screenshot(save_path=os.path.join(FAILURES_DIR, f"goal_incomplete_{success_count}.png"))
        fix = _signal_agent(f"goal_not_met_{success_count}_of_{target_count}", url, ocr.summarize(ss) if ss else [], ss or "")
        
        # If the agent provides a fix (e.g. 'retry' after they manually changed code, or 'skip'), we can handle it
        if fix.get("action") == "retry":
            print("Agent applied a fix. Returning failed to trigger a top-level retry...")
        elif fix.get("action") == "skip":
            print("Agent decided to skip the rest of the goal.")
            return "success"
        
        return "failed"
        
    return "success"
