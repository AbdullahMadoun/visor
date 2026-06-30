import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core import ocr
img_path = os.path.join(PROJECT_ROOT, "job_debug.png")
if os.path.exists(img_path):
    items = ocr.find_all(img_path)
    for i in items:
        print(i["text"], i["confidence"])
else:
    print(f"Please place a screenshot at {img_path} to test OCR.")
