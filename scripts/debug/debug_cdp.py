import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from visor.core import browser
res = browser.cmd("evaluate", {"code": "return typeof window._playwright_click === 'function'"})
print(res)
