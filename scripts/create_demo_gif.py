import os
import time
import glob
import subprocess
from visor.core import browser, ocr, clicker

def main():
    print("\n🎥 [Visor] Starting Demo with Video Recording...")
    
    # Initialize with video recording
    browser.init_browser(headless=True, record_video=True)
    
    url = "https://news.ycombinator.com/"
    print(f"🌍 Navigating to {url}...")
    browser.navigate(url)
    
    time.sleep(2) # Wait for render
    
    print("📸 Taking a screenshot...")
    img_path = browser.screenshot()
    
    target_text = "login"
    print(f"🔍 Using AI/OCR to find '{target_text}' visually...")
    
    match = ocr.find(target_text, img_path, exact=False)
    
    if match:
        print(f"✅ Found '{target_text}' at coordinates (X: {match['x']}, Y: {match['y']})")
        print("🖱️ Injecting CDP Click...")
        clicker.click(match["x"], match["y"])
        # Wait for the click effect to be captured on video
        time.sleep(3)
        print("🎉 Success!")
    else:
        print(f"❌ Could not find '{target_text}' via OCR.")

    # Close browser to flush video
    print("🎬 Saving video...")
    browser.close()
    
    # Find the latest webm video in visor_workspace/videos
    video_dir = os.path.join(os.getcwd(), "visor_workspace", "videos")
    videos = glob.glob(os.path.join(video_dir, "*.webm"))
    if not videos:
        print("❌ No video was recorded!")
        return
        
    latest_video = max(videos, key=os.path.getctime)
    gif_path = os.path.join(os.getcwd(), "examples", "demo.gif")
    
    print(f"🔄 Converting {latest_video} to GIF...")
    # Generate an optimized GIF using ffmpeg
    cmd = [
        "ffmpeg", "-y", "-i", latest_video, 
        "-vf", "fps=10,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse", 
        "-loop", "0", gif_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print(f"✅ GIF created successfully at: {gif_path}")

if __name__ == "__main__":
    main()
