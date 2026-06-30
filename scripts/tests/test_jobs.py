import sys
import time
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core.browser import get_page, navigate, close

def test():
    page = get_page()
    navigate("https://www.linkedin.com/jobs/search/?keywords=Computer%20Vision%20Engineer")
    time.sleep(5)
    page.screenshot(path=os.path.join(PROJECT_ROOT, "jobs_debug.png"))
    with open(os.path.join(PROJECT_ROOT, "jobs_dom.html"), "w") as f:
        f.write(page.content())
    close()
test()
