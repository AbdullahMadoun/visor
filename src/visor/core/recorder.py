import os
import json
import queue
import threading
from visor.core import browser, ocr, PROJECT_ROOT

import time

TRACE_DIR = os.path.join(PROJECT_ROOT, "visor_workspace", "logs", "traces")

# --- Module-level state ---
_events = []
_flow_name = "default"
_recording_active = False
_pending_annotation = None  # queued annotation — auto-attaches to next click
_page_ref = None            # held so background thread can take after-screenshots
_action_queue = queue.Queue()
_scheduled_tasks = []       # tasks to run on the main thread later


# ---------------------------------------------------------------------------
# OCR helpers (run on Python side so we stay off the JS thread)
# ---------------------------------------------------------------------------

def _nearest_label(x: int, y: int, img_path: str) -> str:
    """Return the OCR text whose bounding-box centre is closest to (x, y)."""
    try:
        results = ocr.find_all(img_path)  # list of {text, x, y, x1, y1, x2, y2, confidence}
        best, best_dist = None, float("inf")
        for r in results:
            cx = (r["x1"] + r["x2"]) / 2
            cy = (r["y1"] + r["y2"]) / 2
            d = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
            if d < best_dist:
                best_dist = d
                best = r["text"]
        return best or ""
    except Exception:
        return ""


def _ocr_texts(img_path: str) -> list:
    """Return flat list of visible text strings from a screenshot."""
    try:
        return [r["text"] for r in ocr.find_all(img_path)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# After-state capture (runs on main thread via scheduled task)
# ---------------------------------------------------------------------------

def _capture_after(event_index: int, before_label: str, ts: int):
    """
    Take an after-screenshot, run OCR, and mutate the event dict
    to mark dynamic_label if the clicked label disappeared.
    """
    try:
        after_path = os.path.join(TRACE_DIR, f"{_flow_name}_{ts}_after.png")
        _page_ref.screenshot(path=after_path)
        after_texts = _ocr_texts(after_path)
        is_dynamic = bool(before_label) and before_label not in after_texts
        _events[event_index]["screenshots"]["after"] = after_path
        _events[event_index]["dynamic_label"] = is_dynamic
        if is_dynamic:
            print(f"[RECORDER] '{before_label}' vanished after click → dynamic_label=True")
    except Exception as e:
        print(f"[RECORDER] After-state capture failed: {e}")


# ---------------------------------------------------------------------------
# Network-intercept event processor (runs on main thread — no deadlocks)
# ---------------------------------------------------------------------------

def _handle_recorder_api(route, request):
    if request.method == "POST":
        try:
            data = json.loads(request.post_data)
            _action_queue.put(data)
        except Exception as e:
            print(f"[RECORDER] Failed to parse event: {e}")
    route.fulfill(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        },
        content_type="application/json",
        body='{"status":"ok"}'
    )


def _process_event(action):
    global _pending_annotation, _recording_active
    atype = action.get("type")

    if atype == "click":
        x, y, ts = action["x"], action["y"], action["timestamp"]
        before_path = os.path.join(TRACE_DIR, f"{_flow_name}_{ts}_before.png")
        try:
            _page_ref.screenshot(path=before_path)
        except Exception:
            before_path = None

        before_texts  = _ocr_texts(before_path) if before_path else []
        clicked_label = _nearest_label(x, y, before_path) if before_path else ""

        event = {
            "type": "click", "x": x, "y": y, "timestamp": ts,
            "clicked_label": clicked_label,
            "ocr_visible": before_texts,
            "annotation": _pending_annotation,
            "dynamic_label": False,                        # updated by background thread
            "screenshots": {"before": before_path, "after": None}
        }
        _events.append(event)
        _pending_annotation = None
        print(f"[RECORDER] Click at ({x},{y}) → '{clicked_label}'")

        _scheduled_tasks.append((
            time.time() + 1.0,  # execute 1 second from now
            lambda: _capture_after(len(_events) - 1, clicked_label, ts)
        ))

    elif atype == "annotation":
        _pending_annotation = action["text"]
        print(f"[RECORDER] Annotation queued: '{action['text']}'")

    elif atype == "undo":
        if _events:
            removed = _events.pop()
            print(f"[RECORDER] Undid last event: {removed.get('clicked_label')}")

    elif atype == "stop":
        _recording_active = False
        print("[RECORDER] Stop triggered.")


# ---------------------------------------------------------------------------
# Overlay injection
# ---------------------------------------------------------------------------

