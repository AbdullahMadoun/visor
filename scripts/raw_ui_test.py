import json
import os
import time
import sys
import csv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from visor.core import browser, clicker, ocr

def inject_thought(page, text):
    escaped_text = text.replace("'", "\\'")
    page.evaluate(f"""
        let el = document.getElementById('agent-thought-overlay');
        if (!el) {{
            el = document.createElement('div');
            el.id = 'agent-thought-overlay';
            el.style.position = 'fixed';
            el.style.bottom = '20px';
            el.style.left = '20px';
            el.style.backgroundColor = 'rgba(0, 0, 0, 0.9)';
            el.style.color = '#00ff00';
            el.style.padding = '15px';
            el.style.zIndex = '9999999';
            el.style.fontSize = '22px';
            el.style.borderRadius = '8px';
            el.style.fontFamily = 'monospace';
            document.body.appendChild(el);
        }}
        el.innerText = 'QA Thought: {escaped_text}';
    """)
    print(f"[QA AGENT] {text}")
    page.wait_for_timeout(2500)

def highlight_click(page, x, y):
    page.evaluate(f"""
        let ratio = window.devicePixelRatio || 1;
        let cssX = {x} / ratio;
        let cssY = {y} / ratio;
        let pointer = document.createElement('div');
        pointer.style.position = 'absolute';
        pointer.style.width = '40px';
        pointer.style.height = '40px';
        pointer.style.backgroundColor = 'rgba(255, 0, 0, 0.4)';
        pointer.style.border = '4px solid red';
        pointer.style.borderRadius = '50%';
        pointer.style.zIndex = '9999999';
        pointer.style.pointerEvents = 'none';
        pointer.style.boxShadow = '0 0 15px red';
        pointer.style.transition = 'all 0.2s ease-out';
        
        pointer.style.left = (cssX + window.scrollX - 20) + 'px';
        pointer.style.top = (cssY + window.scrollY - 20) + 'px';
        
        document.body.appendChild(pointer);
        
        setTimeout(() => {{
            pointer.style.transform = 'scale(0.5)';
            pointer.style.backgroundColor = 'rgba(255, 0, 0, 0.8)';
        }}, 100);
        
        setTimeout(() => pointer.remove(), 1500);
    """)
    page.wait_for_timeout(1000)

