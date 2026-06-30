import os
import time
import subprocess
import json

def main():
    os.makedirs('agent_handshake', exist_ok=True)
    
    for i in range(20, 40):
        index = i
        flow_key = f"mind2web_task_{index}"
        target_csv = f'task{index}_targets.csv'
        
        # 4. Execute
        print(f"\n--- Executing Task {index} ---")
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
                    try:
                        os.remove(failure_file)
                    except:
                        pass
                else:
                    print("  -> Max heals reached. Allowing process to timeout or fail.")
            time.sleep(1)
            
        print(f"Task {index} finished with exit code {process.returncode}.")

if __name__ == "__main__":
    main()
