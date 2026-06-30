import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core.ocr import find_all

items = find_all(os.path.join(PROJECT_ROOT, "job_debug.png"))
for item in items:
    if "easy" in item["text"].lower():
        print(item)
