import os
import json
import queue
import time
from visor.core import browser, ocr, WORKSPACE_DIR

TRACE_DIR = os.path.join(WORKSPACE_DIR, "logs", "traces")

class RecorderContext:
    def __init__(self, flow_name: str, url: str = "", description: str = ""):
        self.flow_name = flow_name
        self.url = url
        self.description = description
        self.events = []
        self.active = False
        self.pending_annotation = None
        self.page_ref = None
        self.action_queue = queue.Queue()
        self.scheduled_tasks = []

# Active recorder context
_ctx = RecorderContext("default")

# Module-level aliases for backwards compatibility and test harnesses
_events = _ctx.events
_flow_name = _ctx.flow_name
_recording_active = _ctx.active
_pending_annotation = _ctx.pending_annotation
_page_ref = _ctx.page_ref
_action_queue = _ctx.action_queue
_scheduled_tasks = _ctx.scheduled_tasks


def _sync_module_aliases():
    """Synchronize module-level aliases with active context."""
    global _events, _flow_name, _recording_active, _pending_annotation, _page_ref, _action_queue, _scheduled_tasks
    _events = _ctx.events
    _flow_name = _ctx.flow_name
    _recording_active = _ctx.active
    _pending_annotation = _ctx.pending_annotation
    _page_ref = _ctx.page_ref
    _action_queue = _ctx.action_queue
    _scheduled_tasks = _ctx.scheduled_tasks


def _nearest_label(x: int, y: int, img_path: str) -> str:
    """Return the OCR text whose bounding-box centre is closest to (x, y)."""
    try:
        results = ocr.find_all(img_path)
        return _nearest_label_from_items(x, y, results)
    except Exception:
        return ""


def _nearest_label_from_items(x: int, y: int, items: list) -> str:
    """Find closest OCR item to (x, y) without re-running OCR inference."""
    best, best_dist = None, float("inf")
    for r in items:
        cx = (r["x1"] + r["x2"]) / 2
        cy = (r["y1"] + r["y2"]) / 2
        d = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
        if d < best_dist:
            best_dist = d
            best = r["text"]
    return best or ""


def _ocr_texts(img_path: str) -> list:
    """Return flat list of visible text strings from a screenshot."""
    try:
        return [r["text"] for r in ocr.find_all(img_path)]
    except Exception:
        return []


def _capture_after(event: dict, before_label: str, ts: int):
    """
    Take an after-screenshot, run OCR, and mutate the event dict.
    Safely ignores undone events to prevent race conditions and trace corruption.
    """
    global _ctx
    if not _ctx or event not in _ctx.events:
        return  # Event was undone before after-capture completed

    try:
        after_path = os.path.join(TRACE_DIR, f"{_ctx.flow_name}_{ts}_after.png")
        _ctx.page_ref.screenshot(path=after_path)
        after_texts = _ocr_texts(after_path)
        is_dynamic = bool(before_label) and before_label not in after_texts
        event["screenshots"]["after"] = after_path
        event["dynamic_label"] = is_dynamic
        if is_dynamic:
            print(f"[RECORDER] '{before_label}' vanished after click -> dynamic_label=True")
    except Exception as e:
        print(f"[RECORDER] After-state capture failed: {e}")


def _handle_recorder_api(route, request):
    """Network intercept route handler with payload validation."""
    if request.method == "POST":
        try:
            data = json.loads(request.post_data)
            if isinstance(data, dict) and "type" in data and _ctx:
                _ctx.action_queue.put(data)
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


