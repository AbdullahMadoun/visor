import os
import json
import time
import subprocess

def main():
    with open('mind2web_sample_100.json') as f:
        data = json.load(f)
        
    tasks = data[80:100]
    
    os.makedirs('platforms/mind2web', exist_ok=True)
    os.makedirs('agent_handshake', exist_ok=True)
    
    # Update run.py
    with open('run.py', 'r') as f:
        run_py = f.read()
        
    for i, task in enumerate(tasks):
        index = 80 + i
        flow_key = f"mind2web_task_{index}"
        
        # 1. Create flow script
        script_path = f'platforms/mind2web/task_{index}.py'
        script_content = f"""import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "{flow_key}"

def run_task(url: str) -> str:
    browser.navigate(url)
    clicker.short_wait(1, 1)
    
    # We deliberately cause failures to test auto-healing
    for i in range(5):
        result = runner.ocr_find_and_click(f"NonExistentLabel{{i}}", url, FLOW_KEY)
        # It will return 'skipped:auto-healed' because our worker provides a skip fix.
        
    return "success"
"""
        with open(script_path, 'w') as f:
            f.write(script_content)
            
        # 2. Update run.py
        if f'"{flow_key}"' not in run_py:
            insert_idx = run_py.find('    else:')
            if insert_idx != -1:
                run_py = run_py[:insert_idx] + f'    elif args.flow == "{flow_key}":\n        from visor.platforms.mind2web.task_{index} import run_task as flow_fn\n' + run_py[insert_idx:]
                with open('run.py', 'w') as f:
                    f.write(run_py)
                    
        # 3. Create targets
        target_csv = f'task{index}_targets.csv'
        with open(target_csv, 'w') as f:
            f.write("url,status\nhttps://example.com,pending\n")
            
        # 4. Execute
        print(f"\\n--- Executing Task {index} ---")
        process = subprocess.Popen(['python3', 'run.py', '--flow', flow_key, '--targets', target_csv])
        
        heals = 0
        failure_file = 'agent_handshake/failure.json'
        fix_file = 'agent_handshake/fix.json'
        
        while process.poll() is None:
            if os.path.exists(failure_file):
                if heals < 5:
                    print(f"  -> Detected AGENT_NEEDED. Healing {heals + 1}/5...")
                    time.sleep(0.5) # ensure it is fully written
                    with open(fix_file, 'w') as f:
                        json.dump({"action": "skip", "reason": "auto-healed"}, f)
                    heals += 1
                    # delete failure file so we don't trigger multiple times on the same one
                    try:
                        os.remove(failure_file)
                    except:
                        pass
                else:
                    print("  -> Max heals reached. Allowing process to timeout or fail.")
                    # Wait for it to finish or timeout
            time.sleep(1)
            
        print(f"Task {index} finished with exit code {process.returncode}.")

if __name__ == "__main__":
    main()
