import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core import ocr

path = os.path.join(PROJECT_ROOT, "logs", "debug_dropdown.png")
if os.path.exists(path):
    matches = ocr.find_all(path)
    for m in matches:
        if "More" in m["text"]:
            print(f"Text: '{m['text']}', box: ({m['x1']},{m['y1']}) to ({m['x2']},{m['y2']}), center: ({m['x']},{m['y']})")
else:
    print(f"File not found: {path}")
