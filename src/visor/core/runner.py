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
  5. If the flow declares a GOAL: the goal text must be on screen at the end, on two
     reads a moment apart. Not there → the target failed, whatever the clicks reported,
     and the agent is asked why (kind "goal_not_met").
  6. Agent fixes are on probation: their save_to_tree branches are written to tree.json
     only after the target they were made for succeeds. Fixes that don't survive are
     discarded and listed in the next failure.json as rejected_fixes.
  7. After all targets → report success rate
  8. If < 100% → re-run failed targets (up to max_retries loops)
"""

import os
import sys
import json
import time
import random
import shutil
import csv
import importlib
import importlib.util
from datetime import datetime
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


from visor.config import settings
from visor.core import browser, ocr, clicker, actions, WORKSPACE_DIR
from visor.errors import VisorError, Skip, RestartFlow
from visor.strategy import tree as strategy_tree

HANDSHAKE_DIR = os.path.join(WORKSPACE_DIR, "agent_handshake")
FAILURE_JSON  = os.path.join(HANDSHAKE_DIR, "failure.json")
FIX_JSON      = os.path.join(HANDSHAKE_DIR, "fix.json")
FAILURES_DIR  = os.path.join(WORKSPACE_DIR, "logs", "failures")

# Statuses that count as finished when resuming a run
DONE_STATUSES = ("success", "agent_fixed")

# How many times one target may be restarted (restart_flow) in a row before it counts as failed
MAX_RESTARTS = 3

# Tree branches every flow can use, e.g. "a 'More' menu hides the button"
GLOBAL_KEY = "_global"

# Agent fixes waiting for proof, and fixes that failed it (shown to the agent next time)
_probation = []   # [(keys, branch)]
_rejected = []    # [{"branch": "...", "fix": {...}, "why": "..."}]
_in_target = False
_current_target = None


def _ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _save_screenshot(label: str) -> str:
    os.makedirs(FAILURES_DIR, exist_ok=True)
    path = os.path.join(FAILURES_DIR, f"{label}_{_ts()}.png")
    return browser.screenshot(save_path=path)

def _write_json_atomic(path: str, payload: dict):
    """Readers (agents, supervisors) never see a half-written file."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def _signal_agent(step: str, url: str, ocr_found: list, screenshot_path: str,
                  kind: str = "text_not_found", **context):
    """
    Write failure context to failure.json and block until agent writes fix.json.
    The agent diagnoses purely from ocr_results — screenshot_path is an audit trail only.
    """
    if not settings.agent:
        print(f"[AGENT_NEEDED] step='{step}' on {url} — agent handshake disabled, failing this step.")
        return {"action": "fail", "reason": "agent_disabled"}

    os.makedirs(HANDSHAKE_DIR, exist_ok=True)
    # Clean up any stale fix
    if os.path.exists(FIX_JSON):
        os.remove(FIX_JSON)

    payload = {
        "timestamp": datetime.now().isoformat(),
        "url": url,
        "step": step,
        "screenshot_path": screenshot_path,   # audit trail — agent does NOT read this
        "kind": kind,                         # text_not_found | goal_not_met
        "ocr_results": ocr_found,             # full list of every visible string — THIS is what the agent reads
        "message": f"AGENT_NEEDED: step='{step}' failed. OCR found: {ocr_found}"
    }
    payload.update({k: v for k, v in context.items() if v})
    if _current_target:
        payload["target"] = _current_target
    try:  # where the browser really is; a flow can wander off its target without noticing
        page_url = browser._page.url if browser._page is not None else None
    except Exception:
        page_url = None
    if page_url and page_url != url:
        payload["page_url"] = page_url
    if settings.controls and "controls" not in payload and browser._page is not None:
        # What can be clicked, by accessible name: icon-only buttons OCR can't read show up here
        found = actions.controls(visible_text=ocr_found)
        if found:
            payload["controls"] = found
    rejected = _rejected_for_agent()
    if rejected:
        payload["rejected_fixes"] = rejected  # earlier answers that were tried and did not work
    _write_json_atomic(FAILURE_JSON, payload)

    print(f"\n{'='*60}")
    print(f"[AGENT_NEEDED] step='{step}' on {url}")
    print(f"  Screenshot: {screenshot_path}")
    print(f"  OCR found: {ocr_found}")
    print(f"  Waiting for fix at: {FIX_JSON}")
    print(f"{'='*60}\n")

    # Poll for fix
    deadline = time.monotonic() + settings.agent_timeout
    while time.monotonic() < deadline:
        if os.path.exists(FIX_JSON):
            try:
                with open(FIX_JSON) as f:
                    fix = json.load(f)
                os.remove(FIX_JSON)
                # Handled: remove the request so supervisors don't answer it twice
                if os.path.exists(FAILURE_JSON):
                    os.remove(FAILURE_JSON)
                print(f"[AGENT_FIX] Received: {fix}")
                # Tree updates wait until the fix is proven (see _settle_fix / _end_target)
                _hold(fix)
                return fix
            except json.JSONDecodeError:
                # File is actively being written by agent, wait for next tick
                pass
        browser.wait(1000)

    print("[AGENT_NEEDED] Timed out waiting for fix. Skipping.")
    return {"action": "skip", "reason": "agent_timeout"}


