import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "benchmark_task_1"

def run_task(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(3, 3)

    # Step 1
    result = runner.ocr_find_and_click("Job title, keywords, or company", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.type_text("warehouse associate")
    
    result = runner.ocr_find_and_click("City, state, zip code, or \"remote\"", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.type_text("Chicago, IL")
    
    result = runner.ocr_find_and_click("Find jobs", url, FLOW_KEY)
    if result == "failed": return "failed"

    clicker.short_wait(4, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_search_result", url, ocr.summarize(img_path), img_path)
    
    # Step 2
    result = runner.ocr_find_and_click("Find salaries", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.short_wait(4, 2)
    result = runner.ocr_find_and_click("Job title", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.type_text("software engineer")
    
    result = runner.ocr_find_and_click("Search", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.short_wait(4, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_salary", url, ocr.summarize(img_path), img_path)

    # Step 3
    result = runner.ocr_find_and_click("Career Guide", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.short_wait(4, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_career_guide", url, ocr.summarize(img_path), img_path)
    
    return "success"
