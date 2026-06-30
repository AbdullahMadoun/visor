import sys
import time
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core.browser import get_page, navigate, close
page = get_page()
navigate("https://www.linkedin.com/jobs/view/4424502726")
time.sleep(5)
page.screenshot(path=os.path.join(PROJECT_ROOT, "job_debug.png"))
close()