def _hold(fix: dict):
    """Keep a fix's save_to_tree branches on probation until the step or target they were for succeeds."""
    for path_str, value in (fix.get("save_to_tree") or {}).items():
        branch = dict(value)
        reason = fix.get("reason") or fix.get("note")
        if reason:
            branch.setdefault("reason", reason)
        _probation.append((path_str.split("."), branch))
    if fix.get("save_to_tree"):
        print(f"[TREE] {len(fix['save_to_tree'])} branch(es) on probation until the fix is proven")


def _commit_probation(proof: str):
    """The fix worked: write its branches to tree.json (or, in review mode, to pending.json)."""
    if not _probation:
        return
    tree = strategy_tree.load()
    pending = strategy_tree.load_side(strategy_tree.PENDING) if settings.review else None
    for keys, branch in _probation:
        branch["proven_on"] = proof
        branch["learned_at"] = datetime.now().isoformat(timespec="seconds")
        if pending is None:
            strategy_tree.set_branch(tree, keys, branch)
        else:
            pending.append({"branch": ".".join(keys), "fix": branch})
    if pending is None:
        print(f"[TREE] Saved {len(_probation)} proven branch(es)")
    else:
        strategy_tree.save_side(strategy_tree.PENDING, pending)
        print(f"[TREE] {len(_probation)} proven branch(es) waiting for review: run `visor tree --review`")
    _probation.clear()


def _reject_probation(why: str):
    """The fix did not work: forget its branches, and tell the agent next time."""
    for keys, branch in _probation:
        entry = {"branch": ".".join(keys), "fix": branch, "why": why,
                 "at": datetime.now().isoformat(timespec="seconds")}
        _rejected.append(entry)
        strategy_tree.add_rejected(entry)  # kept for later runs too
        print(f"[TREE] Discarded unproven branch {'.'.join(keys)}: {why}")
    _probation.clear()


def _rejected_for_agent(limit: int = 5) -> list:
    """This run's rejected fixes, plus earlier runs' ones for this flow (or _global): newest last."""
    flows = {settings.flow, GLOBAL_KEY}
    earlier = [e for e in strategy_tree.load_side(strategy_tree.REJECTED)
               if e not in _rejected and e.get("branch", "").split(".")[0] in flows]
    return (earlier + _rejected)[-limit:]


def _settle_fix(status: str, url: str) -> str:
    """After a healed step: outside a run the step's own result is the proof; inside a run, the target's."""
    if status in ("failed",):
        _reject_probation(f"the step still failed on {url}")
    elif not _in_target:
        _end_probation(status, url)
    return status


def _end_probation(status: str, url: str):
    """Only a success proves a fix. A skip proves nothing, so a skip rule is never saved by itself."""
    if status in DONE_STATUSES:
        _commit_probation(url)
    elif status.startswith("skipped"):
        for keys, _ in _probation:
            print(f"[TREE] Not saving {'.'.join(keys)}: a skip can't be proven. Add it to tree.json by hand if it's a rule.")
        _probation.clear()
    elif status != "restart_flow":
        _reject_probation(f"the target ended as {status!r}")


def _goal_labels(goal) -> list:
    return list(goal) if isinstance(goal, (list, tuple)) else [goal]


def goal_met(goal, timeout: float = None) -> bool:
    """The goal text is on screen, and still there a moment later: a flash or a glitch doesn't count."""
    try:
        actions.wait_for(_goal_labels(goal), timeout=timeout, proof=True)
    except VisorError:
        return False
    browser.wait(800)
    return actions.see(_goal_labels(goal), proof=True)


