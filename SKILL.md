---
name: visor
description: >
  Build, run, debug, and extend the self-healing browser automation framework.
  This skill focuses on the core architecture: OCR perception, CDP click actions,
  strategy tree updates, and the live-debugging agent loop. It emphasizes
  strict verification and goal-driven autonomy.
---

# visor — Self-Healing Browser Automation

## Core Agent Mindset — THE MOST IMPORTANT RULE

> **Always assume YOU are wrong first when something doesn't work.**

## Agent Workflow Rules

1. **Hot-Reloading Strategy Tree**: The strategy tree (`tree.json`) is read from disk on every evaluation. If you encounter an `[AGENT_NEEDED]` pause, you can directly modify `tree.json` to teach the framework a new rule, and then pass `{"action": "retry"}` via `fix.json`. The engine will hot-reload your new rule and apply it immediately—no need to restart the daemon!
2. **Never Fire-And-Forget Daemons**: When launching long-running tests or scripts in the background, NEVER passively wait. Immediately check the background task logs using your tools (`manage_task` or reading the log file directly). If the daemon gets caught in an interactive handshake (like `[AGENT_NEEDED]`), you must spot it and intervene instantly instead of waiting for a timeout.

> **THE AUTONOMOUS /GOAL DIRECTIVE: PERFORM NO MATTER WHAT.** You must operate as an autonomous agent that treats every automation task like a relentless `/goal`. Be extra thorough, and NEVER stop until you are confident the objective is completely fulfilled. Constantly audit your own work. The task is *always* achievable if you try enough. **Always assume 100% the task is doable.** If an element isn't found, scroll. If a class name changes, use visual OCR. If a modal blocks you, hit Escape. You must embrace a relentless "break-fix" cycle until success.
>
> **VERIFICATION-DRIVEN EXECUTION.** You must NEVER blindly proceed to the next step. Every single action must be visually proven to have worked via OCR state detection before moving forward. If an action fails verification, you must loop back and fix it.
>
> **OCR-FIRST ALL THE WAY THROUGH.** You must rely primarily on visual perception (OCR) to look for textual clues (e.g., finding the specific word "Submit" or "Follow" on a page) to understand the screen state, locate elements, and execute clicks. Do not rely on brittle DOM parsers or CSS selectors unless absolutely necessary for bulk data extraction.

> **CRITICAL: No One-Off Scripts.** Whenever the user invokes `/visor` or asks to automate a website, treat it as a **serious, full-on workflow**. DO NOT write quick DOM-scraping scripts (e.g. `page.locator('a').all()`). You MUST follow the full architecture: create `platforms/<name>/<flow>.py`, register it in `run.py`, and rely purely on visual `core.ocr` and `core.clicker` with the `tree.json` strategy and `AGENT_NEEDED` handshake.
>
> **STRICT RULE: NO FAKE AUTOMATION & STRICT VERIFICATION.** You are highly prohibited from writing 'demo' scripts that fake workflows. EVERY click must be grounded in genuine visual/OCR state detection, and EVERY action MUST be explicitly verified before reporting success.

## Architecture & Browser Layer

Uses Playwright (`sync_playwright`) with a persistent background profile.
- **Headless**: Runs entirely in the background (no window, no stealing physical mouse).
- **Native Clicks (`clicker.py`)**: Uses Playwright CDP (`page.mouse.click(x, y)`) to inject mouse events directly into the Chromium Blink engine. These events bypass Playwright's actionability checks and go through Blink's full hit-testing pipeline.
- **Coordinates**: Perfectly 1:1 with OCR bounding boxes because CDP operates on internal viewport pixels, completely immune to macOS Display Scaling.

## OCR Robustness Rules — Geometric Anchor Strategy

**The core principle: Use KNOWN elements as spatial anchors, not static pixel cutoffs.**
Pages often have multiple instances of the same button label (e.g., in a sidebar vs. main card). NEVER filter by static coordinates (`y < 660`). Always use geometric relationships.

1. **Anchor match (`ocr.find`)**: Find the target on the same row/column as a known neighbor. This is the most reliable method.
2. **Radius match (`ocr.find_near`)**: Use this AFTER clicking a button to find what appeared (e.g., dropdowns, modals) within a radius of the last click.

