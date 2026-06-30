import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "benchmark_task_2"

def run_task(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(4, 2)
    
    # Step 1
    result = runner.ocr_find_and_click("Message Copilot", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.type_text("What are the three largest deserts in the world by area")
    clicker.press("Enter")
    
    clicker.human_wait(15, 5) # wait for response
    img_path = browser.screenshot()
    runner._signal_agent("read_first_answer", url, ocr.summarize(img_path), img_path)
    
    # Step 2
    result = runner.ocr_find_and_click("Privacy", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.short_wait(4, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_privacy", url, ocr.summarize(img_path), img_path)
    
    # Step 3
    browser.navigate(url)
    clicker.short_wait(4, 2)
    result = runner.ocr_find_and_click("Message Copilot", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.type_text("Convert 450 kilometers to miles")
    clicker.press("Enter")
    
    clicker.human_wait(15, 5) # wait for response
    img_path = browser.screenshot()
    runner._signal_agent("read_second_answer", url, ocr.summarize(img_path), img_path)
    
    return "success"
