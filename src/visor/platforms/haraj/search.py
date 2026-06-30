"""
Haraj Search Flow

Goal: Search for an office chair and find the best deal.
"""

import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "haraj_search"

def search(url: str) -> str:
    """
    Returns: 'success' | 'skipped:<reason>' | 'failed'
    """
    browser.navigate(url)
    clicker.short_wait(3, 3)

    # Step 1: Find Search Box (Placeholder: ابحث عن سلعة)
    # We will use ocr_find_and_click to trigger the tree if it fails
    result = runner.ocr_find_and_click("ابحث عن سلعة", url, FLOW_KEY)
    if "skipped" in str(result):
        return result
    if result == "failed":
        return "failed"
        
    clicker.short_wait(1, 1)

    # Step 2: Type and search
    clicker.type_text("كرسي مكتب الرياض")
    clicker.press("Enter")
    clicker.short_wait(5, 2)

    # Step 3: Trigger AGENT_NEEDED to manually pick the best deal from the results.
    # We do this by searching for a dummy string that won't exist.
    result = runner.ocr_find_and_click("PICK_BEST_DEAL_NOW", url, FLOW_KEY)
    
    return "success"
