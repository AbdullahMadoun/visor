"""
LinkedIn Connect Flow (Synthesized from Recording)

Goal: Connect to a person via search.
"""

import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "linkedin_connect"


def main(url: str) -> str:
    """
    Returns: 'success' | 'skipped:<reason>' | 'failed'
    """
    browser.navigate(url)
    clicker.short_wait(3, 3)

    # Dynamic data target extracted from the recorded trace
    target_query = 'ai engineering saudi "@"'

    # Step 1: Click the Search bar (static element)
    result = runner.ocr_find_and_click("Search", url, FLOW_KEY)
    if "skipped" in str(result):
        return result
    if result == "failed":
        return "failed"
        
    clicker.short_wait(2, 2)

    # Step 2: Click the target search query / suggestion (dynamic data target)
    result = runner.ocr_find_and_click(target_query, url, FLOW_KEY)
    if "skipped" in str(result):
        return result
    if result == "failed":
        return "failed"
        
    clicker.short_wait(5, 5)

    # Step 3: Find and click the Connect button (static element)
    # Note: Noise clicks from human recording (e.g., clicking "More", "4p") are omitted.
    result = runner.ocr_find_and_click("Connect", url, FLOW_KEY)
    if "skipped" in str(result):
        return result
    if result == "failed":
        return "failed"
        
    clicker.short_wait(3, 3)

    # Step 4: Verify the state is "Pending" (or handle "Send without a note" modal)
    if runner.verify_ocr("Pending"):
        return "success"
        
    # If a modal appeared (not present in the specific trace but common in LinkedIn)
    result = runner.ocr_find_and_click("Send without a note", url, FLOW_KEY)
    if result != "failed" and "skipped" not in str(result):
        clicker.short_wait(3, 3)
        if runner.verify_ocr("Pending"):
            return "success"
            
    # Verification failed — save screenshot for agent review
    ss = browser.screenshot(save_path=os.path.join(runner.FAILURES_DIR, "verify_linkedin_connect.png"))
    fix = runner._signal_agent("verify_Pending", url, ocr.summarize(ss) if ss else [], ss or "")
    
    if fix.get("action") == "skip":
        return f"skipped:{fix.get('reason', 'verify_failed')}"
        
    return "failed"
