import sys
import time
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core.browser import get_page, navigate

def run_probe():
    print("[PROBE] Starting...")
    page = get_page()
    url = 'https://www.linkedin.com/jobs/view/4424502726'
    print(f"[PROBE] Navigating to {url}")
    navigate(url)
    time.sleep(5)
    
    print("[PROBE] Clicking Easy Apply...")
    try:
        btn = page.locator('button.jobs-apply-button--top-card, button[aria-label*="Easy Apply"], button.jobs-apply-button').first
        btn.click(timeout=10000)
    except Exception as e:
        print(f"[PROBE] Failed to click Easy Apply: {e}")
        return

    time.sleep(3)
    
    print("[PROBE] Clicking Next on Step 1...")
    try:
        next_btn = page.locator('button.artdeco-button--primary:has-text("Next"), footer button:has-text("Next"), div[role="dialog"] button:has-text("Next")').first
        next_btn.click(timeout=10000)
    except Exception as e:
        print(f"[PROBE] Failed to click Next: {e}")
    
    time.sleep(3)
    
    print("[PROBE] Extracting Body HTML for Resume step...")
    try:
        modal_html = page.evaluate("() => document.body.innerHTML")
        with open(os.path.join(PROJECT_ROOT, 'modal_resume_step.html'), 'w', encoding='utf-8') as f:
            f.write(modal_html)
        print("[PROBE] Successfully saved body HTML")
        
        page.screenshot(path=os.path.join(PROJECT_ROOT, "probe_resume.png"))
        print("[PROBE] Saved screenshot to probe_resume.png")
    except Exception as e:
        print(f"[PROBE] Failed to extract body HTML: {e}")

if __name__ == '__main__':
    run_probe()