def _goal_not_met(goal, url: str, error: str = None) -> str:
    """The flow ended without its goal on screen: ask the agent why, as for a missing button."""
    labels = _goal_labels(goal)
    print(f"[GOAL] Not met: none of {labels} is on screen" + (f" (the flow reported: {error})" if error else ""))
    if not settings.agent:
        return "failed"
    try:
        visible = actions.read()
    except Exception:
        visible = []
    fix = _signal_agent(f"goal:{' / '.join(labels)}", browser.get_page().url, visible,
                        _save_screenshot("goal_not_met"), kind="goal_not_met", goal=labels, error=error)
    action = fix.get("action")
    if action == "skip":
        return f"skipped:{fix.get('reason', 'agent')}"
    if action == "restart_flow":
        return "restart_flow"
    if action == "retry":
        return "retry_target"
    if action == "ocr_click":
        match = actions.locate_target(fix["target"])
        if match:
            actions.press(match)
            clicker.short_wait()
    if action in ("ocr_click", "agent_fixed"):
        return "success" if goal_met(goal) else "failed"
    return "failed"


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

    # Word-level match, preferring real enabled controls; bounds (DOM bounding box) constrain the search
    match = actions.locate(label, exact=True, region=bounds, img_path=img_path)

    if match:
        print(f"[OCR] Found '{label}' at ({match['x']}, {match['y']}) conf={match['confidence']}")
        actions.press(match)
        return "success"

    # Not found — check strategy tree
    print(f"[OCR] '{label}' not found. Visible text: {all_text}")
    return _recover(label, url, flow_key, retry, bounds, state, img_path, all_text)


def recover(label: str, url: str = None, flow_key: str = None, bounds: dict = None, state: str = None) -> str:
    """
    A label could not be found: apply a known strategy-tree branch, else ask the agent.
    Used by visor.click() while run_flow is running a flow.
    """
    img_path = browser.screenshot()
    all_text = ocr.summarize(img_path)
    return _recover(label, url or browser.get_page().url, flow_key or settings.flow or "default",
                    True, bounds, state, img_path, all_text)


def _recover(label, url, flow_key, retry, bounds, state, img_path, all_text) -> str:
    tree = strategy_tree.load()

    # Try contextual state match first, then fallback to stateless match
    not_found_branches = {}
    if state:
        not_found_branches = strategy_tree.get(tree, flow_key, state, f"find_{label.replace(' ', '_')}", "not_found") or {}
    if not not_found_branches:
        not_found_branches = strategy_tree.get(tree, flow_key, f"find_{label.replace(' ', '_')}", "not_found") or {}
    if not not_found_branches:
        # Lessons about how the web works, shared by every flow
        not_found_branches = strategy_tree.get(tree, GLOBAL_KEY, f"find_{label.replace(' ', '_')}", "not_found") or {}

    # Specific conditions first; a "default" branch applies when none of them match
    for condition, branch in sorted(not_found_branches.items(), key=lambda kv: kv[0] == "default"):
        # Check if the condition element is visible in OCR
        condition_label = condition.replace("_visible", "").replace("_", " ")
        if any(condition_label.lower() in t.lower() for t in all_text) or condition == "default":
            print(f"[TREE] Matched condition '{condition}' → action: {branch['action']}")
            if branch["action"] == "skip":
                return f"skipped:{branch.get('reason', 'unknown')}"
            elif branch["action"] == "click_ocr":
                target = branch["target"]
                if not retry:
                    # We are re-checking after this fallback already ran: clicking it again would
                    # only toggle the menu shut. The label is still missing, so the step failed.
                    print(f"[TREE] '{label}' still not found after the fallback '{target}'")
                    return "failed"

                # Maintain bounds mapping even in fallback if applicable
                target_match = actions.locate_target(target, exact=bool(bounds), region=bounds, img_path=img_path)

                if target_match:
                    actions.press(target_match)
                    wait_after = branch.get("wait_after", 2.5)
                    print(f"[TREE] Waiting {wait_after}s for dropdown/animation...")
                    browser.wait(int(wait_after * 1000))

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
                                actions.press(connect_match)
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
    return _settle_fix(_apply_fix(fix, label, url, flow_key, bounds, state), url)


