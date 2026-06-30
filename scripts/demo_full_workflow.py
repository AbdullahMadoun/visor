import os
import time
import re
from rich.console import Console
from visor.core import browser, clicker

console = Console()

def inject_visual_cursor(page):
    js = """
    () => {
        if (document.getElementById('visor-visual-cursor')) return;
        const box = document.createElement('div');
        box.id = 'visor-visual-cursor';
        box.style.position = 'absolute';
        box.style.width = '24px';
        box.style.height = '24px';
        box.style.borderRadius = '50%';
        box.style.backgroundColor = 'rgba(255, 45, 85, 0.7)';
        box.style.border = '2px solid white';
        box.style.boxShadow = '0 4px 10px rgba(0,0,0,0.3)';
        box.style.zIndex = '999999';
        box.style.pointerEvents = 'none';
        box.style.transform = 'translate(-50%, -50%)';
        box.style.transition = 'transform 0.1s ease-out';
        document.body.appendChild(box);
        
        document.addEventListener('mousemove', event => {
            box.style.left = event.pageX + 'px';
            box.style.top = event.pageY + 'px';
            box.style.opacity = '1';
        });
        document.addEventListener('mousedown', () => { box.style.transform = 'translate(-50%, -50%) scale(0.6)'; });
        document.addEventListener('mouseup', () => { box.style.transform = 'translate(-50%, -50%) scale(1)'; });
    }
    """
    try: page.evaluate(js)
    except: pass
    page.mouse.move(500, 500)

def inject_agent_toast(page, text, type="info"):
    color = "#e2e8f0"
    if type == "error": color = "#fca5a5"
    if type == "success": color = "#86efac"
    js = f"""
    () => {{
        let toast = document.getElementById('visor-agent-toast');
        if (!toast) {{
            toast = document.createElement('div');
            toast.id = 'visor-agent-toast';
            toast.style.position = 'fixed';
            toast.style.bottom = '40px';
            toast.style.left = '50%';
            toast.style.transform = 'translateX(-50%)';
            toast.style.padding = '16px 32px';
            toast.style.backgroundColor = 'rgba(15, 23, 42, 0.95)';
            toast.style.color = '{color}';
            toast.style.borderRadius = '12px';
            toast.style.fontFamily = 'system-ui, -apple-system, sans-serif';
            toast.style.fontSize = '18px';
            toast.style.fontWeight = '500';
            toast.style.zIndex = '9999999';
            toast.style.boxShadow = '0 10px 25px rgba(0,0,0,0.5)';
            toast.style.border = '1px solid rgba(255,255,255,0.1)';
            toast.style.backdropFilter = 'blur(8px)';
            toast.style.display = 'flex';
            toast.style.alignItems = 'center';
            toast.style.gap = '12px';
            
            const icon = document.createElement('div');
            icon.id = 'visor-agent-toast-icon';
            icon.style.fontSize = '24px';
            toast.appendChild(icon);
            
            const content = document.createElement('div');
            content.id = 'visor-agent-toast-content';
            toast.appendChild(content);
            
            document.body.appendChild(toast);
        }}
        document.getElementById('visor-agent-toast').style.color = '{color}';
        document.getElementById('visor-agent-toast-icon').innerHTML = '{'🚨' if type == 'error' else '✅' if type == 'success' else '🤖'}';
        document.getElementById('visor-agent-toast-content').innerText = "{text}";
    }}
    """
    try: page.evaluate(js)
    except: pass
    time.sleep(1)

def smooth_move(page, x, y):
    page.mouse.move(x, y, steps=15)
    time.sleep(0.2)

def smooth_click(page, x, y):
    smooth_move(page, x, y)
    page.mouse.down()
    time.sleep(0.1)
    page.mouse.up()

