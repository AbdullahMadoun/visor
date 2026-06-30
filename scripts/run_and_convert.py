import os
import subprocess
import glob

def get_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(result.stdout.strip())
    except:
        return 0

def main():
    videos_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "visor_workspace", "videos")
    # Cleanup old webm files
    for f in glob.glob(os.path.join(videos_dir, "*.webm")):
        os.remove(f)
        
    print("Running flawless execution...")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    
    subprocess.run(["python3", os.path.join(os.path.dirname(__file__), "flawless_run.py")], env=env)
    
    webms = glob.glob(os.path.join(videos_dir, "*.webm"))
    if not webms:
        print("No video found!")
        return
        
    input_video = webms[0]
    output_video = os.path.join(videos_dir, "final_demo.mp4")
    
    if os.path.exists(output_video):
        os.remove(output_video)
        
    duration = get_duration(input_video)
    print(f"Original video duration: {duration}s")
    
    if duration > 0:
        pts_factor = 30.0 / duration
        print(f"Converting and speeding up to exactly 30s (Factor: {pts_factor})...")
        
        cmd = [
            "ffmpeg", "-y", "-i", input_video,
            "-filter:v", f"setpts={pts_factor}*PTS",
            "-an", output_video
        ]
        subprocess.run(cmd)
        
        final_duration = get_duration(output_video)
        print(f"Final MP4 generated: {output_video} (Duration: {final_duration}s)")
    else:
        print("Failed to read original duration.")

if __name__ == "__main__":
    main()
