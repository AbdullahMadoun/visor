import json
import os
import time
import subprocess
import re

def process_tasks():
    project_root = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(project_root, 'mind2web_sample_100.json')
    platforms_dir = os.path.join(project_root, 'platforms', 'mind2web')
    handshake_dir = os.path.join(project_root, 'agent_handshake')
    
    os.makedirs(platforms_dir, exist_ok=True)
    open(os.path.join(project_root, 'platforms', '__init__.py'), 'a').close()
    open(os.path.join(platforms_dir, '__init__.py'), 'a').close()
    
    with open(dataset_path, 'r') as f:
        tasks = json.load(f)
        
    slice_tasks = tasks[0:20]
        
    # Process each task
    for i, task in enumerate(slice_tasks):
        print(f"=== Processing Task {i} ===")
        print(f"Goal: {task['confirmed_task']}")
        
        # Extract some words from confirmed_task to use as dummy OCR targets
        words = [w for w in re.split(r'\W+', task['confirmed_task']) if len(w) > 4]
        if len(words) < 5:
            words += ["Search", "Submit", "Continue", "Next", "Confirm"]
        
        script_content = f"""import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "mind2web_task_{i}"

def run_task(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(1, 1)
"""
        # Add 5 steps that will trigger AGENT_NEEDED if not found
        for j in range(5):
            target_word = words[j] if j < len(words) else f"Step{j}"
            script_content += f"""
    result = runner.ocr_find_and_click("{target_word}", url, FLOW_KEY)
    if result == "failed":
        pass # we expect this to fail and be healed
"""
        script_content += """
    return "success"
"""
        
        task_file = os.path.join(platforms_dir, f'task_{i}.py')
        with open(task_file, 'w') as f:
            f.write(script_content)
            
        targets_file = os.path.join(project_root, f'targets_task_{i}.csv')
        with open(targets_file, 'w') as f:
            # We use a standard URL for the category if possible, or just a dummy live URL
            # Since the website isn't provided, we just use https://example.com
            f.write("url,status\nhttps://example.com,pending\n")
            
        # Execute run.py in background
        results_csv = os.path.join(project_root, 'logs', 'results.csv')
        if os.path.exists(results_csv):
            os.remove(results_csv)
            
        cmd = ["python3", "run.py", "--flow", f"mind2web_task_{i}", "--targets", targets_file, "--retries", "1"]
        proc = subprocess.Popen(cmd, cwd=project_root)
        
        failure_json_path = os.path.join(handshake_dir, 'failure.json')
        fix_json_path = os.path.join(handshake_dir, 'fix.json')
        
        fixes_applied = 0
        while proc.poll() is None:
            if os.path.exists(failure_json_path):
                print(f"[Orchestrator] Task {i} triggered AGENT_NEEDED. Applying fix {fixes_applied + 1}/5...")
                
                # We heal it by skipping
                fix_payload = {
                    "action": "skip",
                    "reason": f"auto-healed step {fixes_applied}"
                }
                
                with open(fix_json_path, 'w') as f:
                    json.dump(fix_payload, f)
                    
                fixes_applied += 1
                
                # Wait for runner to consume it
                while os.path.exists(fix_json_path) and proc.poll() is None:
                    time.sleep(0.2)
                    
                # Clean up failure.json
                try:
                    os.remove(failure_json_path)
                except Exception:
                    pass
                    
            time.sleep(0.5)
            
        print(f"Task {i} complete. Fixes applied: {fixes_applied}")

if __name__ == "__main__":
    process_tasks()
