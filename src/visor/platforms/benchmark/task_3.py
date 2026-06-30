import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "benchmark_task_3"

def run_task(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(4, 2)
    
    # 1. Search for "controllers"
    result = runner.ocr_find_and_click("Search games", url, FLOW_KEY)
    if result == "failed":
        # Fallback to general search
        result = runner.ocr_find_and_click("Search", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.type_text("controllers")
    clicker.press("Enter")
    
    clicker.human_wait(8, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_first_result", url, ocr.summarize(img_path), img_path)
    
    # 2. Trade-In page
    result = runner.ocr_find_and_click("Trade", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.human_wait(6, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_trade_in", url, ocr.summarize(img_path), img_path)
    
    # 3. Track Order
    result = runner.ocr_find_and_click("Track Order", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.human_wait(6, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_track_order", url, ocr.summarize(img_path), img_path)
    
    return "success"
