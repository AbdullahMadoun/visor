"""
Recorder Stress Test
Tests the full recording pipeline without needing a real website:
- Network intercept routing
- Event queue processing
- OCR nearest-label resolution
- Before/after screenshot capture
- Annotation queuing and auto-attach
- Undo
- Rapid-fire click bursts
- Stop signal
"""
import os
import sys
import json
import time
import threading

# Point at the src tree
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from visor.core import recorder as rec
from visor.core import browser

RESULTS = []

# ── helpers ────────────────────────────────────────────────────────────────

def _fire_event(page, event: dict):
    """Simulate a browser event via JS fetch → network intercept."""
    page.evaluate("""
        (data) => fetch('/visor-api-event', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        })
    """, event)
    time.sleep(0.15)   # let the intercept and queue drain tick


def _drain(page, ticks: int = 3):
    """Let the main loop drain the queue and scheduled tasks a few times."""
    for _ in range(ticks):
        while not rec._action_queue.empty():
            rec._process_event(rec._action_queue.get_nowait())
            
        now = time.time()
        for task in list(rec._scheduled_tasks):
            execute_at, func = task
            if now >= execute_at:
                func()
                rec._scheduled_tasks.remove(task)
                
        page.wait_for_timeout(60)


# ── test runner ────────────────────────────────────────────────────────────

def run_tests():
    print("\n" + "="*60)
    print("VISOR RECORDER STRESS TEST")
    print("="*60)

    # Reset module state
    rec._events.clear()
    rec._flow_name = "stress_test"
    rec._recording_active = True
    rec._pending_annotation = None
    while not rec._action_queue.empty():
        rec._action_queue.get_nowait()

    os.makedirs(rec.TRACE_DIR, exist_ok=True)

    # Init browser and inject recorder
    page = browser.init_browser(headless=True)
    rec._page_ref = page
    rec._inject_recorder(page)

    # Navigate to a real domain so fetch('/visor-api-event') has a valid base URL
    page.goto("https://example.com")
    page.evaluate("""
        document.body.innerHTML = `
            <div style="background:#111;color:white;font-family:sans-serif;padding:40px;height:100vh;">
                <h1>Recorder Test Page</h1>
                <button id="btn-a" style="padding:12px 24px;margin:8px;font-size:18px;">Connect</button>
                <button id="btn-b" style="padding:12px 24px;margin:8px;font-size:18px;">More</button>
                <button id="btn-c" style="padding:12px 24px;margin:8px;font-size:18px;">Follow</button>
                <p id="status">Waiting...</p>
            </div>
        `;
    """)
    time.sleep(0.5)

    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ PASS  {name}")
            passed += 1
        else:
            print(f"  ❌ FAIL  {name}")
            failed += 1

    # ── Test 1: Single click registers ────────────────────────────────────
    print("\n[1] Single click registration")
    _fire_event(page, {"type": "click", "x": 100, "y": 200, "timestamp": 1000001})
    _drain(page)
    check("Event appended to _events", len(rec._events) == 1)
    check("Event type is 'click'",     rec._events[0]["type"] == "click")
    check("x/y preserved",            rec._events[0]["x"] == 100 and rec._events[0]["y"] == 200)

    # ── Test 2: Annotation queues then auto-attaches ───────────────────────
    print("\n[2] Annotation queuing + auto-attach")
    _fire_event(page, {"type": "annotation", "text": "Clicking Connect button", "timestamp": 1000002})
    _drain(page)
    check("Annotation stored in _pending_annotation", rec._pending_annotation == "Clicking Connect button")

    _fire_event(page, {"type": "click", "x": 150, "y": 200, "timestamp": 1000003})
    _drain(page)
    check("Annotation attached to click event", rec._events[1].get("annotation") == "Clicking Connect button")
    check("_pending_annotation cleared after attach", rec._pending_annotation is None)

    # ── Test 3: Undo removes last event ───────────────────────────────────
    print("\n[3] Undo")
    count_before = len(rec._events)
    _fire_event(page, {"type": "undo"})
    _drain(page)
    check("Undo removes last event", len(rec._events) == count_before - 1)

    # ── Test 4: Rapid-fire clicks (burst of 20) ───────────────────────────
    print("\n[4] Rapid-fire burst (20 clicks)")
    count_before = len(rec._events)
    for i in range(20):
        _fire_event(page, {"type": "click", "x": 50 + i, "y": 100, "timestamp": 2000000 + i})
    _drain(page, ticks=10)
    burst_count = len(rec._events) - count_before
    check(f"All 20 burst clicks registered (got {burst_count})", burst_count == 20)

    # ── Test 5: Multiple annotations don't stack ──────────────────────────
    print("\n[5] Double annotation (last one wins)")
    _fire_event(page, {"type": "annotation", "text": "First annotation", "timestamp": 3000001})
    _drain(page)
    _fire_event(page, {"type": "annotation", "text": "Second annotation", "timestamp": 3000002})
    _drain(page)
    check("Second annotation overwrites first", rec._pending_annotation == "Second annotation")

    # Consume pending with a click
    _fire_event(page, {"type": "click", "x": 200, "y": 200, "timestamp": 3000003})
    _drain(page)

    # ── Test 6: Stop signal halts recording ───────────────────────────────
    print("\n[6] Stop signal")
    rec._recording_active = True  # ensure it's active
    _fire_event(page, {"type": "stop"})
    _drain(page)
    check("_recording_active set to False by stop", not rec._recording_active)

    # ── Test 7: Trace file saves cleanly ──────────────────────────────────
    print("\n[7] Trace file serialization")
    trace_path = os.path.join(rec.TRACE_DIR, "stress_test_trace.json")
    with open(trace_path, "w") as f:
        json.dump({
            "flow": "stress_test",
            "url": "about:blank",
            "description": "Stress test",
            "events": rec._events
        }, f, indent=2)
    check("Trace file written", os.path.exists(trace_path))
    with open(trace_path) as f:
        loaded = json.load(f)
    check("Trace JSON valid and events present", len(loaded["events"]) > 0)
    check("Every click event has required keys", all(
        {"type","x","y","timestamp","clicked_label","annotation","dynamic_label","screenshots"} <= e.keys()
        for e in loaded["events"] if e["type"] == "click"
    ))

    # ── Test 8: OCR helpers don't crash on bad paths ───────────────────────
    print("\n[8] OCR helpers robustness")
    result = rec._nearest_label(0, 0, "/nonexistent/path.png")
    check("_nearest_label returns '' on bad path", result == "")
    result = rec._ocr_texts("/nonexistent/path.png")
    check("_ocr_texts returns [] on bad path", result == [])

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {passed+failed} tests")
    print("="*60 + "\n")

    browser.close()
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
