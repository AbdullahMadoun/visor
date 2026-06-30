import os
import time
import re
from rich.console import Console
from visor.core import browser, clicker
from visor.core import ocr

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
    
    html_text = text.replace('\n', '<br>')
    
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
        document.getElementById('visor-agent-toast-content').innerHTML = `{html_text}`;
    }}
    """
    try: page.evaluate(js)
    except: pass
    print(f"[AGENT] {text}")
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
    time.sleep(3)
    inject_visual_cursor(page)
    inject_agent_toast(page, "Goal: Find AI Engineering posts, use true OCR for hidden text, track stats, and connect.")
    time.sleep(3)
    
    # 2. Search via actual UI element using Vision
    inject_agent_toast(page, "Locating global search bar using Vision OCR...")
    ss_path = os.path.join(os.getcwd(), "visor_workspace", "feed_snapshot.png")
    page.screenshot(path=ss_path)
    
    from visor.core import ocr
    all_text = ocr.find_all(ss_path)
    search_box = None
    for item in all_text:
        if item["text"].lower().strip() == "search":
            search_box = item
            break
            
    if search_box:
        smooth_click(page, search_box["x"], search_box["y"])
        inject_agent_toast(page, "Typing search query natively...")
        page.keyboard.type('"AI Engineer" "hiring" "@gmail.com"', delay=30)
        time.sleep(1)
        page.keyboard.press("Enter")
        time.sleep(5)
    else:
        inject_agent_toast(page, "Could not visually locate search bar. Falling back to URL...", type="error")
        page.goto('https://www.linkedin.com/search/results/content/?keywords="AI%20Engineer"%20"hiring"%20"@gmail.com"')
        time.sleep(4)
    
    # Switch to "Posts" tab if needed, but the search might default to it or we can just filter
    # For now, if we aren't in content, let's just make sure we are
    if "content" not in page.url:
        page.goto('https://www.linkedin.com/search/results/content/?keywords="AI%20Engineer"%20"hiring"%20"@gmail.com"')
        time.sleep(3)
    
    inject_visual_cursor(page)
    
    # 3. OCR-First Extraction Loop (True Intelligence)
    ss_path = os.path.join(os.getcwd(), "visor_workspace", "feed_snapshot.png")
    
    for scroll_idx in range(4):
        inject_agent_toast(page, f"Scanning viewport {scroll_idx+1}/4 using OCR...")
        time.sleep(1)
        
        while True:
            # Take screenshot of current viewport
            page.screenshot(path=ss_path)
            all_text = ocr.find_all(ss_path)
            
            see_more = None
            for item in all_text:
                t = item["text"].lower().strip()
                if t in ["see more", "...see more", "…see more", "…more", "...more"]:
                    see_more = item
                    break
            
            if see_more:
                inject_agent_toast(page, f"OCR found '{see_more['text']}' at ({see_more['x']}, {see_more['y']}). Natively clicking to expand...")
                smooth_click(page, see_more['x'], see_more['y'])
                time.sleep(1.5) # Wait for DOM expansion
            else:
                break # No more in this exact viewport
                
        # Scroll down carefully to bring next posts into view
        inject_agent_toast(page, "Scrolling down to load next batch of posts...")
        page.mouse.wheel(0, 800)
        time.sleep(2)
        
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)
    
    # 4. Extract Emails & Track Stats
    inject_agent_toast(page, "Extracting emails from the fully expanded DOM...")
    text_joined = page.evaluate('document.body.innerText')
    emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_joined)))
    emails = [e for e in emails if not e.endswith("sentry.io") and "w3.org" not in e]
    
    if emails:
        stats_msg = f"Extracted {len(emails)} unique emails!\n" + "\n".join([f"-> {e}" for e in emails[:3]])
        if len(emails) > 3:
            stats_msg += f"\n...and {len(emails)-3} more!"
        inject_agent_toast(page, stats_msg, type="success")
        time.sleep(5)
    else:
        inject_agent_toast(page, "No emails found.", type="error")
        time.sleep(3)
        return
        
    # 5. Connect with Top Poster
    inject_agent_toast(page, "Locating the top poster's profile link...")
    profile_link = page.evaluate('''() => {
        let links = Array.from(document.querySelectorAll('a'));
        let pLink = links.find(a => a.href.includes('/in/') && !a.href.includes('/overlay/') && !a.href.includes('miniProfile'));
        return pLink ? pLink.href : null;
    }''')
    
    if profile_link:
        inject_agent_toast(page, f"Navigating to profile: {profile_link.split('?')[0]}")
        page.goto(profile_link, wait_until="domcontentloaded")
        time.sleep(4)
        inject_visual_cursor(page)
        
        inject_agent_toast(page, "Scanning profile using OCR for 'Connect' button...")
        page.screenshot(path=ss_path)
        all_text = ocr.find_all(ss_path)
        
        connect_btn = None
        for item in all_text:
            if item["text"].lower().strip() == "connect":
                connect_btn = item
                break
                
        if connect_btn:
            inject_agent_toast(page, f"Found 'Connect' button visually at ({connect_btn['x']}, {connect_btn['y']}). Clicking...")
            smooth_click(page, connect_btn["x"], connect_btn["y"])
        else:
            inject_agent_toast(page, "No direct 'Connect' button found. Searching for 'More' dropdown...")
            more_btn = next((i for i in all_text if i["text"].lower().strip() == "more"), None)
            if more_btn:
                smooth_click(page, more_btn["x"], more_btn["y"])
                time.sleep(1.5)
                # Re-scan for Connect in dropdown
                page.screenshot(path=ss_path)
                dropdown_text = ocr.find_all(ss_path)
                connect_btn = next((i for i in dropdown_text if i["text"].lower().strip() == "connect"), None)
                if connect_btn:
                    inject_agent_toast(page, "Found 'Connect' inside 'More' dropdown. Clicking...")
                    smooth_click(page, connect_btn["x"], connect_btn["y"])
            
        if connect_btn:
            time.sleep(3)
            inject_agent_toast(page, "Handling connection modal. Searching for 'Send' button...")
            page.screenshot(path=ss_path)
            all_text_modal = ocr.find_all(ss_path)
            send_btn = None
            for item in all_text_modal:
                t = item["text"].lower().strip()
                if "send without" in t or t == "send":
                    send_btn = item
                    break
            
            if send_btn:
                smooth_click(page, send_btn["x"], send_btn["y"])
                inject_agent_toast(page, "Connection Request Sent Successfully! Workflow complete.", type="success")
                time.sleep(4)
            else:
                inject_agent_toast(page, "Could not find 'Send' button in modal.", type="error")
                page.keyboard.press("Escape")
        else:
            inject_agent_toast(page, "Could not locate a Connection path for this profile.", type="error")
            time.sleep(3)
            
    browser.close()

if __name__ == "__main__":
    main()
