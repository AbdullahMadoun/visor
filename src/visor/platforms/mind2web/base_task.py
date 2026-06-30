import sys
import os
from visor.core import browser, runner

def playwright_click(page, label: str, url: str, timeout: int = 3000):
    try:
        page.locator(f"text={label}").first.click(timeout=timeout)
        return True
    except Exception:
        ss_path = browser.screenshot()
        # signal agent
        runner._signal_agent(f"find_{label}", url, [], ss_path)
        # try again with standard playwright or skip
        return False
