import os
import sys
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from visor.core import browser, ocr, clicker

MSG = """Hi Akash,

I saw your work on Mavriq AI and SaaS platforms. I'm really interested in GenAI entrepreneurship and was wondering how you broke into the startup space. Would love to learn from your journey. Please let me know if you are open to a quick chat or if you need any help with your current projects!

Thanks!"""

def main():
    print("Navigating to Akash...")
    browser.navigate("https://www.linkedin.com/in/akash-goyal-/")
    time.sleep(4)

    img = browser.screenshot()
    print("Finding 'Message' button...")
    # Use Hybrid DOM+OCR mapping to limit search to the main profile card, avoiding the top navbar
    page = browser.get_page()
    bounds = page.locator("section.artdeco-card").first.bounding_box()
    match = ocr.find("Message", img, exact=True, bounds=bounds)
    
    if not match:
        print("Could not find Message on profile card. Trying leftmost.")
        match = ocr.find("Message", img, exact=True)
        
    if match:
        clicker.click(match["x"], match["y"])
        print("Clicked Message. Waiting for chat popup...")
        time.sleep(3)
        
        print("Clicking text box to focus...")
        img2 = browser.screenshot()
        # Find 'Write' or 'message' to locate the input box
        box_match = ocr.find("Write", img2, exact=False, min_conf=0.4)
        if not box_match:
            box_match = ocr.find("message", img2, exact=False, min_conf=0.4)
            
        if box_match:
            # Click slightly below the text to hit the middle of the input box
            clicker.click(box_match["x"], box_match["y"] + 10)
            time.sleep(1)
        else:
            print("Could not find input box placeholder, typing anyway...")
        
        print("Typing message...")
        clicker.type_text(MSG)
        time.sleep(1)
        
        print("Clicking Send...")
        img3 = browser.screenshot()
        send_match = ocr.find("Send", img3, exact=True, min_conf=0.6)
        if send_match:
            # We want the Send button inside the chat popup (bottom right)
            # The chat popup is at the bottom right, so 'Send' will have a high X and high Y
            all_sends = [item for item in ocr.find_all(img3) if "send" in item["text"].lower() and item["confidence"] > 0.6]
            if all_sends:
                # Pick the bottom-right-most Send
                bottom_right_send = max(all_sends, key=lambda i: i["x"] + i["y"])
                clicker.click(bottom_right_send["x"], bottom_right_send["y"])
                print("Clicked Send!")
                time.sleep(3)
                
                # VERIFICATION STEP
                print("[VERIFY] Checking if message was sent...")
                img4 = browser.screenshot()
                all_text = ocr.summarize(img4)
                
                # Check 1: Is our exact message text visible as a sent bubble?
                # OCR might break the text into multiple blocks, so we check for fragments
                snippet = "Mavriq AI"
                snippet2 = "startup space"
                
                if any(snippet.lower() in t.lower() for t in all_text) and any(snippet2.lower() in t.lower() for t in all_text):
                    print("[RESULT] Message confirmed sent! Snippets found in chat history.")
                else:
                    print(f"[RESULT] FAILED! Text not found. Visible text: {all_text}")
                    # Escalation or retry logic would go here in the main framework
            else:
                print("Could not find 'Send' button.")
        else:
            print("Could not find 'Send'.")
    else:
        print("Failed to click Message.")
        
    browser.close()

if __name__ == "__main__":
    main()
