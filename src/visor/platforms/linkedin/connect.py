"""
LinkedIn Connect Flow

Goal: Send a connection request to a LinkedIn profile.
Success criteria: Page shows "Pending" after send.

Steps:
  1. Navigate to profile
  2. OCR find "Connect" → CDP click
  3. OCR find "Send without a note" → CDP click
  4. Reload → OCR verify "Pending"
"""

import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "linkedin_connect"


def connect(profile_url: str) -> str:
    """
    Returns: 'success' | 'skipped:<reason>' | 'failed'
    """
    browser.navigate(profile_url)
    clicker.short_wait(3, 3)  # wait for page load

    # Step 1: Find the Connect button
    result = runner.ocr_find_and_click("Connect", profile_url, FLOW_KEY)
    if "skipped" in str(result):
        return result
    if result == "failed":
        return "failed"

    clicker.short_wait(2, 2)

    # Step 2: Find and click Send without a note
    result = runner.ocr_find_and_click("Send without a note", profile_url, FLOW_KEY)
    if "skipped" in str(result):
        return result
    if result == "failed":
        # Try plain "Send"
        result = runner.ocr_find_and_click("Send", profile_url, FLOW_KEY)
        if "skipped" in str(result):
            return result
    if result == "failed":
        return "failed"

    clicker.short_wait(2, 2)

    # Step 3: Reload and verify Pending
    browser.navigate(profile_url)
    clicker.short_wait(4, 2)

    if runner.verify_ocr("Pending"):
        return "success"

    # Verification failed — save all screenshots for agent review
    ss = browser.screenshot(save_path=os.path.join(runner.FAILURES_DIR, f"verify_{profile_url.split('/')[-1]}.png"))
    fix = runner._signal_agent("verify_Pending", profile_url,
                               ocr.summarize(ss) if ss else [], ss or "")
    if fix.get("action") == "skip":
        return f"skipped:{fix.get('reason', 'verify_failed')}"
    return "failed"
