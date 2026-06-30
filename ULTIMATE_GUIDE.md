# Visor: The Ultimate Architecture Guide

This guide documents the final, bulletproof architecture of **visor**, a self-healing browser automation framework that bypasses advanced anti-bot protections (like LinkedIn's) while operating 100% in the background.

## 1. The Core Philosophy
Traditional browser automation fails for two reasons:
1. **DOM Obfuscation:** Modern SPAs (like LinkedIn, React/Next.js apps) use dynamic class names, deeply nested shadow DOMs, and synthetic event traps to detect headless bots.
2. **Brittle Selectors:** When the DOM changes, XPath and CSS selectors break, requiring constant human maintenance.

Visor abandons the DOM entirely for perception and abandons synthetic DOM events for actions. Instead, it relies on **Visual Perception (OCR)** and **Native Blink Engine Events (Playwright CDP)**.

## 2. Architecture Layers

### Layer 1: Browser & Session Management (`core/browser.py`)
- **Engine:** Playwright Chromium connected to a persistent Chromium instance via CDP debug port (localhost:9222).
- **Visibility (`headless=False`):** We run the browser headfully. Headless browsers are easily detected by modern anti-bot scripts (they lack standard hardware concurrency, audio contexts, and WebGL footprints). Running `headless=False` ensures the browser looks like a real user.
- **Headful CDP Session Reuse:** To prevent macOS from forcefully switching Spaces or stealing focus every time a script restarts, `init_browser` first tries to `connect_over_cdp("http://localhost:9222")`. If the browser is already open, Playwright seamlessly attaches to the existing background tab without triggering a macOS GUI focus steal!
- **No Physical Mouse Stealing:** Despite being visible on screen, the automation **does not steal your physical mouse**. It uses an internal "ghost mouse" provided by the Chrome DevTools Protocol (CDP). You can work on other apps while visor runs.

### Layer 2: Perception (`core/ocr.py`)
- **Engine:** EasyOCR.
- **The Screen Never Lies:** We take a screenshot of the viewport and pass it to OCR. We only click what a human can see.
- **Hybrid DOM + OCR Geometry Mapping:** We don't just globally search for "More" or "Connect". We use a fully general hybrid approach: first, we query the DOM for a stable structural container (like the main profile card `<section>`) to get its geometric bounding box. Then, we filter the OCR results to only interact with elements falling strictly inside that bounding box. This solves the "multiple buttons with the same name" problem natively without rigid hardcoded text anchors.
- **Lower Confidence for Sentences:** Single words ("More", "Connect") OCR with 90%+ confidence. Sentences ("Send without a note") get lower confidence. We keep the threshold at `0.6` to avoid silently ignoring long buttons.

### Layer 3: Action (`core/clicker.py`)
- **Engine:** Playwright CDP `page.mouse.click(x, y)`.
- **Why not OS-level clicks (cliclick)?** OS-level clicks suffer from macOS Retina display scaling (DPI warping) and require Accessibility permissions. CDP avoids all of this.
- **Why not `element.click()`?** Playwright's `element.click()` runs visibility and actionability checks that time out on elements hidden behind overlays or custom styled components. CDP mouse events skip these checks entirely.
- **The CDP Advantage:** `page.mouse.click()` dispatches mouse events directly into the Blink rendering engine's hit-testing pipeline. Because the browser viewport is strictly defined (e.g., `1440x900`), the X,Y coordinates from OCR map 1:1 to CDP click coordinates, completely bypassing OS-level Retina warping.

### Layer 4: Self-Healing Strategy Tree (`strategy/tree.py`)
- **The Problem:** UI state is complex. Sometimes "Connect" is hidden inside a "More" dropdown. Sometimes the user is already connected ("Message" only).
- **The Solution:** A JSON-based decision tree (`tree.json`).
- **Flow:** If OCR fails to find the primary target (e.g., "Connect"), it checks the screen against the Strategy Tree. If it sees "More", the tree dictates: *Click "More", wait 2.5s, then look for "Connect" nearby*.
- **Growth:** The tree grows forever. It encodes every single failure and human-provided fix into permanent knowledge.

### Layer 5: The Agent Handshake (`core/runner.py`)
- **If the script gets stuck:** It does not crash. It saves a screenshot, writes `failure.json`, and pauses, printing `AGENT_NEEDED`.
- **The Fix Loop:** An AI Agent (or human) looks at the screenshot, figures out what state the UI is in, writes a rule to `fix.json` (updating the Strategy Tree), and the script resumes instantly without dropping the session.

---

## 3. Best Practices for Modifying Visor

1. **Never write DOM code:** No `page.locator()`, no `page.get_by_text()`. If you need to find something, use `ocr.py`. If you need to click it, use `clicker.py`.
2. **Always test on a real screen state:** If a script fails, look at the screenshot in `logs/failures/`. Don't guess. The screen never lies.
3. **Respect timings:** Dropdowns and modals have CSS animations. Always add a `2.5s` to `3s` wait after clicking something that opens a modal.
4. **Assume you are wrong first:** If OCR didn't find the button, it's not because the OCR is broken—it's usually because the button wasn't there yet, or was off-screen, or had slightly different text. Look at the raw OCR output first.
5. **Strict State Verification:** A flow is only successful if it verifies the outcome. Just because you clicked "Send" doesn't mean it sent. Always take a post-action screenshot and verify the resulting UI (e.g., checking if the message text appeared in the chat history bubble).
6. **Explicit Form Focus:** Never assume an input box is automatically focused. Depending on the UI state (e.g., an empty chat vs. a chat with history), inputs may drop focus. Always explicitly OCR the input placeholder (e.g., "Write a message..."), click it (adding a `+10` Y-offset if needed to hit the center of the box), and *then* type.
7. **Resilient OCR Verification:** When verifying text that was typed (like a sent message), remember that OCR can misclassify characters (e.g., reading "AI" as "Al"). Use lowercase substring fragment matching across multiple words to avoid false-negative verification failures.
8. **Top-Level Goal Enforcement:** Do not silently exit loops when a script (like a scroll loop) reaches a dead end. If the overarching target/goal is not met (e.g., connected 1 out of 5), the script MUST explicitly trigger `AGENT_NEEDED`. This upgrades the framework from a brittle script to a goal-oriented agent loop.
9. **READ ALL OCR TEXT:** When investigating an `AGENT_NEEDED` pause, DO NOT guess the browser's state based on a hasty glance. You MUST read every single element in the `all_text` OCR array. For example, if a modal opened, the OCR array will explicitly contain "Add a note" or "Send without a note". Ignoring this leads to false skipping.
10. **The Pagination Trap:** Infinite scrolling is not always infinite. At the bottom of a loaded batch, there is often a "Show more results" button. If OCR stops finding target buttons, look for "Show more results" in the array and click it before giving up.
11. **Do Not Abruptly Close Playwright Contexts:** In `run.py`, do not place `browser.close()` in a `finally` block or retry wrappers. This causes the browser to forcefully quit and restore tabs repeatedly. Let the Python process hang at the end so the user can inspect the final visual state seamlessly.
12. **Autonomous Subagent Healer:** When running tasks, you (the AI Agent) can launch the `visor` loop in the background and iteratively read `AGENT_NEEDED` signals to write `fix.json` fixes yourself. The user only needs to be involved if you completely fail to resolve the state after 5 consecutive approaches.
13. **Playwright Target Closed Handling:** Background scripts must aggressively wrap interactions in try/except for "Target closed" or "Connection refused".
14. **Expired Jobs Mid-Application Detection:** Check for fatal termination states (e.g., "No longer accepting applications") before hunting for form elements to avoid infinite loops on dead targets.
15. **Obsidian-Verified Form Filling:** Do NOT use random heuristics or blind guesses for form fields. When encountering custom questions, query an Obsidian knowledge bank.
16. **Handling Overlay `<dialog>` Interceptions:** Add a pre-click hook to automatically locate and `close()` open `<dialog>` elements or click explicit "Discard" buttons to cleanly reset page state.
17. **Robust Success String Detection:** Include an array of known success variants (`["application was sent", "your application was sent", "application submitted"]`) to prevent false-negative stalls.
18. **DOM-First Interaction over OCR for Modals:** Inside highly structured flows (like Easy Apply), prioritize pure Playwright DOM locators for structural elements (`Next`, `Review`, `Submit`). Only use OCR for state detection.
19. **Bypassing Playwright Actionability Checks:** Use native Javascript execution to force interaction for visually hidden `<input type='radio'>` inputs instead of Playwright's default `click()`.
20. **Avoid Sidebar OCR Traps:** All OCR fallback clicks for modals must enforce coordinate bounds (e.g., `x < 1200`) to guarantee we only interact with the active viewport/modal, not the background UI.
21. **No One-Off Scripts:** Treat all automation requests as serious, full-on workflows. DO NOT write quick DOM-scraping scripts. You MUST follow the full architecture: create `platforms/<name>/<flow>.py`, register it in `run.py`, and rely purely on visual `core.ocr` and `core.clicker`.

## 4. Established Workflows (Queryable Log)
Detailed configurations, proven targets, specific DOM selectors, and execution commands for fully completed tasks (like the Easy Apply loop or the Job Miner) have been migrated to a dedicated, queryable log file to prevent cluttering this core architectural document.
If you need to run an established task or see how past agents solved specific extraction problems on LinkedIn, **READ THIS FILE:** `logs/WORKFLOWS.md`
