"""
Test Flow Platform

Goal: Click the 'More information' button.
"""

from visor.core import browser, clicker, runner

FLOW_KEY = "test_flow"

def main(url: str = "https://example.com") -> str:
    """
    Returns: 'success' | 'skipped:<reason>' | 'failed'
    """
    browser.navigate(url)
    clicker.short_wait(3, 3)

    # Step 1: Find and click the 'More information' button
    # Based on SKILL.md rules, we MUST use OCR geometry instead of the hardcoded trace coordinates (x: 300, y: 400).
    result = runner.ocr_find_and_click("More information", url, FLOW_KEY)
    
    if "skipped" in str(result):
        return result
    if result == "failed":
        return "failed"
        
    clicker.short_wait(2, 2)

    return "success"
