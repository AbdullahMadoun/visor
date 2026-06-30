import os
import time
import re
from rich.console import Console
from rich.panel import Panel
from visor.core import browser, clicker, ocr

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
    console.print(Panel.fit("[bold cyan]Visor 🤖 LinkedIn Job Miner[/bold cyan]\n[dim]Hunting for AI Engineering job emails using hybrid DOM+OCR.[/dim]"))
    
    browser.init_browser(headless=False, record_video=False)
    page = browser.get_page()
    
    url = "https://www.linkedin.com/jobs/search/?keywords=AI%20Engineer&f_TPR=r86400" # Past 24h
    console.print(f"[bold yellow]Navigating to {url}...[/bold yellow]")
    browser.navigate(url)
    
    inject_visual_cursor(page)
    inject_agent_toast(page, "Navigated to LinkedIn Jobs (AI Engineer)")
    time.sleep(3)
    
    # 1. Check for Login Wall / Wait for login
    if page.locator("input#session_key, input#username, button[data-id='sign-in-form__submit-btn']").count() > 0:
        inject_agent_toast(page, "Login wall detected! Please log in. Waiting 60 seconds...")
        console.print("[bold red]🚨 Login required. Please log in to LinkedIn in the browser window![/bold red]")
        try:
            page.wait_for_selector(".job-card-container", timeout=60000)
            console.print("[bold green]✅ Login successful! Resuming...[/bold green]")
            # Save session
            page.context.storage_state(path=os.path.join(os.getcwd(), "visor_workspace", "session.json"))
            inject_agent_toast(page, "Session saved! Scanning jobs...")
        except Exception:
            console.print("[bold red]❌ Timed out waiting for login.[/bold red]")
            browser.close()
            return
            
    inject_agent_toast(page, "Extracting job card bounding boxes via DOM...")
    job_cards = page.locator(".job-card-container").all()
    
    if not job_cards:
        inject_agent_toast(page, "No job cards found. Ensure you are logged in!")
        console.print("[bold red]❌ No job cards found![/bold red]")
        time.sleep(3)
        return
        
    console.print(f"[bold green]✅ Found {len(job_cards)} job cards. Scanning for emails...[/bold green]")
    
    for i, card in enumerate(job_cards[:7]): # Scan first 7 jobs
        try:
            box = card.bounding_box()
            if not box: continue
            
            inject_agent_toast(page, f"Clicking Job #{i+1} via native CDP...")
            # Click the card geometrically
            smooth_click(page, box["x"] + 20, box["y"] + 20)
            time.sleep(2) # Wait for description to load
            
            # Click 'See more' if exists using JS
            page.evaluate('''() => {
                document.querySelectorAll('button').forEach(b => {
                    if(b.innerText.toLowerCase().includes('see more')) b.click();
                });
            }''')
            time.sleep(1)
            
            # Extract description text
            desc_text = page.evaluate('document.body.innerText')
            
            # Regex search for emails
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', desc_text)
            emails = [e for e in set(emails) if not e.endswith("sentry.io") and not e.endswith("example.com")]
            
            if emails:
                inject_agent_toast(page, f"JACKPOT! Found email: {emails[0]}")
                console.print(f"[bold magenta]🎉 Found email on Job #{i+1}: {emails}[/bold magenta]")
                time.sleep(5)
                return
            else:
                inject_agent_toast(page, f"No email in Job #{i+1}, moving to next...")
                
        except Exception as e:
            console.print(f"[bold red]Error on card {i}: {e}[/bold red]")
            
    inject_agent_toast(page, "Finished scan. No emails found in top results.")
    console.print("[bold yellow]Finished scan.[/bold yellow]")
    time.sleep(3)
    browser.close()

if __name__ == "__main__":
    main()
