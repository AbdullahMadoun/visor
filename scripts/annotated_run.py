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
        el.innerText = 'Agent Thought: {escaped_text}';
    """)
    print(f"[AGENT] {text}")
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
        writer.writerow(['Profile URL', 'Job Post Info', 'Connection Status'])

    inject_thought(page, "Booting up fresh context. Injecting session cookies...")
    session_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "visor_workspace", "session.json")
    if os.path.exists(session_path):
        with open(session_path, 'r') as f:
            cookies = json.load(f).get('cookies', [])
            page.context.add_cookies(cookies)
    
    inject_thought(page, "Navigating to LinkedIn feed...")
    page.goto("https://www.linkedin.com/feed/")
    page.wait_for_timeout(4000)

    ss_path = os.path.join(os.getcwd(), "temp_agent.png")

    inject_thought(page, "Running OCR to find the Search bar natively...")
    page.screenshot(path=ss_path)
    boxes = ocr.find_all(ss_path)
    search_box = next((b for b in boxes if b['text'].lower() == 'search'), None)

    if search_box:
        inject_thought(page, f"Found Search box. Hovering and clicking...")
        highlight_click(page, search_box['x'], search_box['y'])
        clicker.click(search_box['x'], search_box['y'])
        page.wait_for_timeout(500)
        
        inject_thought(page, "Typing generalized query: 'AI engineer hiring @gmail.com'")
        page.keyboard.type("AI engineer hiring @gmail.com", delay=50)
        page.keyboard.press("Enter")
        page.wait_for_timeout(4000)
    else:
        inject_thought(page, "Could not find Search bar. Aborting.")
        return

    inject_thought(page, "Scanning results to filter by 'Posts' tab...")
    page.screenshot(path=ss_path)
    boxes = ocr.find_all(ss_path)
    posts_tab = next((b for b in boxes if b['text'].lower() == 'posts'), None)
    if posts_tab:
        inject_thought(page, "Found Posts tab. Clicking...")
        highlight_click(page, posts_tab['x'], posts_tab['y'])
        clicker.click(posts_tab['x'], posts_tab['y'])
        page.wait_for_timeout(4000)

    inject_thought(page, "Extracting post data and profile URLs from the feed...")
    extracted_data = page.evaluate('''() => {
        let results = [];
        let containers = document.querySelectorAll('.feed-shared-update-v2');
        for (let i = 0; i < containers.length; i++) {
            let textEl = containers[i].querySelector('.update-components-text');
            let linkEl = containers[i].querySelector('a.app-aware-link');
            if (textEl && linkEl) {
                let href = linkEl.href;
                if (href.includes('/in/')) {
                    results.push({
                        url: href.split('?')[0],
                        text: textEl.innerText
                    });
                }
            }
        }
        return results;
    }''')
    
    unique_profiles = {}
    for item in extracted_data:
        if item['url'] not in unique_profiles:
            unique_profiles[item['url']] = item['text']
            
    targets = list(unique_profiles.items())[:3]
    
    if not targets:
        inject_thought(page, "No profile URLs extracted. Exiting.")
        return

    inject_thought(page, f"Extracted {len(targets)} targets. Initiating profile connection loop...")
    
    connected_count = 0
    
    for url, post_text in targets:
        inject_thought(page, f"Opening profile: {url}")
        page.goto(url)
        page.wait_for_timeout(4000)
        
        status = "Failed"
        
        inject_thought(page, "Scanning profile for Connect button via OCR...")
        page.screenshot(path=ss_path)
        boxes = ocr.find_all(ss_path)
        connect_btn = next((b for b in boxes if b['text'].lower() == 'connect' and b['x'] < 1200), None)
        
        if connect_btn:
            inject_thought(page, "Found primary Connect button. Engaging...")
            highlight_click(page, connect_btn['x'], connect_btn['y'])
            clicker.click(connect_btn['x'], connect_btn['y'])
            page.wait_for_timeout(2000)
        else:
            inject_thought(page, "Connect not visible. Searching for 'More' dropdown...")
            more_btn = next((b for b in boxes if b['text'].lower() == 'more' and b['x'] < 1200), None)
            if more_btn:
                highlight_click(page, more_btn['x'], more_btn['y'])
                clicker.click(more_btn['x'], more_btn['y'])
                page.wait_for_timeout(2500)
                
                inject_thought(page, "Scanning dropdown for Connect option...")
                page.screenshot(path=ss_path)
                boxes2 = ocr.find_all(ss_path)
                dropdown_connect = next((b for b in boxes2 if b['text'].lower() == 'connect'), None)
                if dropdown_connect:
                    inject_thought(page, "Found Connect in dropdown. Clicking...")
                    highlight_click(page, dropdown_connect['x'], dropdown_connect['y'])
                    clicker.click(dropdown_connect['x'], dropdown_connect['y'])
                    page.wait_for_timeout(2000)
                else:
                    inject_thought(page, "Connect not found in dropdown. Logging Failed.")
            else:
                inject_thought(page, "Neither Connect nor More found. Logging Failed.")
        
        inject_thought(page, "Scanning for 'Send without a note' modal...")
        page.screenshot(path=ss_path)
        boxes = ocr.find_all(ss_path)
        send_btn = next((b for b in boxes if 'send' in b['text'].lower()), None)
        
        if send_btn:
            inject_thought(page, "Modal found. Clicking Send...")
            highlight_click(page, send_btn['x'], send_btn['y'])
            clicker.click(send_btn['x'], send_btn['y'])
            page.wait_for_timeout(2000)
            
            inject_thought(page, "Verifying UI transition to 'Pending' via OCR...")
            page.screenshot(path=ss_path)
            boxes = ocr.find_all(ss_path)
            if any('pending' in b['text'].lower() for b in boxes):
                status = "Pending"
                connected_count += 1
                inject_thought(page, f"Verified Pending state. Progress: {connected_count}/3")
            else:
                status = "Verification Failed"
                inject_thought(page, "Pending text not found.")
        else:
            inject_thought(page, "No send modal detected.")
            status = "No Modal"
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([url, post_text.replace('\\n', ' ').replace('\\r', '')[:200] + '...', status])

    inject_thought(page, f"Objective Complete! Processed {len(targets)} targets. Verified Connections: {connected_count}")
    page.wait_for_timeout(3000)

if __name__ == "__main__":
    main()
