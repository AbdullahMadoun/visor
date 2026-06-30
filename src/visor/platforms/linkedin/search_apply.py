"""
LinkedIn Search and Apply Flow

Goal: Search for jobs, click on them, and apply.
"""

import sys
import os
import time

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "linkedin_search_apply"

def apply(dummy_url: str) -> str:
    # 1. Navigate to jobs search
    url = "https://www.linkedin.com/jobs/search/?keywords=Computer%20Vision%20Engineer&location=Worldwide&f_AL=true"
    browser.navigate(url)
    clicker.short_wait(4, 3)

    # 2. Find a job card that hasn't been clicked (using OCR text)
    ss = browser.screenshot()
    text_list = ocr.summarize(ss) if ss else []
    
    # Trigger AGENT_NEEDED to let the subagent build the robust tree
    fix = runner._signal_agent("search_and_click", url, text_list, ss or "")
    if fix.get("action") == "skip":
        return f"skipped:{fix.get('reason', 'no_jobs')}"
        
    return "success"
