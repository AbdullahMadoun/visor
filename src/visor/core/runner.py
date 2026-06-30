"""
Runner — the execution engine.

Flow:
  1. Navigate to target
  2. Screenshot
  3. OCR: find expected element
  4a. Found → CDP click → short_wait → continue
  4b. Not found → check strategy tree for known fix
      4b-i.  Known fix → apply → retry
      4b-ii. Unknown  → save failure context → print AGENT_NEEDED → poll for fix.json
  5. After all targets → report success rate
  6. If < 100% → re-run failed targets (up to max_retries loops)
"""

import os
import sys
import json
import time
import shutil
import csv
import importlib
from datetime import datetime
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


from visor.core import browser, ocr, clicker, PROJECT_ROOT
from visor.strategy import tree as strategy_tree

HANDSHAKE_DIR = os.path.join(PROJECT_ROOT, "visor_workspace", "agent_handshake")
FAILURE_JSON  = os.path.join(HANDSHAKE_DIR, "failure.json")
FIX_JSON      = os.path.join(HANDSHAKE_DIR, "fix.json")
FAILURES_DIR  = os.path.join(PROJECT_ROOT, "visor_workspace", "logs", "failures")

os.makedirs(HANDSHAKE_DIR, exist_ok=True)
os.makedirs(FAILURES_DIR, exist_ok=True)


def _ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _save_screenshot(label: str) -> str:
    path = os.path.join(FAILURES_DIR, f"{label}_{_ts()}.png")
    return browser.screenshot(save_path=path)

