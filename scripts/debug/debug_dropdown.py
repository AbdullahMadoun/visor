import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))
from visor.core import browser, ocr, clicker

browser.navigate("https://www.linkedin.com/in/lanchuhuong/")
time.sleep(4)
page = browser.get_page()
bounds = page.locator("section.artdeco-card").first.bounding_box()
match = ocr.find("More", browser.screenshot(), exact=True, bounds=bounds)
if match:
    clicker.click(match["x"], match["y"])
    time.sleep(2)
    path = browser.screenshot(save_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "debug_dropdown.png"))
    print(f"Saved to {path}")
    print(ocr.summarize(path))
else:
    print("More not found")
