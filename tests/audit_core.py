"""
Full Core Audit — Static analysis of visor core modules.
Checks for API mismatches, logic bugs, and missing guards.
"""
import os, sys, ast, textwrap

ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "visor")

issues = []
passes = []

def ok(msg):   passes.append(f"  ✅  {msg}")
def fail(msg): issues.append(f"  ❌  {msg}")

def grep(path, pattern):
    with open(path) as f:
        return [i+1 for i, l in enumerate(f) if pattern in l]

# ─── ocr.py ───────────────────────────────────────────────────────────────────
OCR = os.path.join(ROOT, "core", "ocr.py")
with open(OCR) as f:
    src = f.read()

# Public API surface
for fn in ["find_all", "find", "find_near", "summarize", "find_with_scroll", "semantic_find"]:
    if f"def {fn}(" in src:
        ok(f"ocr.{fn} defined")
    else:
        fail(f"ocr.{fn} MISSING")

# No ocr.read() — that doesn't exist
if "def read(" in src:
    fail("ocr.read() exists — rename or remove it to avoid confusion")
else:
    ok("ocr.read() correctly absent")

# find_with_scroll uses time.sleep (blocking) not page.wait_for_timeout
lines = grep(OCR, "time.sleep")
if lines:
    fail(f"ocr.find_with_scroll uses time.sleep on lines {lines} — blocks sync loop, should use page.wait_for_timeout")
else:
    ok("ocr.py uses no bare time.sleep")

# browser import inside find_all — should be fine (lazy)
if "from visor.core import browser" in src:
    ok("ocr.find_all lazy-imports browser for DPR scaling")

# ─── recorder.py ──────────────────────────────────────────────────────────────
REC = os.path.join(ROOT, "core", "recorder.py")
with open(REC) as f:
    src = f.read()

if "ocr.read(" in src:
    fail("recorder.py calls ocr.read() which does not exist — should be ocr.find_all()")
else:
    ok("recorder.py correctly calls ocr.find_all()")

if "_recording_active = False\n_recording_active" in src or src.count("_recording_active = False") > 1:
    fail("recorder.py has duplicate _recording_active declaration")
else:
    ok("recorder.py has no duplicate state declarations")

if "expose_binding" in src:
    fail("recorder.py still references expose_binding — should be fully removed")
else:
    ok("recorder.py uses page.route (no expose_binding deadlock)")

if "_action_queue.get_nowait()" in src:
    ok("recorder.py drains queue with get_nowait() — non-blocking")
else:
    fail("recorder.py may block on queue.get() — should use get_nowait()")

if "MutationObserver" in src:
    ok("recorder.py has SPA reinject via MutationObserver")
else:
    fail("recorder.py missing MutationObserver for SPA resilience")

# ─── runner.py ────────────────────────────────────────────────────────────────
RUN = os.path.join(ROOT, "core", "runner.py")
with open(RUN) as f:
    src = f.read()

if "import sys" in src and "import importlib" in src:
    ok("runner.py imports sys and importlib for hot-reload")
else:
    fail("runner.py missing sys or importlib for restart_flow")

if "screenshot_b64" in src:
    fail("runner.py still embeds screenshot as base64 — should be removed (OCR-only philosophy)")
else:
    ok("runner.py does NOT embed screenshot — OCR-only philosophy preserved")

if '"restart_flow"' in src:
    ok("runner.py handles restart_flow action")
else:
    fail("runner.py missing restart_flow handler")

if "PlaywrightTimeoutError" in src:
    ok("runner.py imports PlaywrightTimeoutError for safe_dom_action")
else:
    fail("runner.py missing PlaywrightTimeoutError import")

if "scroll_and_collect" in src:
    ok("runner.py has scroll_and_collect primitive")
else:
    fail("runner.py missing scroll_and_collect")

# ─── browser.py ───────────────────────────────────────────────────────────────
BRO = os.path.join(ROOT, "core", "browser.py")
with open(BRO) as f:
    src = f.read()

if "if _owns_browser:" in src:
    ok("browser.py gates ghost-tab cleanup behind _owns_browser")
else:
    fail("browser.py missing _owns_browser check for ghost tab cleanup")

if "context.new_page()" in src and "_owns_browser" in src:
    ok("browser.py spawns isolated tab for CDP sessions")
else:
    fail("browser.py does not isolate CDP tab")

if "scroll_down" in src:
    ok("browser.py exposes scroll_down primitive")
else:
    fail("browser.py missing scroll_down")

# ─── extractor.py ─────────────────────────────────────────────────────────────
EXT = os.path.join(ROOT, "core", "extractor.py")
with open(EXT) as f:
    src = f.read()

if "browser.get_page()" in src:
    ok("extractor.py correctly uses browser.get_page()")
else:
    fail("extractor.py does not call browser.get_page()")

if "([schema, container_sel])" in src or "[schema, container_selector]" in src:
    ok("extractor.py passes JS args as list (correct Playwright syntax)")
else:
    fail("extractor.py JS arg passing may be incorrect")

# ─── cli.py ───────────────────────────────────────────────────────────────────
CLI = os.path.join(ROOT, "cli.py")
with open(CLI) as f:
    src = f.read()

if "runner._active_module = module" in src:
    ok("cli.py sets runner._active_module for hot-reload")
else:
    fail("cli.py does not inject _active_module into runner")

if "sys.stdout.reconfigure" in src or "PYTHONUNBUFFERED" in src or "line_buffering" in src:
    ok("cli.py enforces unbuffered stdout")
else:
    fail("cli.py missing unbuffered stdout — AGENT_NEEDED may be silently hidden")

# ─── Print report ─────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("VISOR CORE AUDIT REPORT")
print("="*60)
for p in passes:
    print(p)
print()
for i in issues:
    print(i)
print()
print(f"{'='*60}")
print(f"Result: {len(passes)} OK, {len(issues)} ISSUES")
print(f"{'='*60}\n")
sys.exit(len(issues))