def _process_event(action: dict):
    """Processes a single UI interaction event safely."""
    global _ctx, _recording_active, _pending_annotation
    if not _ctx or not isinstance(action, dict):
        return

    atype = action.get("type")
    if atype == "click":
        if "x" not in action or "y" not in action or "timestamp" not in action:
            return
        x, y, ts = action["x"], action["y"], action["timestamp"]
        before_path = os.path.join(TRACE_DIR, f"{_ctx.flow_name}_{ts}_before.png")
        try:
            _ctx.page_ref.screenshot(path=before_path)
        except Exception:
            before_path = None

        # Perform OCR once per click
        ocr_items = ocr.find_all(before_path) if before_path else []
        before_texts = [r["text"] for r in ocr_items]
        clicked_label = _nearest_label_from_items(x, y, ocr_items)

        event = {
            "type": "click", "x": x, "y": y, "timestamp": ts,
            "clicked_label": clicked_label,
            "ocr_visible": before_texts,
            "annotation": _ctx.pending_annotation,
            "dynamic_label": False,
            "screenshots": {"before": before_path, "after": None}
        }
        _ctx.events.append(event)
        _ctx.pending_annotation = None
        _sync_module_aliases()
        print(f"[RECORDER] Click at ({x},{y}) -> '{clicked_label}'")

        # Pass event dict reference directly to prevent index drift on undo
        _ctx.scheduled_tasks.append((
            time.time() + 1.0,
            lambda ev=event, lbl=clicked_label, t=ts: _capture_after(ev, lbl, t)
        ))

    elif atype == "annotation":
        ann_text = action.get("text", "")
        _ctx.pending_annotation = ann_text
        _sync_module_aliases()
        print(f"[RECORDER] Annotation queued: '{ann_text}'")

    elif atype == "undo":
        if _ctx.events:
            removed = _ctx.events.pop()
            _sync_module_aliases()
            print(f"[RECORDER] Undid last event: {removed.get('clicked_label')}")

    elif atype == "stop":
        _ctx.active = False
        _sync_module_aliases()
        print("[RECORDER] Stop triggered.")


def _inject_recorder(page):
    global _ctx
    if _ctx:
        _ctx.page_ref = page
    _sync_module_aliases()

    page.route("**/visor-api-event", _handle_recorder_api)
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

        const observer = new MutationObserver(() => {
            if (!document.getElementById('visor-recorder-ui')) buildOverlay();
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
    """)


def start_recording(flow_name: str, url: str, description: str) -> str:
    """Starts the browser in recording mode and blocks until stopped."""
    os.makedirs(TRACE_DIR, exist_ok=True)
    global _ctx
    _ctx = RecorderContext(flow_name, url, description)
    _ctx.active = True
    _sync_module_aliases()

    print(f"[RECORDER] Starting recording for '{flow_name}'.")
    page = browser.init_browser(headless=False, record_video=False)
    _ctx.page_ref = page
    _inject_recorder(page)

    print(f"[RECORDER] Navigating to {url}")
    page.goto(url)

    stop_flag = os.path.join(TRACE_DIR, f"{flow_name}_stop.flag")
    if os.path.exists(stop_flag):
        os.remove(stop_flag)

    print("[RECORDER] Active. Use the overlay to annotate. Click Stop or Ctrl+C to finish.")
    try:
        while _ctx.active and not os.path.exists(stop_flag):
            while not _ctx.action_queue.empty():
                _process_event(_ctx.action_queue.get_nowait())

            now = time.time()
            for task in list(_ctx.scheduled_tasks):
                execute_at, func = task
                if now >= execute_at:
                    func()
                    _ctx.scheduled_tasks.remove(task)

            page.wait_for_timeout(50)
    except KeyboardInterrupt:
        print("\n[RECORDER] Stopped via Ctrl+C. Saving trace…")
    except Exception as e:
        print(f"\n[RECORDER] Browser or session ended ({e}). Saving trace…")
    finally:
        print("\n[RECORDER] Flushing final events and saving trace…")
        if os.path.exists(stop_flag):
            try:
                os.remove(stop_flag)
            except OSError:
                pass

        while not _ctx.action_queue.empty():
            _process_event(_ctx.action_queue.get_nowait())
        for execute_at, func in list(_ctx.scheduled_tasks):
            try:
                func()
            except Exception:
                pass
        _ctx.scheduled_tasks.clear()

        trace_file = os.path.join(TRACE_DIR, f"{flow_name}_trace.json")
        with open(trace_file, "w") as f:
            json.dump({
                "flow": flow_name,
                "url": url,
                "description": description,
                "events": _ctx.events
            }, f, indent=2)

        print(f"[RECORDER] Saved trace -> {trace_file}")
        _ctx.active = False
        _sync_module_aliases()

    return trace_file
