import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core import ocr, browser
page = browser.get_page()
img = browser.screenshot()
items = ocr.find_all(img)
for i in items:
    print(f"{i['text']} (x={i['x']}, y={i['y']}, conf={i['confidence']})")