def _apply_fix(fix, label, url, flow_key, bounds, state) -> str:
    if fix.get("action") == "skip":
        return f"skipped:{fix.get('reason', 'agent')}"
    elif fix.get("action") == "ocr_click":
        target_match = actions.locate_target(fix["target"])
        if target_match:
            actions.press(target_match)
            clicker.short_wait()
            if fix.get("then") == "retry":
                return ocr_find_and_click(label, url, flow_key, retry=False, bounds=bounds, state=state)
            return "agent_fixed"
    elif fix.get("action") == "retry":
        # The agent may have just edited tree.json: apply its branch, then look for the label again
        return ocr_find_and_click(label, url, flow_key, retry=True, bounds=bounds, state=state)
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


def _reload_module(mod):
    """
    Hot-reload a flow module. Flows loaded by file path are not on sys.path,
    so importlib.reload can't find them; re-execute those from their source file.
    """
    # Read before reloading: a failed importlib.reload clears __spec__
    spec = getattr(mod, "__spec__", None)
    origin = getattr(spec, "origin", None)
    try:
        return importlib.reload(mod)
    except ImportError:
        if not origin or not os.path.isfile(origin):
            raise
        spec = importlib.util.spec_from_file_location(mod.__name__, origin)
        mod.__spec__ = spec
        spec.loader.exec_module(mod)
        return mod


def _normalize_status(status) -> str:
    """Flows may return a status string, True/False, or nothing (finished without raising = success)."""
    if status is None or status is True:
        return "success"
    if status is False:
        return "failed"
    return str(status).strip() or "success"


def _is_done(status: str) -> bool:
    return status in DONE_STATUSES or status.startswith("skipped")


def _run_one(flow_fn, url: str, goal=None) -> str:
    error = None
    try:
        status = _normalize_status(flow_fn(url))
    except Skip as e:
        # "Already pending" with Pending on screen means the job is done: count it, don't hide it
        if goal and browser._page is not None and goal_met(goal, timeout=1):
            print(f"[GOAL] Met; the flow wanted to skip ({e.reason}), so this counts as a success")
            return "success"
        return f"skipped:{e.reason}"
    except RestartFlow:
        return "restart_flow"
    except VisorError as e:
        print(f"[ERROR] {e}")
        status, error = "failed", str(e)
    except Exception as e:
        print(f"[ERROR] Target crashed unexpectedly: {type(e).__name__}: {e}")
        status, error = "failed", f"{type(e).__name__}: {e}"

    # The goal decides, not the script: check the outcome on screen
    if goal and status in DONE_STATUSES + ("failed",):
        if browser._page is None:
            print("[GOAL] Can't check the goal: the flow never opened a page")
            return "failed"
        if goal_met(goal):
            if status == "failed":
                print("[GOAL] Met, although the flow reported a failure")
            return "success"
        status = _goal_not_met(goal, url, error)

    if status == "failed" and browser._page is not None:  # never launch a browser just to photograph a failure
        try:
            print(f"[ERROR] Screenshot of the failure: {_save_screenshot('crash')}")
        except Exception:
            pass
    return status


def _run_target(flow_fn, url: str, goal=None) -> str:
    """One target, with its agent fixes settled: proven fixes are saved, failed ones dropped."""
    global _in_target, _current_target
    _in_target, _current_target = True, url
    if callable(goal):  # the user's goal for this target, e.g. lambda t: f"Booked for {t}"
        goal = goal(url)
    try:
        status = _run_one(flow_fn, url, goal)
        for _ in range(2):  # the agent asked to run the target again from the start
            if status != "retry_target":
                break
            print("[RUNNER] Running the target again, as the agent asked")
            status = _run_one(flow_fn, url, goal)
        if status == "retry_target":
            status = "failed"
    finally:
        _in_target, _current_target = False, None
    _end_probation(status, url)
    return status


def _pace(status: str):
    """Pause between targets: human-like after a success, short otherwise."""
    low, high = settings.pace
    if high <= 0:
        return
    if status == "success":
        delay = random.uniform(low, high)
        print(f"[WAIT] {delay:.1f}s")
        browser.wait(int(delay * 1000))
    else:
        browser.wait(int(random.uniform(min(1.5, low), min(3.5, high)) * 1000))


