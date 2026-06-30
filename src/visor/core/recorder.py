import os
import json
import time
from visor.core import browser, PROJECT_ROOT

TRACE_DIR = os.path.join(PROJECT_ROOT, "visor_workspace", "logs", "traces")

def _inject_recorder(page):
    """Injects a listener that records clicks and a UI for annotations."""
    page.expose_binding("visorLogClick", lambda source, x, y, timestamp: _log_event(source, x, y, timestamp))
    page.expose_binding("visorLogAnnotation", lambda source, text, timestamp: _log_annotation(text, timestamp))
    page.expose_binding("visorStopRecording", lambda source: _stop_recording())
    
    # Inject click listener and UI overlay
    page.add_init_script("""
        window.visorTrace = [];
        
        // Setup listener
        document.addEventListener('click', (e) => {
            if (e.target.closest('#visor-recorder-ui')) return;
            const time = Date.now();
            window.visorLogClick(e.clientX, e.clientY, time);
        }, true);
        
        // Setup UI
        window.addEventListener('load', () => {
            const ui = document.createElement('div');
            ui.id = 'visor-recorder-ui';
            ui.innerHTML = `
                <div style="
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    width: 320px;
                    background: rgba(15, 23, 42, 0.85);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 16px;
                    padding: 16px;
                    color: white;
                    font-family: 'Inter', system-ui, sans-serif;
                    z-index: 2147483647;
                    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    transition: all 0.3s ease;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div style="width: 10px; height: 10px; border-radius: 50%; background: #ef4444; animation: pulse 2s infinite;"></div>
                            <span style="font-weight: 600; font-size: 14px; letter-spacing: 0.5px;">Visor Recording</span>
                        </div>
                        <button id="visor-stop-btn" style="
                            background: rgba(239, 68, 68, 0.2);
                            color: #ef4444;
                            border: 1px solid rgba(239, 68, 68, 0.3);
                            border-radius: 6px;
                            padding: 4px 10px;
                            font-size: 12px;
                            font-weight: 600;
                            cursor: pointer;
                            transition: all 0.2s;
                        ">Stop</button>
                    </div>
                    
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <input type="text" id="visor-annotation-input" placeholder="Type your intent here..." style="
                            background: rgba(0, 0, 0, 0.3);
                            border: 1px solid rgba(255, 255, 255, 0.15);
                            border-radius: 8px;
                            padding: 10px 12px;
                            color: white;
                            font-size: 13px;
                            outline: none;
                            width: 100%;
                            box-sizing: border-box;
                            transition: border-color 0.2s;
                        "/>
                        <button id="visor-annotation-btn" style="
                            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
                            color: white;
                            border: none;
                            border-radius: 8px;
                            padding: 10px;
                            font-size: 13px;
                            font-weight: 600;
                            cursor: pointer;
                            transition: opacity 0.2s;
                            width: 100%;
                        ">Add Annotation</button>
                    </div>
                </div>
                <style>
                    @keyframes pulse {
                        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
                        70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
                        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
                    }
                    #visor-annotation-input:focus { border-color: #3b82f6 !important; }
                    #visor-annotation-btn:hover { opacity: 0.9; }
                    #visor-stop-btn:hover { background: rgba(239, 68, 68, 0.3) !important; }
                </style>
            `;
            document.body.appendChild(ui);
            
            document.getElementById('visor-annotation-btn').addEventListener('click', () => {
                const input = document.getElementById('visor-annotation-input');
                const text = input.value.trim();
                if (text) {
                    window.visorLogAnnotation(text, Date.now());
                    input.value = '';
                    const btn = document.getElementById('visor-annotation-btn');
                    btn.innerText = 'Added!';
                    setTimeout(() => btn.innerText = 'Add Annotation', 1500);
                }
            });
            
            document.getElementById('visor-annotation-input').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    document.getElementById('visor-annotation-btn').click();
                }
            });
            
            document.getElementById('visor-stop-btn').addEventListener('click', () => {
                window.visorStopRecording();
            });
        });
    """)

_events = []
_pending_screenshots = []
_flow_name = "default"
_recording_active = False

def _log_event(source, x, y, timestamp):
    _events.append({
        "type": "click", 
        "x": x, 
        "y": y, 
        "timestamp": timestamp,
        "screenshot": os.path.join(TRACE_DIR, f"{_flow_name}_{timestamp}.png")
    })
    _pending_screenshots.append(timestamp)
    print(f"[RECORDER] Registered click at ({x}, {y})")

def _log_annotation(text, timestamp):
    _events.append({
        "type": "annotation",
        "text": text,
        "timestamp": timestamp,
        "screenshot": os.path.join(TRACE_DIR, f"{_flow_name}_{timestamp}_annotation.png")
    })
    _pending_screenshots.append(f"{timestamp}_annotation")
    print(f"[RECORDER] Added annotation: '{text}'")

def _stop_recording():
    global _recording_active
    _recording_active = False
    print("[RECORDER] Stop button clicked in browser.")

def start_recording(flow_name: str, url: str, description: str):
    """Starts the browser in recording mode."""
    os.makedirs(TRACE_DIR, exist_ok=True)
    global _events, _flow_name, _recording_active
    _events = []
    _flow_name = flow_name
    _recording_active = True
    
    print(f"[RECORDER] Starting recording for '{flow_name}'.")
    # record_video=False allows connecting to the user's real Chrome profile via CDP!
    page = browser.init_browser(headless=False, record_video=False)
    _inject_recorder(page)
    
    print(f"[RECORDER] Navigating to {url}")
    page.goto(url)
    
    stop_flag = os.path.join(TRACE_DIR, f"{flow_name}_stop.flag")
    if os.path.exists(stop_flag):
        os.remove(stop_flag)
        
    print("[RECORDER] Recording active. Use the UI overlay to add annotations or stop.")
    try:
        while _recording_active and not os.path.exists(stop_flag):
            if _pending_screenshots:
                ts = _pending_screenshots.pop(0)
                ss_path = os.path.join(TRACE_DIR, f"{flow_name}_{ts}.png")
                try:
                    page.screenshot(path=ss_path)
                    print(f"[RECORDER] Captured {ss_path}")
                except Exception as e:
                    print(f"[RECORDER] Failed screenshot: {e}")
            page.wait_for_timeout(100)
            
        print("\n[RECORDER] Recording stopped. Saving trace...")
        if os.path.exists(stop_flag):
            os.remove(stop_flag)
    except KeyboardInterrupt:
        print("\n[RECORDER] Stopped via Ctrl+C. Saving trace...")
    
    
    # Save trace
    trace_file = os.path.join(TRACE_DIR, f"{flow_name}_trace.json")
    with open(trace_file, "w") as f:
        json.dump({
            "flow": flow_name,
            "url": url,
            "description": description,
            "events": _events
        }, f, indent=2)
        
    print(f"[RECORDER] Saved trace to {trace_file}")
    return trace_file
