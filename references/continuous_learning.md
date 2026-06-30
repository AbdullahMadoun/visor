# Continuous Learning & Global Skill Adjustment

This document serves as a durable, compounding log of automated testing adjustments and robustness rules learned during execution. Whenever a visual workflow is improved, document the learnings here to update the global skillset.

## 1. Exception Safety & Graceful Failure

- **Target Closed Handling**: Wrap background page interactions in targeted `try/except` blocks to handle `Target page, context or browser has been closed` or `Connection refused` exceptions when pages detach or redirect. Return a structured fail/skip code instead of letting the entire process crash.
- **Pre-Check for Inactive States**: Before executing multi-step interactions, run a pre-check to detect if the target page is in a dead or inactive state (e.g., "no longer accepting requests", "out of stock", "closed"). If found, exit early with a skipped status.

## 2. Robust Form Filling & Selection

- **No Heuristic Guesses**: Never use random guesses or generic fallbacks (like selecting the first radio button or guessing numbers) for custom form questions. 
- **Knowledge Base Verification**: Query verified knowledge stores (e.g. personal wikis, Obsidian vaults) for ground-truth answers. If verified answers do not exist, pause and escalate to the user.
- **Bypass Actionability for Hidden Elements**: Visually styled dropdowns, checkboxes, and radio buttons often hide the underlying input elements. If Playwright's standard `.click()` times out waiting for actionability, bypass it using native Javascript evaluation:
  ```python
  page.locator("input[type='radio']").first.evaluate("el => el.click()")
  ```

## 3. Modal and Overlay Resiliency

- **Overlay Dialog Close Hooks**: Add hook checks to identify and close intercepting `<dialog>` overlays, cookie consent popups, and confirmation requests (e.g., clicking "Discard" or "Cancel" on background-saving prompts) that block main page interactions.
- **Strict Viewport/Modal Bounds**: When interacting with elements inside a modal or dialog, enforce coordinate boundaries on OCR results (e.g., `x < 1200` or `bounds=modal_box`) to prevent the click from hitting background elements, sidebars, or headers.

## 4. Execution & Verification Loop

- **Multi-Variant Success Matching**: Do not search for a single hardcoded success message. Define an array of potential success keywords (e.g., `["submitted", "completed", "done", "success"]`) to robustly catch confirmation screens.
- **Strict Visual Verification**: Never assume a click succeeded. Take a follow-up screenshot and use OCR or page properties to explicitly verify the interface transitioned to the expected next state.
- **Dynamic Feed Scanning**: For scrolling feeds or infinite lists, scroll progressively (e.g. using `page.mouse.wheel(0, 800)`) and run OCR checks at each interval. Do not assume the entire list fits in a single viewport.

## 5. Timing and Rendering

- **Asynchronous Dropdowns & Modals**: After clicking an element that opens a dropdown or modal, wait at least 2.5s before re-OCR-ing. The UI renders asynchronously and taking a screenshot immediately will miss the new elements.

## 6. The "Agent Healer" Mindset

- **Wrong First Diagnosis is Normal**: When you see a failure, your first hypothesis will often be wrong. Look at the actual screenshot before deciding. The screen never lies.
- **Code Changes Don't Apply to Running Tasks**: Always kill and relaunch after changing core Python code. Never try to magically fix a running script if the code itself is wrong.
- **READ ALL OCR TEXT (The Core Design Note)**: When investigating an `AGENT_NEEDED` pause, DO NOT guess the browser's state based on a hasty glance. You MUST read every single element in the `all_text` OCR array. If a modal opened, the OCR array will contain its text. Ignoring this leads to false skipping.
- **Top-Level Goal Enforcement**: Do not silently exit loops when a script (like a scroll loop) reaches a dead end. If the overarching target/goal is not met, the script MUST explicitly trigger `AGENT_NEEDED`. This upgrades the framework from a brittle script to a goal-oriented agent loop.

## 7. DOM & Interaction Edge Cases

- **Explicit Form Field Focus**: Do not assume text inputs (like chat boxes or textareas) are automatically focused upon opening. Focus may drop. Always explicitly find the input placeholder (via OCR or DOM), calculate an offset to hit the input area, click to focus, and *then* type.
- **Resilient OCR Matching for Verification**: When checking if an action succeeded (e.g. text appeared on screen), do not strictly match exact full strings. OCR can easily confuse characters (e.g., "AI" as "Al"). Match lowercase substring fragments to prevent false-negative verifications.
- **The Pagination Trap**: Many modern pages do not infinite scroll forever natively. At the bottom of a loaded batch, there is often a "Show more results" or "Next" button. If OCR stops finding targets while scrolling, look for pagination buttons in the array and click them before giving up.
- **Do Not Abruptly Close Playwright Contexts**: In orchestration scripts, do not place `browser.close()` in a `finally` block or retry wrappers. This causes the browser to forcefully quit. Let the Python process hang at the end (e.g., `while True: time.sleep(1)`) so the user can inspect the final visual state seamlessly.
