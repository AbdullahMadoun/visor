import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core.ocr import find

match = find("Easy Apply", os.path.join(PROJECT_ROOT, "job_debug.png"), exact=False, min_conf=0.3)
print("Match result:", match)
