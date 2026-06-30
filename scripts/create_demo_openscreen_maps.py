import os
import time
import glob
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
            // Start the cursor exactly where it is so it doesn't jump
            box.style.opacity = '1';
        });
        document.addEventListener('mousedown', () => { box.style.transform = 'translate(-50%, -50%) scale(0.6)'; });
        document.addEventListener('mouseup', () => { box.style.transform = 'translate(-50%, -50%) scale(1)'; });
    }
    """
    page.evaluate(js)
    # Move mouse somewhere central initially
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
    page.evaluate(js)
    time.sleep(0.5)

def smooth_click(x, y):
    page = browser.get_page()
    page.mouse.move(x, y, steps=15) # Sped up mouse move
    time.sleep(0.1)
    page.mouse.down()
    time.sleep(0.1)
    page.mouse.up()

def main():
    console.print(Panel.fit("[bold cyan]Visor 🤖 OpenScreen-Style Tough Demo[/bold cyan]\n[dim]Navigating Google Maps (Canvas/Dynamic DOM) with OCR & visual cursor gliding.[/dim]"))
    
    with console.status("[bold green]Initializing Playwright with Video Recording..."):
        browser.init_browser(headless=True, record_video=True)
    
    page = browser.get_page()
    url = "https://www.google.com/maps"
    with console.status(f"[bold yellow]Navigating to {url}..."):
        browser.navigate(url)
        inject_agent_toast(page, "Navigated to Google Maps in clean en-US context")
        time.sleep(2) # Sped up
        
    with console.status("[bold magenta]Injecting Screen Studio-style visual cursor..."):
        inject_visual_cursor(page)
        
    # Dismiss cookie banner if present (Google Maps Europe/Incognito specific)
    inject_agent_toast(page, "Scanning for cookie consent banners...")
    img_path = browser.screenshot()
    accept = ocr.find("Accept all", img_path, exact=False)
    if accept:
        smooth_click(accept["x"], accept["y"])
        time.sleep(1)
        img_path = browser.screenshot() # fresh screenshot
    
    # 1. Search Google Maps
    target_text = "Search"
    inject_agent_toast(page, f"Running OCR to find '{target_text}' box...")
    with console.status(f"[bold blue]Using AI/OCR to locate placeholder: '{target_text}'..."):
        match = ocr.find(target_text, img_path, exact=False)
    
    if match:
        console.print(f"[bold green]✅ Found '{target_text}' at coordinates (X: {match['x']}, Y: {match['y']})[/bold green]")
        inject_agent_toast(page, f"Found '{target_text}' at ({match['x']}, {match['y']}). Clicking...")
        smooth_click(match["x"], match["y"] + 10) 
        
        with console.status("[bold cyan]Typing 'Specialty Coffee Tokyo'..."):
            inject_agent_toast(page, "Typing 'Specialty Coffee Tokyo' using native CDP...")
            clicker.type_text("Specialty Coffee Tokyo")
            time.sleep(0.5)
            
        with console.status("[bold yellow]Pressing 'Enter' key..."):
            clicker.press("Enter")
            inject_agent_toast(page, "Pressed Enter. Waiting for results to render...")
            time.sleep(3) # Let pins drop
            
        # 2. Re-screenshot and look for a filter or specific pin
        with console.status("[bold magenta]Taking second screenshot to find filter chips..."):
            img_path = browser.screenshot()
            
        target_text2 = "Coffee"
        inject_agent_toast(page, f"Running OCR to find '{target_text2}' result...")
        match2 = ocr.find(target_text2, img_path, exact=False)
        if match2:
            console.print(f"[bold green]✅ Found '{target_text2}' filter![/bold green]")
            inject_agent_toast(page, f"Found '{target_text2}'. Gliding and clicking...")
            smooth_click(match2["x"], match2["y"])
            time.sleep(2)
        else:
            console.print(f"[bold red]❌ Could not find '{target_text2}'.[/bold red]")
            
        inject_agent_toast(page, "🎉 Tough Demo Complete! Hybrid DOM+OCR Architecture.")
        time.sleep(2)
        console.print("[bold green]🎉 Tough Demo Complete! Executed smooth OCR-driven interactions on Google Maps.[/bold green]")
    else:
        console.print(f"[bold red]❌ Could not find '{target_text}'.[/bold red]")

    with console.status("[bold magenta]Saving and flushing video..."):
        browser.close()
    
    # Convert latest video to GIF using native python tools
    video_dir = os.path.join(os.getcwd(), "visor_workspace", "videos")
    videos = glob.glob(os.path.join(video_dir, "*.webm"))
    if videos:
        latest_video = max(videos, key=os.path.getctime)
        gif_path = os.path.join(os.getcwd(), "examples", "demo_openscreen_maps.gif")
        
        with console.status("[bold green]Converting WebM to stunning GIF using cv2 and Pillow..."):
            import cv2
            from PIL import Image
            
            cap = cv2.VideoCapture(latest_video)
            frames = []
            frame_count = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                # SPED UP: Skip every 3rd frame
                if frame_count % 3 == 0:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(frame_rgb)
                    w_percent = (800 / float(pil_img.size[0]))
                    h_size = int((float(pil_img.size[1]) * float(w_percent)))
                    pil_img = pil_img.resize((800, h_size), Image.Resampling.LANCZOS)
                    frames.append(pil_img)
                frame_count += 1
            cap.release()
            
            if frames:
                frames[0].save(
                    gif_path,
                    save_all=True,
                    append_images=frames[1:],
                    optimize=True,
                    duration=40, # SPED UP: 25fps equivalent for the frames we keep
                    loop=0
                )
            
        console.print(Panel.fit(f"[bold cyan]✅ Masterpiece OpenScreen-style GIF created at:[/bold cyan]\n[green]{gif_path}[/green]"))

if __name__ == "__main__":
    main()
