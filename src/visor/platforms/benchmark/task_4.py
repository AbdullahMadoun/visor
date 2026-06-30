import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "benchmark_task_4"

def run_task(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(4, 2)
    
    # 1. Search for "What is the tallest..."
    result = runner.ocr_find_and_click("Search anything", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.type_text("What is the tallest building in the world and when was it completed")
    clicker.press("Enter")
    
    clicker.human_wait(15, 5) # wait for answer
    img_path = browser.screenshot()
    runner._signal_agent("read_first_answer", url, ocr.summarize(img_path), img_path)
    
    # 2. Pro page
    result = runner.ocr_find_and_click("Try Pro", url, FLOW_KEY)
    if result == "failed":
        result = runner.ocr_find_and_click("Pro", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.short_wait(4, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_pro_page", url, ocr.summarize(img_path), img_path)
    
    # 3. Second search
    browser.navigate(url)
    clicker.short_wait(4, 2)
    result = runner.ocr_find_and_click("Search anything", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.type_text("Compare the populations of Tokyo, Delhi, and Shanghai")
    clicker.press("Enter")
    
    clicker.human_wait(15, 5)
    img_path = browser.screenshot()
    runner._signal_agent("read_second_answer", url, ocr.summarize(img_path), img_path)
    
    return "success"
