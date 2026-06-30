import os
import json
import threading
from visor.core import browser, ocr, PROJECT_ROOT

TRACE_DIR = os.path.join(PROJECT_ROOT, "visor_workspace", "logs", "traces")

# --- Module-level state ---
_events = []
_flow_name = "default"
_recording_active = False
_pending_annotation = None  # queued annotation — auto-attaches to next click
_page_ref = None            # held so background thread can take after-screenshots


# ---------------------------------------------------------------------------
# OCR helpers (run on Python side so we stay off the JS thread)
# ---------------------------------------------------------------------------

def _nearest_label(x: int, y: int, img_path: str) -> str:
    """Return the OCR text whose bounding-box centre is closest to (x, y)."""
    try:
        results = ocr.read(img_path)  # list of {text, x, y, w, h, conf}
        best, best_dist = None, float("inf")
        for r in results:
            cx = r["x"] + r["w"] / 2
            cy = r["y"] + r["h"] / 2
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
        return [r["text"] for r in ocr.read(img_path)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# After-state capture (runs in a background thread)
# ---------------------------------------------------------------------------

def _capture_after(event_index: int, before_label: str, ts: int):
    """
    Wait 1 s, take an after-screenshot, run OCR, and mutate the event dict
    to mark dynamic_label if the clicked label disappeared.
    """
    try:
        _page_ref.wait_for_timeout(1000)
        after_path = os.path.join(TRACE_DIR, f"{_flow_name}_{ts}_after.png")
        _page_ref.screenshot(path=after_path)
        after_texts = _ocr_texts(after_path)
        is_dynamic = before_label and before_label not in after_texts
        _events[event_index]["screenshots"]["after"] = after_path
        _events[event_index]["dynamic_label"] = is_dynamic
        if is_dynamic:
            print(f"[RECORDER] '{before_label}' vanished after click → dynamic_label=True")
    except Exception as e:
        print(f"[RECORDER] After-state capture failed: {e}")


# ---------------------------------------------------------------------------
# Python-side bindings (called from JS via expose_binding)
# ---------------------------------------------------------------------------

def _on_click(source, x, y, timestamp):
    global _pending_annotation
    page = _page_ref

    # Before screenshot
    before_path = os.path.join(TRACE_DIR, f"{_flow_name}_{timestamp}_before.png")
    try:
        page.screenshot(path=before_path)
    except Exception:
        before_path = None

    before_texts = _ocr_texts(before_path) if before_path else []
    clicked_label = _nearest_label(x, y, before_path) if before_path else ""

    event = {
        "type": "click",
        "x": x,
        "y": y,
        "timestamp": timestamp,
        "clicked_label": clicked_label,
        "ocr_visible": before_texts,
        "annotation": _pending_annotation,
        "dynamic_label": False,          # updated by background thread
        "screenshots": {
            "before": before_path,
            "after": None,               # updated by background thread
        }
    }
    _events.append(event)
    event_index = len(_events) - 1
    _pending_annotation = None           # consume queued annotation

    print(f"[RECORDER] Click at ({x},{y}) → '{clicked_label}'")

    # Kick off after-state detection without blocking browsing
    t = threading.Thread(target=_capture_after, args=(event_index, clicked_label, timestamp), daemon=True)
    t.start()


def _on_annotation(source, text, timestamp):
    global _pending_annotation
    _pending_annotation = text
    print(f"[RECORDER] Annotation queued: '{text}' (attaches to next click)")


def _on_undo(source):
    if _events:
        removed = _events.pop()
        print(f"[RECORDER] Undid last event: {removed.get('clicked_label') or removed.get('text', '?')}")


def _on_stop(source):
    global _recording_active
    _recording_active = False
    print("[RECORDER] Stop triggered from overlay.")


# ---------------------------------------------------------------------------
# Overlay injection
# ---------------------------------------------------------------------------

def _inject_recorder(page):
    global _page_ref
    _page_ref = page

    page.expose_binding("visorLogClick",       _on_click)
    page.expose_binding("visorLogAnnotation",  _on_annotation)
    page.expose_binding("visorUndo",           _on_undo)
    page.expose_binding("visorStopRecording",  _on_stop)

    page.add_init_script("""
        // --- Click listener ---
        document.addEventListener('click', (e) => {
            if (e.target.closest('#visor-recorder-ui')) return;
            window.visorLogClick(e.clientX, e.clientY, Date.now());
        }, true);

        // --- Overlay factory ---
        function buildOverlay() {
            if (document.getElementById('visor-recorder-ui')) return;
            const ui = document.createElement('div');
            ui.id = 'visor-recorder-ui';
            ui.innerHTML = `
                <div id="visor-panel" style="
                    position: fixed; top: 20px; right: 20px; width: 320px;
                    background: rgba(15, 23, 42, 0.88);
                    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
                    border: 1px solid rgba(255,255,255,0.1); border-radius: 16px;
                    padding: 16px; color: white;
                    font-family: 'Inter', system-ui, sans-serif;
                    z-index: 2147483647;
                    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.55);
                    display: flex; flex-direction: column; gap: 12px;
                ">
                    <!-- Header -->
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <div style="width:10px;height:10px;border-radius:50%;background:#ef4444;animation:vPulse 2s infinite;"></div>
                            <span style="font-weight:600;font-size:14px;letter-spacing:.5px;">Visor Recording</span>
                        </div>
                        <button id="visor-stop-btn" style="
                            background:rgba(239,68,68,.2);color:#ef4444;
                            border:1px solid rgba(239,68,68,.3);border-radius:6px;
                            padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer;">Stop</button>
                    </div>

                    <!-- Stats bar -->
                    <div id="visor-stats" style="
                        font-size:11px;color:rgba(255,255,255,.55);
                        display:flex;gap:12px;padding:6px 10px;
                        background:rgba(0,0,0,.25);border-radius:8px;">
                        <span>Clicks: <b id="visor-click-count">0</b></span>
                        <span>Annotations: <b id="visor-ann-count">0</b></span>
                        <span id="visor-last-label" style="flex:1;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></span>
                    </div>

                    <!-- Annotation input -->
                    <div style="display:flex;flex-direction:column;gap:8px;">
                        <input type="text" id="visor-annotation-input"
                            placeholder="Next click intent (auto-attaches)…" style="
                            background:rgba(0,0,0,.3);
                            border:1px solid rgba(255,255,255,.15);border-radius:8px;
                            padding:10px 12px;color:white;font-size:13px;outline:none;
                            width:100%;box-sizing:border-box;transition:border-color .2s;"/>
                        <div style="display:flex;gap:8px;">
                            <button id="visor-annotation-btn" style="
                                flex:1;background:linear-gradient(135deg,#3b82f6,#8b5cf6);
                                color:white;border:none;border-radius:8px;padding:10px;
                                font-size:13px;font-weight:600;cursor:pointer;">Queue Annotation</button>
                            <button id="visor-undo-btn" style="
                                background:rgba(255,255,255,.08);color:rgba(255,255,255,.7);
                                border:1px solid rgba(255,255,255,.12);border-radius:8px;
                                padding:10px 14px;font-size:16px;cursor:pointer;" title="Undo last event">↩</button>
                        </div>
                    </div>
                </div>
                <style>
                    @keyframes vPulse {
                        0%   { transform:scale(.95); box-shadow:0 0 0 0 rgba(239,68,68,.7); }
                        70%  { transform:scale(1);   box-shadow:0 0 0 6px rgba(239,68,68,0); }
                        100% { transform:scale(.95); box-shadow:0 0 0 0 rgba(239,68,68,0); }
                    }
                    #visor-annotation-input:focus { border-color:#3b82f6 !important; }
                    #visor-annotation-btn:hover   { opacity:.9; }
                    #visor-stop-btn:hover         { background:rgba(239,68,68,.35) !important; }
                    #visor-undo-btn:hover         { background:rgba(255,255,255,.15) !important; }
                </style>
            `;
            document.body.appendChild(ui);

            // --- Live stats state ---
            let clickCount = 0, annCount = 0;

            // Intercept click events to update counter + last label
            document.addEventListener('visor-click-fired', (e) => {
                clickCount++;
                document.getElementById('visor-click-count').innerText = clickCount;
                if (e.detail) document.getElementById('visor-last-label').innerText = e.detail;
            });

            // Queue annotation on button click or Enter
            document.getElementById('visor-annotation-btn').addEventListener('click', () => {
                const input = document.getElementById('visor-annotation-input');
                const text  = input.value.trim();
                if (!text) return;
                window.visorLogAnnotation(text, Date.now());
                input.value = '';
                annCount++;
                document.getElementById('visor-ann-count').innerText = annCount;
                const btn = document.getElementById('visor-annotation-btn');
                btn.innerText = 'Queued!';
                setTimeout(() => btn.innerText = 'Queue Annotation', 1500);
            });

            document.getElementById('visor-annotation-input').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') document.getElementById('visor-annotation-btn').click();
            });

            document.getElementById('visor-undo-btn').addEventListener('click', () => {
                window.visorUndo();
                if (clickCount > 0) { clickCount--; document.getElementById('visor-click-count').innerText = clickCount; }
            });

            document.getElementById('visor-stop-btn').addEventListener('click', () => window.visorStopRecording());
        }

        // Build on load
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
            page.wait_for_timeout(200)
        print("\n[RECORDER] Recording stopped. Saving trace…")
        if os.path.exists(stop_flag):
            os.remove(stop_flag)
    except KeyboardInterrupt:
        print("\n[RECORDER] Stopped via Ctrl+C. Saving trace…")

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