## The AGENT_NEEDED Protocol

The script pauses and writes `agent_handshake/failure.json` when:
- An OCR step finds nothing AND no tree branch matches the visible state.

**When AGENT_NEEDED fires:**
1. **Do NOT just retry the same thing.**
2. **View the screenshot immediately** (`logs/failures/<filename>.png`). What does the page actually show?
3. **Read all OCR text**. What elements are actually present?
4. **Generate DIVERGENT Hypotheses (Never Tunnel-Vision)**: Do not get stuck endlessly retrying one failed path. You must explicitly brainstorm multiple, equally smart, laterally divergent paths. Look for "tricks" or alternative ways around the UI. (e.g., Is there a modal? Hit Escape. Is the button hidden? Try zooming out. Is the main flow blocked? Search for an alternative entry point in a dropdown. Can we force it via DOM evaluate?).
5. **Write fix.json** to mutate the strategy tree, or fix the code and relaunch.

## Handshake Protocol Schema (fix.json)

When writing `fix.json` to resolve an `AGENT_NEEDED` block, you must output a valid JSON object matching one of these schemas so the execution engine (`runner.py`) knows how to proceed:

### 1. `ocr_click` (Execute fallback & learn)
Tells the engine to click a fallback target right now. By including `save_to_tree`, the framework permanently learns this exact fallback pattern.
```json
{
  "action": "ocr_click",
  "target": "More",
  "then": "retry",
  "save_to_tree": {
    "my_custom_flow.find_Submit.not_found.More_visible": {
      "action": "click_ocr",
      "target": "More",
      "then": "retry_find_Submit",
      "wait_after": 2.5
    }
  }
}
```

### 2. `retry` (Re-run current step)
Triggers a fresh execution of the current OCR check, useful if you manually fixed the screen state (e.g., dismissing a blocking modal).
```json
{ "action": "retry" }
```

### 3. `skip` (Abort target)
Tells the engine to abandon this specific target and move to the next item in the CSV.
```json
{ 
  "action": "skip", 
  "reason": "Human-readable reason (e.g., profile is restricted)" 
}
```

### 4. `agent_fixed` (Proceed)
Tells the engine that the objective of the current step was met via manual agent intervention, and the script should proceed to the next step.
```json
{ "action": "agent_fixed" }
```

## Strategy Tree Structure

`strategy/tree.json` — grows over time, never shrinks:

```json
{
  "platform_flow": {
    "step_name": {
      "not_found": {
        "VisibleElement_visible": {
          "action": "skip | click_ocr",
          "target": "ElementToClick",
          "wait_after": 2.5,
          "then": "retry_step_name",
          "note": "Human-readable reason for the fix"
        }
      }
    }
  }
}
```

**Tree update rules:**
- Every diagnosed failure → new branch.
- Keys format: `<flow>.<step>.<not_found|other>.<VisibleElement_visible>`.
- Never delete branches — they encode hard-won knowledge.

## Execution Quality Bar

Before marking an automation run as successful, verify the following:
- **Strict Verification**: Did you visually confirm the target state was rendered after the final interaction?
- **No Coordinate Hardcoding**: Did you use geometric filters (anchors or relative bounds) to click buttons rather than static pixel coordinates?
- **Separation of Concerns**: Is all platform-specific code isolated inside `platforms/`, core mechanics in `core/`, and visual recovery paths in `strategy/tree.json`?
- **Portability**: Are all path resolutions relative to `PROJECT_ROOT`?

## Continuous Learning & Resiliency Patterns

These generalized architectural rules represent hard-won knowledge from thousands of automation runs. Apply them universally to every new flow:

### 1. Hybrid Execution (DOM + OCR)
While OCR is best for visual perception and state detection, relying purely on OCR to click structural navigation elements (like pagination or form submissions) can fail if they render below the fold or get cropped. 
**Pattern**: Prioritize pure DOM locators (`is_visible()`) for structural navigation. Use OCR purely for understanding the current visual state of the workflow.