def main():
    print("[SYSTEM] Initializing browser...")
    browser.init_browser(headless=False, record_video=True)
    page = browser.get_page()

    csv_path = os.path.join(os.getcwd(), "connection_log.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Profile URL', 'Job Post Snippet', 'Connection Status'])

    inject_thought(page, "Entering authenticated state via session cookies...")
    session_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "visor_workspace", "session.json")
    if os.path.exists(session_path):
        with open(session_path, 'r') as f:
            cookies = json.load(f).get('cookies', [])
            page.context.add_cookies(cookies)
    
    inject_thought(page, "Navigating to feed to commence search validation...")
    page.goto("https://www.linkedin.com/feed/")
    page.wait_for_timeout(4000)

    ss_path = os.path.join(os.getcwd(), "temp_qa.png")

    inject_thought(page, "Isolating Search component via OCR...")
    page.screenshot(path=ss_path)
    boxes = ocr.find_all(ss_path)
    search_box = next((b for b in boxes if b['text'].lower() == 'search'), None)

    if search_box:
        inject_thought(page, f"Search element acquired. Initiating click...")
        highlight_click(page, search_box['x'], search_box['y'])
        clicker.click(search_box['x'], search_box['y'])
        page.wait_for_timeout(500)
        
        inject_thought(page, "Injecting test query: 'AI engineer hiring @gmail.com'")
        page.keyboard.type("AI engineer hiring @gmail.com", delay=50)
        page.keyboard.press("Enter")
        page.wait_for_timeout(4000)
    else:
        inject_thought(page, "Search bar not detected. Test Failed.")
        return

    inject_thought(page, "Locating 'Posts' tab filter to isolate job posts...")
    page.screenshot(path=ss_path)
    boxes = ocr.find_all(ss_path)
    posts_tab = next((b for b in boxes if b['text'].lower() == 'posts'), None)
    if posts_tab:
        inject_thought(page, "Posts tab identified. Applying filter...")
        highlight_click(page, posts_tab['x'], posts_tab['y'])
        clicker.click(posts_tab['x'], posts_tab['y'])
        page.wait_for_timeout(7000)

    inject_thought(page, "Extracting post snippet and profile URL data using resilient locators...")
    extracted_data = page.evaluate('''() => {
        let results = [];
        let links = Array.from(document.querySelectorAll('a')).filter(a => a.href.includes('/in/') && !a.href.includes('/recent-activity'));
        for (let link of links) {
            let container = link.closest('div.feed-shared-update-v2, li.reusable-search__result-container, div.search-entity-media') || link.parentElement;
            results.push({
                url: link.href.split('?')[0],
                text: container ? container.innerText.substring(0, 300) : "Snippet unavailable"
            });
        }
        return results;
    }''')
    
    unique_profiles = {}
    for item in extracted_data:
        if item['url'] not in unique_profiles:
            unique_profiles[item['url']] = item['text']
            
    targets = list(unique_profiles.items())[:3]
    
    if not targets:
        inject_thought(page, "Data extraction yielded 0 profile targets. Test Failed.")
        return

    inject_thought(page, f"Extraction complete: {len(targets)} profiles loaded. Beginning transition test...")
    
    connected_count = 0
    
    for url, post_text in targets:
        inject_thought(page, f"Navigating to Target Profile: {url}")
        page.goto(url)
        page.wait_for_timeout(4000)
        
        status = "Failed"
        
        inject_thought(page, "Scanning profile DOM visually for 'Connect' node...")
        page.screenshot(path=ss_path)
        boxes = ocr.find_all(ss_path)
        connect_btn = next((b for b in boxes if b['text'].lower() == 'connect' and b['x'] < 1200), None)
        
        if connect_btn:
            inject_thought(page, "Target 'Connect' found. Firing click event...")
            highlight_click(page, connect_btn['x'], connect_btn['y'])
            clicker.click(connect_btn['x'], connect_btn['y'])
            page.wait_for_timeout(2000)
        else:
            inject_thought(page, "Connect button obscured. Hunting for 'More' dropdown...")
            more_btn = next((b for b in boxes if b['text'].lower() == 'more' and b['x'] < 1200), None)
            if more_btn:
                highlight_click(page, more_btn['x'], more_btn['y'])
                clicker.click(more_btn['x'], more_btn['y'])
                page.wait_for_timeout(2500)
                
                inject_thought(page, "Scanning expanded dropdown for Connect action...")
                page.screenshot(path=ss_path)
                boxes2 = ocr.find_all(ss_path)
                dropdown_connect = next((b for b in boxes2 if b['text'].lower() == 'connect'), None)
                if dropdown_connect:
                    inject_thought(page, "Connect action isolated in dropdown. Clicking...")
                    highlight_click(page, dropdown_connect['x'], dropdown_connect['y'])
                    clicker.click(dropdown_connect['x'], dropdown_connect['y'])
                    page.wait_for_timeout(2000)
                else:
                    inject_thought(page, "Connect action entirely absent. Marking Failed.")
            else:
                inject_thought(page, "No viable connection path visible. Marking Failed.")
        
        inject_thought(page, "Monitoring for 'Send without a note' interstitial modal...")
        page.screenshot(path=ss_path)
        boxes = ocr.find_all(ss_path)
        send_btn = next((b for b in boxes if 'send' in b['text'].lower()), None)
        
        if send_btn:
            inject_thought(page, "Modal detected. Bypassing note by clicking Send...")
            highlight_click(page, send_btn['x'], send_btn['y'])
            clicker.click(send_btn['x'], send_btn['y'])
            page.wait_for_timeout(2000)
            
            inject_thought(page, "Validating final transition to 'Pending' state...")
            page.screenshot(path=ss_path)
            boxes = ocr.find_all(ss_path)
            if any('pending' in b['text'].lower() for b in boxes):
                status = "Pending"
                connected_count += 1
                inject_thought(page, f"State Validation Passed: Profile -> Pending. ({connected_count}/3)")
            else:
                status = "Verification Failed"
                inject_thought(page, "State Validation Failed. Expected 'Pending' not visible.")
        else:
            inject_thought(page, "No interstitial modal triggered.")
            status = "No Modal"
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([url, post_text.replace('\\n', ' ').replace('\\r', '')[:200] + '...', status])

    inject_thought(page, f"Test Suite Complete. Total successful transition validations: {connected_count}/3")
    page.wait_for_timeout(3000)

if __name__ == "__main__":
    main()
