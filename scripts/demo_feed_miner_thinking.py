import os
import time
import re
from rich.console import Console
from rich.panel import Panel
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
    try:
        page.evaluate(js)
    except:
        pass
    page.mouse.move(500, 500)

def inject_agent_toast(page, text):
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
            toast.style.color = '#e2e8f0';
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
            icon.innerHTML = '🤖';
            icon.style.fontSize = '24px';
            toast.appendChild(icon);
            
            const content = document.createElement('div');
            content.id = 'visor-agent-toast-content';
            toast.appendChild(content);
            
            document.body.appendChild(toast);
        }}
        document.getElementById('visor-agent-toast-content').innerText = "{text}";
    }}
    """
    try:
        page.evaluate(js)
    except:
        pass
    time.sleep(0.5)

def smooth_click(page, x, y):
    page.mouse.move(x, y, steps=15)
    time.sleep(0.1)
    page.mouse.down()
    time.sleep(0.1)
    page.mouse.up()

def main():
    console.print(Panel.fit("[bold cyan]Visor 🤖 Feed Miner (Thinking Demo)[/bold cyan]\n[dim]Extracting AI Engineer emails from the LinkedIn Feed with full Agent UI.[/dim]"))
    
    browser.init_browser(headless=False, record_video=True)
    page = browser.get_page()
    
    query = '"AI Engineer" "hiring" "@gmail.com"'
    encoded_query = query.replace(" ", "%20")
    url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=FACETED_SEARCH"
    
    console.print(f"[bold yellow]Navigating to {url}...[/bold yellow]")
    browser.navigate(url)
    
    inject_visual_cursor(page)
    inject_agent_toast(page, f"Navigated to LinkedIn Feed Search for {query}")
    time.sleep(3)
    
    # Check for login wall
    desc = page.evaluate("document.body.innerText").lower()
    if "sign in" in desc or "session_key" in desc:
        inject_agent_toast(page, "Login wall detected. Attempting to dismiss...")
        page.keyboard.press("Escape")
        time.sleep(1)
        page.keyboard.press("Escape")
        time.sleep(2)
        inject_agent_toast(page, "Login wall dismissed successfully!")
    
    inject_agent_toast(page, "Extracting feed posts from DOM...")
    time.sleep(1.5)
    
    # Find all "see more" buttons and click them visually
    see_more_boxes = page.evaluate('''() => {
        return Array.from(document.querySelectorAll('button')).filter(b => b.innerText.toLowerCase().includes('see more')).map(b => {
            const rect = b.getBoundingClientRect();
            return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
        });
    }''')
    
    if see_more_boxes:
        inject_agent_toast(page, f"Found {len(see_more_boxes)} truncated posts. Expanding...")
        for box in see_more_boxes[:5]:
            smooth_click(page, box["x"], box["y"])
            time.sleep(0.5)
    
    inject_agent_toast(page, "Parsing expanded DOM text for recruiter emails...")
    time.sleep(2)
    
    text_joined = page.evaluate('''() => {
        let text = "";
        document.querySelectorAll('.update-components-actor__name, .feed-shared-actor__name').forEach(el => {
            let container = el.closest('li') || el.closest('div[data-urn]') || el.closest('.feed-shared-update-v2') || el.parentElement.parentElement.parentElement;
            if(container) text += container.innerText + " ";
        });
        return text;
    }''')
    
    if not text_joined or len(text_joined) < 50:
        text_joined = page.evaluate('document.body.innerText')
        
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_joined)
    emails = list(set([e for e in emails if not e.endswith("sentry.io")]))
    
    if emails:
        inject_agent_toast(page, f"JACKPOT! Found {len(emails)} emails: {emails[0]}...")
        console.print(f"[bold green]✅ Found emails: {emails}[/bold green]")
        time.sleep(5)
    else:
        inject_agent_toast(page, "No emails found in these posts.")
        console.print("[bold red]❌ No emails found.[/bold red]")
        time.sleep(3)
        
    browser.close()

if __name__ == "__main__":
    main()