def _signal_agent(step: str, url: str, ocr_found: list, screenshot_path: str):
    """
    Write failure context to failure.json and block until agent writes fix.json.
    """
    # Clean up any stale fix
    if os.path.exists(FIX_JSON):
        os.remove(FIX_JSON)

    payload = {
        "timestamp": datetime.now().isoformat(),
        "url": url,
        "step": step,
        "screenshot": screenshot_path,
        "ocr_results": ocr_found,
        "message": f"AGENT_NEEDED: step='{step}' failed. OCR found: {ocr_found}"
    }
    with open(FAILURE_JSON, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n{'='*60}")
    print(f"[AGENT_NEEDED] step='{step}' on {url}")
    print(f"  Screenshot: {screenshot_path}")
    print(f"  OCR found: {ocr_found}")
    print(f"  Waiting for fix at: {FIX_JSON}")
    print(f"{'='*60}\n")

    # Poll for fix
    for _ in range(600):  # wait up to 10 minutes
        if os.path.exists(FIX_JSON):
            try:
                with open(FIX_JSON) as f:
                    fix = json.load(f)
                os.remove(FIX_JSON)
                print(f"[AGENT_FIX] Received: {fix}")
                # If tree update included, persist to disk
                if "save_to_tree" in fix:
                    tree = strategy_tree.load()
                    for path_str, value in fix["save_to_tree"].items():
                        keys = path_str.split(".")
                        strategy_tree.set_branch(tree, keys, value)
                return fix
            except json.JSONDecodeError:
                # File is actively being written by agent, wait for next tick
                pass
        time.sleep(1)

    print("[AGENT_NEEDED] Timed out waiting for fix. Skipping.")
    return {"action": "skip", "reason": "agent_timeout"}


def safe_dom_action(func, *args, **kwargs):
    """
    Executes a Playwright DOM locator action (like bounding_box) safely.
    If it hits a TimeoutError, it catches it and triggers the AGENT_NEEDED protocol 
    instead of violently crashing the Python process.
    """
    try:
        return func(*args, **kwargs)
    except PlaywrightTimeoutError as e:
        print(f"[DOM_ISOLATION] Caught Playwright TimeoutError: {e}")
        ss_path = _save_screenshot("dom_timeout")
        fix = _signal_agent("safe_dom_action", browser.get_page().url, [], ss_path)
        return {"error": "timeout", "fix": fix}


def scroll_and_collect(target_label: str, max_scrolls: int = 10, scroll_delay_ms: int = 2000) -> bool:
    """
    Native scroller and list pagination manager.
    Scrolls down the page until target_label becomes visible via OCR.
    """
    print(f"[RUNNER] Scrolling to find '{target_label}'...")
    for i in range(max_scrolls):
        img_path = browser.screenshot()
        if img_path and ocr.find(target_label, img_path, exact=False):
            print(f"[RUNNER] Found '{target_label}' after {i} scrolls.")
            return True
        browser.scroll_down(wait_ms=scroll_delay_ms)
    print(f"[RUNNER] Failed to find '{target_label}' after {max_scrolls} scrolls.")
    return False


def ocr_find_and_click(label: str, url: str, flow_key: str, retry: bool = True, bounds: dict = None, state: str = None) -> str:
    """
    Take screenshot, OCR-find label within optional bounds, click it via CDP.
    Returns: 'success' | 'skipped' | 'failed' | 'agent_fixed'
    """
    img_path = browser.screenshot()
    if not img_path:
        return "failed"

    all_text = ocr.summarize(img_path)

    # Use DOM bounding box constraint if provided by the platform script
    if bounds:
        match = ocr.find(
            label, img_path, exact=True,
            bounds=bounds
        )
    else:
        match = ocr.find(label, img_path, exact=True)

    if match:
        print(f"[OCR] Found '{label}' at ({match['x']}, {match['y']}) conf={match['confidence']}")
        clicker.click(match["x"], match["y"])
        return "success"

    # Not found — check strategy tree
    print(f"[OCR] '{label}' not found. Visible text: {all_text}")
    tree = strategy_tree.load()
    
    # Try contextual state match first, then fallback to stateless match
    not_found_branches = {}
    if state:
        not_found_branches = strategy_tree.get(tree, flow_key, state, f"find_{label.replace(' ', '_')}", "not_found") or {}
    if not not_found_branches:
        not_found_branches = strategy_tree.get(tree, flow_key, f"find_{label.replace(' ', '_')}", "not_found") or {}

    for condition, branch in not_found_branches.items():
        # Check if the condition element is visible in OCR
        condition_label = condition.replace("_visible", "").replace("_", " ")
        if any(condition_label.lower() in t.lower() for t in all_text):
            print(f"[TREE] Matched condition '{condition}' → action: {branch['action']}")
            if branch["action"] == "skip":
                return f"skipped:{branch.get('reason', 'unknown')}"
            elif branch["action"] == "click_ocr":
                target = branch["target"]

                # Maintain bounds mapping even in fallback if applicable
                if bounds:
                    target_match = ocr.find(
                        target, img_path, exact=True,
                        bounds=bounds
                    )
                else:
                    target_match = ocr.find(target, img_path, exact=False)

                if target_match:
                    clicker.click(target_match["x"], target_match["y"])
                    wait_after = branch.get("wait_after", 2.5)
                    print(f"[TREE] Waiting {wait_after}s for dropdown/animation...")
                    time.sleep(wait_after)

                    if branch.get("then", "").startswith("retry_find_") and retry:
                        img_after = browser.screenshot()
                        if img_after:
                            connect_match = ocr.find_near(
                                label, img_after,
                                near_x=target_match["x"],
                                near_y=target_match["y"],
                                radius=400,
                                exact=True,
                                min_conf=0.6
                            )
                            if connect_match:
                                print(f"[OCR] Found '{label}' in dropdown/near at "
                                      f"({connect_match['x']}, {connect_match['y']})")
                                clicker.click(connect_match["x"], connect_match["y"])
                                return "success"
                            return ocr_find_and_click(label, url, flow_key, retry=False)
                    elif branch.get("then", "") == "retry" and retry:
                        print(f"[TREE] Verifying intended button '{label}' after fallback...")
                        # Geometrically verify the intended button actually exists after fallback
                        return ocr_find_and_click(label, url, flow_key, retry=False)
                    elif branch.get("then", "") == "continue":
                        # If the tree explicitly says continue, we assume the click itself was the goal (e.g. Apply)
                        # We verify the state visually changed to prove the click wasn't dead
                        img_after = browser.screenshot()
                        if img_after and ocr.find(target, img_after, exact=False):
                            print(f"[TREE] Warning: '{target}' still visible after click. Fallback might have failed.")
                        return "agent_fixed"
                        
                    return "agent_fixed"
                else:
                    print(f"[TREE] Strategy failed: Target '{target}' not found by OCR with sufficient confidence.")
                    # Fall through to agent escalation

    # Truly unknown — escalate to agent
    ss_path = _save_screenshot(f"failure_{label.replace(' ', '_')}")
    shutil.copy(img_path, ss_path)
    fix = _signal_agent(f"find_{label}", url, all_text, ss_path)

    if fix.get("action") == "skip":
        return f"skipped:{fix.get('reason', 'agent')}"
    elif fix.get("action") == "ocr_click":
        target_match = ocr.find(fix["target"], browser.screenshot(), exact=False)
        if target_match:
            clicker.click(target_match["x"], target_match["y"])
            clicker.short_wait()
            if fix.get("then") == "retry":
                return ocr_find_and_click(label, url, flow_key, retry=False, bounds=bounds, state=state)
            return "agent_fixed"
    elif fix.get("action") == "retry":
        return ocr_find_and_click(label, url, flow_key, retry=False, bounds=bounds, state=state)
    elif fix.get("action") == "agent_fixed":
        return "agent_fixed"
    elif fix.get("action") == "restart_flow":
        return "restart_flow"
        
    return "failed"


def verify_ocr(label: str) -> bool:
    """Take fresh screenshot and verify label is present."""
    img_path = browser.screenshot()
    if not img_path:
        return False
    match = ocr.find(label, img_path, exact=True)
    all_text = ocr.summarize(img_path)
    print(f"[VERIFY] Looking for '{label}'. OCR found: {all_text}")
    return match is not None


def run_flow(flow_fn, targets: list, results_csv: str, max_retries: int = 1):
    """
    Main loop:
      - Run flow on all targets
      - Track success rate
      - Re-run failures up to max_retries until 100% or exhausted
    """
    results = {t: "pending" for t in targets}

    # Load existing results if resuming
    if os.path.exists(results_csv):
        with open(results_csv) as f:
            for row in csv.DictReader(f):
                key = row.get("target", row.get("url", "")).strip()
                if key and row["status"] in ("success", "skipped"):
                    results[key] = row["status"]

    for attempt in range(1, max_retries + 1):
        pending = [url for url, s in results.items() if s in ("pending", "failed")]
        if not pending:
            break

        print(f"\n{'='*60}")
        print(f"[RUN] Attempt {attempt}/{max_retries} — {len(pending)} targets")
        print(f"{'='*60}")

        for url in pending:
            print(f"\n[TARGET] {url}")
            try:
                status = flow_fn(url)
            except Exception as e:
                print(f"[ERROR] Target crashed unexpectedly: {e}")
                status = "failed"
                
            if status == "restart_flow":
                print("[RUNNER] restart_flow requested! Hot-reloading active Python module...")
                if hasattr(sys.modules[__name__], '_active_module') and sys.modules[__name__]._active_module:
                    importlib.reload(sys.modules[__name__]._active_module)
                    print("[RUNNER] Module reloaded successfully. Retrying target from scratch...")
                # Push back into pending to restart from step 1
                results[url] = "pending"
                continue

            results[url] = status
            print(f"[RESULT] {url} → {status}")

            # Write running results to CSV
            _write_csv(results, results_csv)

            if status == "success":
                clicker.human_wait()
            else:
                clicker.short_wait()

        # Report
        success = sum(1 for s in results.values() if s == "success")
        skipped = sum(1 for s in results.values() if "skipped" in str(s))
        failed  = sum(1 for s in results.values() if s == "failed")
        total   = len(targets)
        actionable = total - skipped
        rate = (success / actionable * 100) if actionable > 0 else 100

        print(f"\n[REPORT] Attempt {attempt}: {success}/{actionable} actionable succeeded ({rate:.0f}%)")
        print(f"         Skipped: {skipped} | Failed: {failed}")

        if rate == 100.0:
            print("[DONE] 100% success rate achieved!")
            break

    _write_csv(results, results_csv)
    return results


def _write_csv(results: dict, path: str):
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["target", "url", "status", "timestamp"])
        writer.writeheader()
        for target, status in results.items():
            writer.writerow({"target": target, "url": target, "status": status, "timestamp": datetime.now().isoformat()})
