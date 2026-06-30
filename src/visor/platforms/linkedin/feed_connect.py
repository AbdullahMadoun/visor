import time
from visor.core import browser, ocr, clicker
from visor.core.runner import ocr_find_and_click

def feed_connect(url: str) -> str:
    page = browser.get_page()
    browser.navigate(url)
    time.sleep(3)
    
    connections_made = 0
    visited_y = set()
    
    for _ in range(5):
        if connections_made >= 3:
            break
            
        img = browser.screenshot()
        # Find post authors by looking for "3rd+"
        matches = ocr.find_all(img)
        authors = [m for m in matches if "3rd+" in m["text"] or "2nd" in m["text"]]
        
        for author in authors:
            if connections_made >= 3:
                break
            
            # Avoid clicking the same vertical area again in the same viewport
            if any(abs(author["y"] - vy) < 50 for vy in visited_y):
                continue
                
            visited_y.add(author["y"])
            
            # Click author
            clicker.click(author["x"], author["y"])
            time.sleep(4)
            
            # Now we are on their profile. Look for Connect button
            # We use runner's ocr_find_and_click to leverage self-healing
            status = ocr_find_and_click("Connect", url, "linkedin_feed_connect", retry=True)
            
            if status in ["success", "agent_fixed"]:
                # The connect modal might open, we need to click "Send without a note" or "Send"
                time.sleep(2)
                
                # Check for "Send without a note" or "Send"
                send_status = ocr_find_and_click("Send without a note", url, "linkedin_feed_connect", retry=True)
                if send_status == "failed":
                    send_status = ocr_find_and_click("Send", url, "linkedin_feed_connect", retry=True)
                
                print(f"[feed_connect] Connection {connections_made + 1} sent!")
                connections_made += 1
            
            # Go back to feed
            page.go_back()
            time.sleep(3)
        
        # Scroll down for more posts
        page.mouse.wheel(0, 800)
        time.sleep(2)
        # Clear visited_y because coordinates changed
        visited_y.clear()

    if connections_made >= 3:
        return "success"
    return "failed"
