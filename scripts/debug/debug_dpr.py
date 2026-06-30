import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from visor.core import browser
res = browser.cmd("evaluate", {"code": "window.devicePixelRatio"})
print(res)