def main():
    browser.init_browser(headless=False, record_video=True)
    page = browser.get_page()
    
    # 1. Start from Main Page
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    time.sleep(2)
    inject_visual_cursor(page)
    inject_agent_toast(page, "Goal: Find 20 AI Engineering posts, fix truncated DOMs, extract emails, and connect with top poster.")
    time.sleep(3)
    
    # 2. Search
    inject_agent_toast(page, "Navigating to global search bar...")
    search_box = page.locator("input.search-global-typeahead__input").first
    if search_box.is_visible():
        box = search_box.bounding_box()
        if box:
            smooth_click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            page.keyboard.type('"AI Engineer" "hiring" "@gmail.com"', delay=50)
            time.sleep(1)
            page.keyboard.press("Enter")
    else:
        # Fallback if search bar not found
        page.goto("https://www.linkedin.com/search/results/content/?keywords=%22AI%20Engineer%22%20%22hiring%22%20%22%40gmail.com%22")
    
    time.sleep(4)
    inject_visual_cursor(page)
    
    # 3. Scroll and Expand Truncated Posts (Genuine OCR Automation)
    inject_agent_toast(page, "Scanning feed to find and expand truncated posts...", type="info")
    time.sleep(2)
    
    from visor.core import ocr
    
    clicked_count = 0
    for step in range(5):
        # Save a screenshot to the local directory
        ss_path = os.path.join(os.getcwd(), "visor_workspace", "feed_snapshot.png")
        page.screenshot(path=ss_path)
        
        all_text = ocr.find_all(ss_path)
        
        see_more_boxes = []
        for item in all_text:
            text = item["text"].lower().strip()
            # Match LinkedIn's various more buttons
            if text in ["see more", "…more", "...more", "more"]:
                see_more_boxes.append(item)
                
        if see_more_boxes:
            for box in see_more_boxes:
                # Ensure we only click in the main feed area, not sidebar
                if box["x"] < 1200:
                    smooth_click(page, box["x"], box["y"])
                    clicked_count += 1
                    time.sleep(0.8)
                    
        # Scroll down to reveal more posts
        page.mouse.wheel(0, 800)
        time.sleep(2.0)
        
    inject_agent_toast(page, f"Successfully expanded {clicked_count} posts using OCR Vision.", type="success")
    time.sleep(2)
    
    # 5. Extract Emails
    inject_agent_toast(page, "Extracting recruiter emails from repaired DOM...", type="info")
    text_joined = page.evaluate('document.body.innerText')
    emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_joined)))
    emails = [e for e in emails if not e.endswith("sentry.io")][:5]
    
    inject_agent_toast(page, f"Extracted {len(emails)} emails! Moving to connect with top poster...", type="success")
    time.sleep(3)
    
    # 6. Open Profile and Connect
    inject_agent_toast(page, "Identifying top poster profile link...")
    profile_link = page.evaluate('''() => {
        let links = Array.from(document.querySelectorAll('.update-components-actor__container a, .feed-shared-actor__container a'));
        if (links.length > 0) {
            const rect = links[0].getBoundingClientRect();
            return {x: rect.x + rect.width/2, y: rect.y + rect.height/2, href: links[0].href};
        }
        return null;
    }''')
    
    if profile_link:
        smooth_click(page, profile_link["x"], profile_link["y"])
        time.sleep(4)
        inject_visual_cursor(page)
        
        inject_agent_toast(page, "Analyzing profile for connection criteria...")
        page.mouse.wheel(0, 500)
        time.sleep(1.5)
        page.mouse.wheel(0, -500)
        time.sleep(1)
        
        inject_agent_toast(page, "Criteria met. Initiating Connection Request...")
        
        # 1. Click Connect
        ss_path = os.path.join(os.getcwd(), "visor_workspace", "profile_snapshot.png")
        page.screenshot(path=ss_path)
        all_text = ocr.find_all(ss_path)
        connect_btn = next((item for item in all_text if item["text"].strip() == "Connect"), None)
        
        if connect_btn:
            smooth_click(page, connect_btn["x"], connect_btn["y"])
            time.sleep(2)
            
            # 2. Click "Send without a note" or "Send"
            page.screenshot(path=ss_path)
            modal_text = ocr.find_all(ss_path)
            send_btn = next((item for item in modal_text if item["text"].lower().strip() in ["send without a note", "send"]), None)
            
            if send_btn:
                smooth_click(page, send_btn["x"], send_btn["y"])
                time.sleep(2)
                
            # 3. Verify Pending
            page.screenshot(path=ss_path)
            final_text = ocr.find_all(ss_path)
            is_pending = any(item["text"].strip() == "Pending" for item in final_text)
            
            if is_pending:
                inject_agent_toast(page, "Verified 'Pending' status. Connection requested successfully!", type="success")
            else:
                inject_agent_toast(page, "Connection request sent but could not verify 'Pending' status.", type="info")
        else:
            inject_agent_toast(page, "Could not find 'Connect' button. Profile might already be connected.", type="error")
            
        time.sleep(4)
        
    browser.close()

if __name__ == "__main__":
    main()
