import os
import json
import time
import glob
import subprocess
from visor.core import browser, ocr, clicker

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
    page.evaluate(js)
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
    page.mouse.move(x, y, steps=15)
    time.sleep(0.1)
    page.mouse.down()
    time.sleep(0.1)
    page.mouse.up()

def main():
    print("\n🩺 [Visor] Starting Self-Healing Handshake Demo...")
    
    # Initialize with video recording
    browser.init_browser(headless=True, record_video=True)
    page = browser.get_page()
    
    url = "https://news.ycombinator.com/"
    print(f"🌍 Navigating to {url}...")
    browser.navigate(url)
    
    inject_visual_cursor(page)
    inject_agent_toast(page, "Navigated to Hacker News in fresh en-US context")
    time.sleep(1) # Wait for render
    
    print("📸 Taking a screenshot...")
    img_path = browser.screenshot()
    
    # Intentionally looking for something that does not exist
    target_text = "NonExistentSubmitButton"
    print(f"\n🔍 Using AI/OCR to find '{target_text}' visually...")
    inject_agent_toast(page, f"Running OCR to find '{target_text}'...")
    
    match = ocr.find(target_text, img_path, exact=False)
    
    if not match:
        print(f"❌ Could not find '{target_text}'.")
        print("🚨 AGENT_NEEDED: Halting execution and requesting human/LLM intervention...")
        inject_agent_toast(page, f"Target '{target_text}' not found! Halting and saving failure.json...")
        time.sleep(1)
        
        # Simulate writing the failure state
        handshake_dir = os.path.join(os.getcwd(), "visor_workspace", "agent_handshake")
        os.makedirs(handshake_dir, exist_ok=True)
        failure_path = os.path.join(handshake_dir, "failure.json")
        fix_path = os.path.join(handshake_dir, "fix.json")
        
        with open(failure_path, "w") as f:
            json.dump({"error": "Target not found", "target": target_text}, f)
            
        print(f"📝 Saved failure state to {failure_path}.")
        print("⏳ Waiting for fix.json to be created by the healer agent...")
        
        # Wait to simulate human/agent thinking
        inject_agent_toast(page, "AGENT_NEEDED triggered. Polling for fix.json...")
        time.sleep(2)
        
        # Simulate the Healer Agent dropping in the fix
        print("\n🧠 [Healer Agent] Diagnosing the screenshot...")
        print("🧠 [Healer Agent] 'Ah, the button on Hacker News is actually called login!'")
        print(f"🧠 [Healer Agent] Writing fix.json...")
        inject_agent_toast(page, "🧠 [Healer Agent] Wrote fix.json! Target changed to 'login'.")
        with open(fix_path, "w") as f:
            json.dump({"action": "replace_target", "new_target": "login"}, f)
            
        # The main loop polls for fix.json
        while not os.path.exists(fix_path):
            time.sleep(0.5)
            
        print("\n📥 Detected fix.json! Reading instructions...")
        with open(fix_path, "r") as f:
            fix_data = json.load(f)
            
        if fix_data.get("action") == "replace_target":
            target_text = fix_data["new_target"]
            print(f"✅ Self-Healed! Target updated to '{target_text}'. Resuming execution...")
            inject_agent_toast(page, f"✅ Self-Healed! Resuming execution and clicking '{target_text}'...")
            
            # Resume
            match = ocr.find(target_text, img_path, exact=False)
            if match:
                print(f"✅ Found '{target_text}' at coordinates (X: {match['x']}, Y: {match['y']})")
                print("🖱️ Injecting CDP Click...")
                smooth_click(match["x"], match["y"])
                time.sleep(1.5)
                print("🎉 Absolute Success! The script healed itself dynamically.")
                inject_agent_toast(page, "🎉 Absolute Success! Script healed and execution resumed.")
                time.sleep(1.5)
            else:
                print("❌ Failed even after healing.")
        
        # Cleanup
        if os.path.exists(failure_path): os.remove(failure_path)
        if os.path.exists(fix_path): os.remove(fix_path)
        
    # Close browser to flush video
    print("🎬 Saving video...")
    browser.close()
    
    # Convert latest video to GIF using existing libraries
    video_dir = os.path.join(os.getcwd(), "visor_workspace", "videos")
    videos = glob.glob(os.path.join(video_dir, "*.webm"))
    if videos:
        latest_video = max(videos, key=os.path.getctime)
        gif_path = os.path.join(os.getcwd(), "examples", "demo_self_healing.gif")
        
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        
        with console.status("[bold green]Converting WebM to GIF using cv2 and Pillow..."):
            import cv2
            from PIL import Image
            
            cap = cv2.VideoCapture(latest_video)
            frames = []
            frame_count = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
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
                    duration=40,
                    loop=0
                )
            
        console.print(Panel.fit(f"[bold cyan]✅ Masterpiece GIF created at:[/bold cyan]\n[green]{gif_path}[/green]"))

if __name__ == "__main__":
    main()