def run_flow(flow_fn, targets: list, results_csv: str, max_retries: int = 1, flow_key: str = None,
             goal=None):
    """
    Main loop:
      - Run flow on all targets
      - Track success rate
      - Re-run failures up to max_retries until 100% or exhausted
    flow_fn(target) returns 'success' / 'failed' / 'skipped:<why>' / True / False / None,
    or raises visor.Skip / visor.RestartFlow / any exception (= failed).
    goal: text (or list of texts) that must be on screen when a target is done. Defaults to
    the flow module's GOAL, if it has one.
    """
    if goal is None:
        goal = getattr(sys.modules.get(getattr(flow_fn, "__module__", None) or ""), "GOAL", None)
    if goal:
        shown = "the flow's GOAL(target)" if callable(goal) else repr(goal)
        print(f"[GOAL] A target counts as done only when {shown} is on screen")
    targets = list(dict.fromkeys(t.strip() for t in targets if t and t.strip()))
    results = {t: "pending" for t in targets}

    # Load existing results if resuming
    if os.path.exists(results_csv):
        with open(results_csv) as f:
            for row in csv.DictReader(f):
                key = (row.get("target") or row.get("url") or "").strip()
                status = (row.get("status") or "").strip()
                if key and _is_done(status):
                    results[key] = status

    # While a flow runs, high-level actions escalate to the strategy tree / agent
    previous = (settings.heal, settings.flow)
    settings.heal = True
    settings.flow = flow_key or settings.flow or getattr(flow_fn, "__module__", "") or "default"

    try:
        for attempt in range(1, max_retries + 1):
            pending = [url for url in targets if not _is_done(results[url])]
            if not pending:
                break

            print(f"\n{'='*60}")
            print(f"[RUN] Attempt {attempt}/{max_retries} — {len(pending)} targets")
            print(f"{'='*60}")

            for n, url in enumerate(pending, 1):
                print(f"\n[TARGET] ({n}/{len(pending)}) {url}")
                status = _run_target(flow_fn, url, goal)
                restarts = 0
                while status == "restart_flow" and restarts < MAX_RESTARTS:
                    restarts += 1
                    print("[RUNNER] restart_flow requested! Hot-reloading active Python module...")
                    mod = getattr(sys.modules[__name__], "_active_module", None)
                    if mod:
                        try:
                            mod = _reload_module(mod)
                        except Exception as e:
                            print(f"[ERROR] Hot-reload failed, keeping previous flow: {e}")
                            status = "failed"
                            break
                        sys.modules[__name__]._active_module = mod
                        if hasattr(flow_fn, "__name__") and hasattr(mod, flow_fn.__name__):
                            flow_fn = getattr(mod, flow_fn.__name__)
                        print("[RUNNER] Module reloaded successfully.")
                    print(f"[RUNNER] Running the target again from step 1 (restart {restarts}/{MAX_RESTARTS})")
                    status = _run_target(flow_fn, url, goal)
                if status == "restart_flow":
                    print(f"[RUNNER] Still asking to restart after {MAX_RESTARTS} restarts; marking it failed")
                    status = "failed"

                results[url] = status
                print(f"[RESULT] {url} → {status}")

                # Write running results to CSV
                _write_csv(results, results_csv)

                if n < len(pending):
                    _pace(status)

            # Report (current targets only; older rows in the CSV are kept but not counted)
            current = [results[t] for t in targets]
            success = sum(1 for s in current if s in DONE_STATUSES)
            skipped = sum(1 for s in current if s.startswith("skipped"))
            failed  = sum(1 for s in current if not _is_done(s))
            actionable = len(current) - skipped
            rate = (success / actionable * 100) if actionable > 0 else 100

            print(f"\n[REPORT] Attempt {attempt}: {success}/{actionable} actionable succeeded ({rate:.0f}%)")
            print(f"         Skipped: {skipped} | Failed: {failed}")

            if failed == 0:
                print("[DONE] 100% success rate achieved!")
                break
    except KeyboardInterrupt:
        print("\n[RUN] Interrupted — progress saved; run again to resume.")
        _write_csv(results, results_csv)
        raise
    finally:
        settings.heal, settings.flow = previous

    _write_csv(results, results_csv)
    return results


def _write_csv(results: dict, path: str):
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["target", "url", "status", "timestamp"])
        writer.writeheader()
        for target, status in results.items():
            writer.writerow({"target": target, "url": target, "status": status, "timestamp": datetime.now().isoformat()})
    os.replace(tmp, path)
