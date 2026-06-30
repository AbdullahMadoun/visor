import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from visor.core import browser, ocr
import time

page = browser.get_page()
browser.navigate("https://www.linkedin.com/in/akash-goyal-/")
time.sleep(4)
img = browser.screenshot()
print(ocr.summarize(img))
browser.close()
