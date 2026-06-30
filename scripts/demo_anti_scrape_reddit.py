import os
import time
from rich.console import Console
from rich.panel import Panel
from visor.core import browser, ocr, clicker

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

def smooth_click(x, y):
    page = browser.get_page()
    page.mouse.move(x, y, steps=15)
    time.sleep(0.1)
    page.mouse.down()
    time.sleep(0.1)
    page.mouse.up()

def main():
    console.print(Panel.fit("[bold red]Visor 🤖 Anti-Scrape & Hard DOM Demo[/bold red]\n[dim]Navigating Reddit with headless=False and pure OCR.[/dim]"))
    
    with console.status("[bold green]Initializing Playwright (HEADLESS = FALSE)..."):
        browser.init_browser(headless=False, record_video=False)
    page = browser.get_page()
    
    url = "https://www.reddit.com/"
    with console.status(f"[bold yellow]Navigating to {url}..."):
        browser.navigate(url)
        time.sleep(3) # Wait for initial load and potential anti-bot checks
        inject_visual_cursor(page)
    
    with console.status("[bold magenta]Taking viewport screenshot..."):
        img_path = browser.screenshot()
    
    # Reddit DOM is heavily obfuscated with dynamic classes like 'shreddit-app', 'faceplate-tracker'.
    # We ignore the DOM completely and just look for the "Log In" button visually!
    target_text = "Log In"
    with console.status(f"[bold blue]Using AI/OCR to locate '{target_text}'..."):
        match = ocr.find(target_text, img_path, exact=False)
    
    if match:
        console.print(f"[bold green]✅ Found '{target_text}' at coordinates (X: {match['x']}, Y: {match['y']})[/bold green]")
        with console.status("[bold red]Injecting native CDP Click..."):
            smooth_click(match["x"], match["y"])
            time.sleep(2)
            
        console.print("[bold green]🎉 Success! Clicked Log In via pure vision, bypassing DOM obfuscation.[/bold green]")
    else:
        console.print(f"[bold red]❌ Could not find '{target_text}' via OCR.[/bold red]")

    time.sleep(3) # Hold browser open for a moment so the user can see it!
    browser.close()

if __name__ == "__main__":
    main()
