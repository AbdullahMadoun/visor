import os
import time
import threading
from flask import Flask, request
from datasets import Dataset
import json

# Local imports for Visor
import sys
sys.path.insert(0, os.path.dirname(__file__))
from visor.core import ocr

app = Flask(__name__)

current_html = ""
current_pos_candidates = []
last_clicked_node = None
click_event = threading.Event()

@app.route('/')
def serve_html():
    injection = """
    <script>
    document.addEventListener('click', function(e) {
        let node_id = e.target.getAttribute('backend_node_id');
        let curr = e.target;
        while (!node_id && curr) {
            node_id = curr.getAttribute('backend_node_id');
            curr = curr.parentElement;
        }
        fetch('/log_click', {method: 'POST', body: node_id || 'UNKNOWN'});
    });
    </script>
    """
    return current_html + injection

@app.route('/log_click', methods=['POST'])
def log_click():
    global last_clicked_node
    last_clicked_node = request.data.decode('utf-8')
    click_event.set()
    return "OK"

def run_server():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(port=8080, use_reloader=False)

def start_proxy():
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(1)

def evaluate_gt():
    global current_html, current_pos_candidates, last_clicked_node

    print("[EVAL] Loading Mind2Web dataset (from cache)...")
    ds = Dataset.from_file(os.path.expanduser("~/.cache/huggingface/datasets/osunlp___mind2_web/default/0.0.0/17ece8eb89862368edc0cc806acee6fca5163474/mind2_web-train-00000-of-00008.arrow"))
    start_proxy()
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        
        # Block all network requests except localhost to load instantly
        def abort_route(route):
            if "localhost" not in route.request.url:
                route.abort()
            else:
                route.continue_()
                
        page = context.new_page()
        page.route("**/*", abort_route)

        correct_steps = 0
        total_steps = 0
        
        num_tasks = 5
        print(f"[EVAL] Starting evaluation on {num_tasks} tasks...")

        for i in range(num_tasks):
            task = ds[i]
            print(f"\n[EVAL] Task {i}: {task['confirmed_task']}")
            actions = task['actions']
            
            for step_idx, action in enumerate(actions):
                current_html = action['raw_html']
                current_pos_candidates = [str(x['backend_node_id']) for x in action['pos_candidates']]
                
                print(f"  Step {step_idx}: Target nodes: {current_pos_candidates}")
                click_event.clear()
                last_clicked_node = None
                
                try:
                    # Load the raw HTML proxy
                    page.goto("http://localhost:8080", wait_until="commit", timeout=5000)
                    time.sleep(1) # wait for render
                    
                    img_path = f"/tmp/eval_step_{i}_{step_idx}.png"
                    page.screenshot(path=img_path)
                    
                    action_repr = task['action_reprs'][step_idx]
                    keyword = action_repr.split("]")[-1].strip() if "]" in action_repr else action_repr
                    
                    items = ocr.find_all(img_path)
                    best_match = None
                    for item in items:
                        if keyword.lower() in item['text'].lower():
                            best_match = item
                            break
                    
                    if best_match:
                        print(f"  [Visor OCR] Found '{best_match['text']}' at {best_match['x']}, {best_match['y']}")
                        page.mouse.click(best_match['x'], best_match['y'])
                        
                        click_event.wait(timeout=2)
                        
                        if last_clicked_node in current_pos_candidates:
                            print(f"  => SUCCESS! GT Matched (Clicked Node: {last_clicked_node}).")
                            correct_steps += 1
                        else:
                            print(f"  => FAILED! Clicked {last_clicked_node}, expected {current_pos_candidates}")
                    else:
                        print("  => FAILED! OCR did not find target text.")
                        
                except Exception as e:
                    print(f"  => ERROR: {e}")
                
                total_steps += 1
                
                # Write progress to file so we can monitor it
                with open("/tmp/eval_progress.txt", "w") as f:
                    f.write(f"Task: {i+1}/{num_tasks}\nSteps Correct: {correct_steps}/{total_steps} ({(correct_steps/total_steps*100) if total_steps>0 else 0:.1f}%)")

        print(f"\n[EVAL] Final GT Score: {correct_steps}/{total_steps} ({(correct_steps/total_steps)*100:.1f}%)")

if __name__ == "__main__":
    evaluate_gt()
