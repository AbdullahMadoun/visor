import sys
import os

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "benchmark_task_5"

def run_task(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(4, 2)
    
    # 1. Ask question
    result = runner.ocr_find_and_click("Ask anything", url, FLOW_KEY)
    if result == "failed": return "failed"
    clicker.type_text("List the five longest rivers in Africa by length")
    clicker.press("Enter")
    
    clicker.human_wait(15, 5) # wait for answer
    img_path = browser.screenshot()
    runner._signal_agent("read_first_answer", url, ocr.summarize(img_path), img_path)
    
    # 2. Pricing
    result = runner.ocr_find_and_click("Pricing", url, FLOW_KEY)
    if result == "failed":
        result = runner.ocr_find_and_click("See plans and pricing", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.short_wait(4, 2)
    img_path = browser.screenshot()
    runner._signal_agent("read_pricing", url, ocr.summarize(img_path), img_path)
    
    # 3. Ask another question
    browser.navigate(url)
    clicker.short_wait(4, 2)
    result = runner.ocr_find_and_click("Ask anything", url, FLOW_KEY)
    if result == "failed": return "failed"
    
    clicker.type_text("What is the boiling point of water at sea level in Fahrenheit and Celsius")
    clicker.press("Enter")
    
    clicker.human_wait(15, 5)
    img_path = browser.screenshot()
    runner._signal_agent("read_second_answer", url, ocr.summarize(img_path), img_path)
    
    return "success"
