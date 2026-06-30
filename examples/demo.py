"""
Visor Self-Healing Demo 🚀

This script demonstrates the core magic of Visor: 
1. Hijacking a local Chromium browser session.
2. Navigating to Hacker News.
3. Using pure OCR (via EasyOCR) to find and click a button without ever looking at the brittle DOM.
"""

import time
from visor.core import browser, ocr, clicker

def main():
    print("\n🤖 [Visor] Starting Demo...")
    
    url = "https://news.ycombinator.com/"
    print(f"🌍 Navigating to {url}...")
    browser.navigate(url)
    
    time.sleep(2) # Wait for render
    
    print("📸 Taking a screenshot...")
    img_path = browser.screenshot()
    
    if not img_path:
        print("❌ Could not take screenshot. Is Chromium running with --remote-debugging-port=9222?")
        return

    target_text = "login"
    print(f"🔍 Using AI/OCR to find '{target_text}' visually, ignoring the DOM...")
    
    match = ocr.find(target_text, img_path, exact=False)
    
    if match:
        print(f"✅ Found '{target_text}' at coordinates (X: {match['x']}, Y: {match['y']}) with {match['confidence']:.2f} confidence.")
        print("🖱️  Injecting low-level CDP Click...")
        clicker.click(match["x"], match["y"])
        print("🎉 Success! The click bypassed Playwright's actionability checks and executed natively.")
    else:
        print(f"❌ Could not find '{target_text}' via OCR. Ensure the page loaded correctly.")

if __name__ == "__main__":
    main()