def _inject_recorder(page):
    global _page_ref
    _page_ref = page
    page.route("**/*visor-api-event*", _handle_recorder_api)

    page.add_init_script("""
        window.visorSendEvent = function(data) {
            fetch('/visor-api-event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            }).catch(() => {});
        };

        document.addEventListener('click', (e) => {
            if (e.target.closest('#visor-recorder-ui')) return;
            const cc = document.getElementById('visor-click-count');
            if (cc) cc.innerText = parseInt(cc.innerText || "0") + 1;
            window.visorSendEvent({type: 'click', x: e.clientX, y: e.clientY, timestamp: Date.now()});
        }, true);

        function buildOverlay() {
            if (document.getElementById('visor-recorder-ui')) return;
            const ui = document.createElement('div');
            ui.id = 'visor-recorder-ui';
            ui.innerHTML = `
                <div id="visor-panel" style="
                    position: fixed; top: 20px; right: 20px; width: 320px;
                    background: rgba(15, 23, 42, 0.88); backdrop-filter: blur(14px);
                    -webkit-backdrop-filter: blur(14px);
                    border: 1px solid rgba(255,255,255,0.1); border-radius: 16px;
                    padding: 16px; color: white; font-family: 'Inter', system-ui, sans-serif;
                    z-index: 2147483647; display: flex; flex-direction: column; gap: 12px;
                    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.55);
                ">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <div style="width:10px;height:10px;border-radius:50%;background:#ef4444;animation:vPulse 2s infinite;"></div>
                            <span style="font-weight:600;font-size:14px;">Visor Recording</span>
                        </div>
                        <button id="visor-stop-btn" style="background:rgba(239,68,68,.2);color:#ef4444;border:1px solid rgba(239,68,68,.3);border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer;">Stop</button>
                    </div>
                    <div style="font-size:11px;color:rgba(255,255,255,.55);background:rgba(0,0,0,.25);padding:6px 10px;border-radius:8px;display:flex;gap:12px;">
                        <span>Clicks: <b id="visor-click-count">0</b></span>
                        <span>Queued: <b id="visor-ann-queued">—</b></span>
                    </div>
                    <input type="text" id="visor-annotation-input" placeholder="Next click intent (auto-attaches)…" style="background:rgba(0,0,0,.3);color:white;border:1px solid rgba(255,255,255,.15);border-radius:8px;padding:10px 12px;font-size:13px;outline:none;width:100%;box-sizing:border-box;"/>
                    <div style="display:flex;gap:8px;">
                        <button id="visor-annotation-btn" style="flex:1;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:white;border:none;border-radius:8px;padding:10px;font-size:13px;font-weight:600;cursor:pointer;">Queue Annotation</button>
                        <button id="visor-undo-btn" style="background:rgba(255,255,255,.08);color:rgba(255,255,255,.7);border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:10px 14px;font-size:16px;cursor:pointer;" title="Undo last">↩</button>
                    </div>
                </div>
                <style>
                    @keyframes vPulse {
                        0%   { transform:scale(.95); box-shadow:0 0 0 0 rgba(239,68,68,.7); }
                        70%  { transform:scale(1);   box-shadow:0 0 0 6px rgba(239,68,68,0); }
                        100% { transform:scale(.95); box-shadow:0 0 0 0 rgba(239,68,68,0); }
                    }
                    #visor-annotation-input:focus { border-color:#3b82f6 !important; }
                </style>
            `;
            document.body.appendChild(ui);

            document.getElementById('visor-annotation-btn').addEventListener('click', () => {
                const input = document.getElementById('visor-annotation-input');
                if (!input.value.trim()) return;
                window.visorSendEvent({type: 'annotation', text: input.value.trim(), timestamp: Date.now()});
                document.getElementById('visor-ann-queued').innerText = input.value.trim().slice(0, 20) + '…';
                input.value = '';
                const btn = document.getElementById('visor-annotation-btn');
                btn.innerText = 'Queued!';
                setTimeout(() => { btn.innerText = 'Queue Annotation'; }, 1600);
            });

            document.getElementById('visor-annotation-input').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') document.getElementById('visor-annotation-btn').click();
            });

            document.getElementById('visor-undo-btn').addEventListener('click', () => {
                window.visorSendEvent({type: 'undo'});
                const cc = document.getElementById('visor-click-count');
                if (cc && parseInt(cc.innerText) > 0) cc.innerText = parseInt(cc.innerText) - 1;
            });

            document.getElementById('visor-stop-btn').addEventListener('click', () => {
                window.visorSendEvent({type: 'stop'});
            });
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', buildOverlay);
        } else {
            buildOverlay();
        }

        // MutationObserver: auto-reinject if SPA tears out the overlay
        const observer = new MutationObserver(() => {
            if (!document.getElementById('visor-recorder-ui')) buildOverlay();
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
    """)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_recording(flow_name: str, url: str, description: str) -> str:
    """Starts the browser in recording mode and blocks until stopped."""
    os.makedirs(TRACE_DIR, exist_ok=True)
    global _events, _flow_name, _recording_active, _pending_annotation
    _events = []
    _flow_name = flow_name
    _recording_active = True
    _pending_annotation = None

    print(f"[RECORDER] Starting recording for '{flow_name}'.")
    page = browser.init_browser(headless=False, record_video=False)
    _inject_recorder(page)

    print(f"[RECORDER] Navigating to {url}")
    page.goto(url)

    stop_flag = os.path.join(TRACE_DIR, f"{flow_name}_stop.flag")
    if os.path.exists(stop_flag):
        os.remove(stop_flag)

    print("[RECORDER] Active. Use the overlay to annotate. Click Stop or Ctrl+C to finish.")
    try:
        while _recording_active and not os.path.exists(stop_flag):
            # Drain the queue on the main thread — safe with Playwright sync API
            while not _action_queue.empty():
                _process_event(_action_queue.get_nowait())
                
            # Process scheduled tasks (e.g. after-screenshots)
            now = time.time()
            for task in list(_scheduled_tasks):
                execute_at, func = task
                if now >= execute_at:
                    func()
                    _scheduled_tasks.remove(task)
                    
            page.wait_for_timeout(50)
        print("\n[RECORDER] Recording stopped. Saving trace…")
        if os.path.exists(stop_flag):
            os.remove(stop_flag)
    except KeyboardInterrupt:
        print("\n[RECORDER] Stopped via Ctrl+C. Saving trace…")

    # Flush any remaining queued events and tasks
    while not _action_queue.empty():
        _process_event(_action_queue.get_nowait())
    for execute_at, func in _scheduled_tasks:
        func()
    _scheduled_tasks.clear()

    trace_file = os.path.join(TRACE_DIR, f"{flow_name}_trace.json")
    with open(trace_file, "w") as f:
        json.dump({
            "flow": flow_name,
            "url": url,
            "description": description,
            "events": _events
        }, f, indent=2)

    print(f"[RECORDER] Saved trace → {trace_file}")
    return trace_file