### 2. Forcing Hidden Element Interaction
Modern web frameworks often visually hide semantic HTML elements (like underlying inputs) behind complex styled containers. Playwright's default interactions will timeout waiting for these elements to become "actionable".
**Pattern**: Bypass strict visibility checks by forcing the interaction via native JavaScript evaluation on the underlying semantic element (e.g., `locator.evaluate("el => el.click()")`).

### 3. Overlay Interception Handlers
Generic overlays (like confirmation dialogues, cookie banners, or tooltips) invisibly intercept clicks targeting the background, causing silent timeouts.
**Pattern**: Implement pre-action hooks to detect and explicitly dismiss obstructing overlays before interacting with background elements. Enforce `:visible` pseudo-selectors aggressively.

### 4. Subagent Resilience
Background polling loops or independent healer subagents must assume the main orchestrator might navigate away or close the context at any time.
**Pattern**: Wrap all background browser interactions in robust error handling that catches target or context closures (`Target closed`). Fail gracefully rather than crashing the entire process.

### 5. Geometric Bounding Constraints
Global text searches often yield false positives in unrelated UI sections (like sidebars or background layers).
**Pattern**: When operating within a specific container (like a modal or a distinct card), always restrict the OCR search space using geometric bounding boxes to guarantee interactions only occur within the active foreground component.

### 6. Fatal State Pre-checks
Dynamic applications can spontaneously terminate workflows (e.g., a target item becomes unavailable mid-process). Searching for next steps on a dead page creates infinite loops.
**Pattern**: Before initiating deep workflows, verify the base page hasn't transitioned to a known fatal end-state. Cleanly abort or skip if a fatal state is detected.

### 7. Authentic Iteration
Never fake execution by scanning only the top of the viewport or blindly assuming an action worked. 
**Pattern**: If exploring a list, write explicit loops that physically scroll and scan. If executing an action, always capture a subsequent state verification to confirm the UI successfully transitioned.

### 8. Fuzzy State Verification & UI Volatility
UI success strings are highly volatile and subject to minor rewording or A/B testing.
**Pattern**: Avoid strict exact-match validations for state confirmation. Use arrays of known variants or lowercase substring fragments to ensure robust state verification. Furthermore, whenever a previously passing verification step suddenly fails, assume the UI copy has fundamentally changed. Do not assume the task is broken; immediately trigger the self-healing protocol to learn and save the new visual state signature.

### 9. Deterministic Inputs (No Blind Guessing)
Filling custom workflows with random heuristics pollutes data and leads to unpredictable end states.
**Pattern**: Do NOT guess inputs. If a workflow encounters an unknown requirement, query an explicit ground-truth knowledge base for verified answers. If no proof exists, pause and escalate.

### 10. Component-First Induction (Building Blocks Before Pipelines)
Attempting to execute a massive, multi-step pipeline on an unfamiliar platform usually ends in compounded failures.
**Pattern**: When trying a workflow for the first time, break it down into small, single tasks executed one at a time. Perform a full OCR search of the frontend after each interaction to guarantee visual conversion. For example, before writing a script to scrape 50 Amazon products, first explicitly learn and verify how to interact with the search bar, then toggle a specific filter, and visually bound a single product card. Only orchestrate the full pipeline *after* these atomic components are reliably mapped via OCR.

### 11. Isolate DOM Locator Timeouts
Playwright's default behavior is to violently crash the process if a `locator` times out (e.g., waiting for a modal that never appeared).
**Pattern**: Never let DOM locators crash the orchestrator. Always wrap hybrid DOM+OCR locators (like `page.locator().bounding_box()`) in strict `try/except` blocks with short timeouts (e.g. `timeout=2000`). If they fail, fallback gracefully to `AGENT_NEEDED` or the `tree.json` strategy.

### 12. Context-Aware Fallbacks & Hot-Reloading
When a workflow gets stuck, modifying Python files and sending a `retry` handshake will fail if the script is running in-memory without hot-reloading.
**Pattern**: If a code change is made during an `AGENT_NEEDED` pause, the daemon must implement `importlib.reload()` to consume the new logic, or the agent must kill and restart the daemon instead of blindly sending a `retry` handshake. Furthermore, reactive fallbacks (like `tree.json`) must eventually incorporate temporal state awareness (e.g., "I just clicked Connect") to prevent hallucinated interactions on unrelated elements.
