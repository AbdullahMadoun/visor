"""
LinkedIn Easy Apply Flow

Goal: Apply to a job using Easy Apply.
Success criteria: Application submitted ("Your application was sent" visible in OCR).

Strategy:
- Navigate to the job URL
- OCR-find the Easy Apply button with TOPMOST match (avoids Arabic suffix bbox extension)
- Verify modal opened after click; if not, dismiss Premium sidebar (Escape) and retry
- Handle multi-step forms with WHOLE-WORD matching (no 'next-generation' false positives)
- Any unknown state escalates to AGENT_NEEDED
"""

import sys
import os
import re
import time

from visor.core import browser, ocr, clicker, runner

FLOW_KEY = "linkedin_apply"


def _find_easy_apply(img_path: str):
    """
    Locate the Easy Apply button robustly.

    LinkedIn OCR variants: "Easy Apply", "Easy Apply لمنأ", "in Easy Apply"
    Key insight: the Arabic suffix 'لمنأ' extends the bounding box DOWNWARD,
    so we must pick the TOPMOST candidate (min y), not min(x,y).
    This ensures the click lands on the actual button, not below it.
    """
    all_items = ocr.find_all(img_path)
    candidates = []
    for item in all_items:
        text = item["text"].strip()
        if "easy apply" in text.lower() and item["confidence"] >= 0.25:
            # Use y1 (top of bounding box) not cy (center) to anchor click to button top
            candidates.append(item)
    if not candidates:
        return None
    # Pick topmost match — real Easy Apply button is always above the fold
    # and above any sidebar duplicates
    best = min(candidates, key=lambda c: c["y1"] if "y1" in c else c["y"])
    # Click at y1 + 15px (top of button + small offset) to avoid Arabic suffix zone
    best["y"] = (best.get("y1", best["y"]) + 15)
    return best


def _modal_is_open(all_text: list) -> bool:
    """Return True if the Easy Apply modal is open (form elements visible)."""
    modal_signals = ["submit application", "review", "contact info",
                     "phone number", "resume", "work experience",
                     "additional questions", "privacy policy"]
    text_joined = " ".join(all_text).lower()
    return any(sig in text_joined for sig in modal_signals)


def _whole_word(word: str, text: str) -> bool:
    """Case-insensitive whole-word match — prevents 'next-generation' matching 'next'."""
    return bool(re.search(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE))


def apply(job_url: str) -> str:
    """
    Returns: 'success' | 'skipped:<reason>' | 'failed'
    """
    browser.navigate(job_url)
    clicker.short_wait(3, 2)

    # ── Step 1: Find and click Easy Apply ──────────────────────────────────
    img_path = browser.screenshot()
    match = _find_easy_apply(img_path)

    if not match:
        # Before giving up: check if the tree knows what to do with visible elements
        all_text = ocr.summarize(img_path)
        print(f"[APPLY] 'Easy Apply' not found. Visible: {all_text}")

        # If we see "Apply" but no "Easy Apply" → external application redirect
        if any("apply" in t.lower() for t in all_text) and \
           not any("easy apply" in t.lower() for t in all_text):
            print("[APPLY] Only generic Apply visible — external job, skipping.")
            return "skipped:external_apply"

        # Otherwise truly unknown — escalate
        ss = browser.screenshot(save_path=os.path.join(runner.FAILURES_DIR, f"apply_no_btn_{int(time.time())}.png"))
        fix = runner._signal_agent("find_Easy_Apply", job_url, all_text, ss)
        if fix.get("action") == "skip":
            return f"skipped:{fix.get('reason', 'agent_skip')}"
        if fix.get("action") != "resume":
            return "failed"

    # ── DOM-first click (most reliable — bypasses OCR coordinate issues) ───
    page = browser.get_page()
    dom_clicked = False
    try:
        # LinkedIn's Easy Apply button has a consistent class on the job header
        easy_apply_btn = page.locator(
            "button.jobs-apply-button--top-card, "
            "button[aria-label*='Easy Apply'], "
            "button.jobs-apply-button"
        ).first
        if easy_apply_btn.count() > 0:
            easy_apply_btn.click(timeout=5000)
            dom_clicked = True
            print(f"[APPLY] DOM click on Easy Apply button succeeded")
    except Exception as e:
        print(f"[APPLY] DOM click failed ({e}), falling back to OCR coords")

    if not dom_clicked:
        # OCR fallback
        print(f"[APPLY] OCR fallback: clicking at ({match['x']}, {match['y']}) conf={match['confidence']:.2f}")
        clicker.click(match["x"], match["y"])

    clicker.short_wait(3, 1)

    # ── Verify modal opened; if not, close Premium sidebar and retry ────────
    ss_check = browser.screenshot()
    check_text = ocr.summarize(ss_check)
    if not _modal_is_open(check_text):
        print("[APPLY] Modal did not open or OCR missed signals. Retrying DOM click...")
        clicker.short_wait(1, 1)
        # Retry DOM click
        try:
            btn2 = page.locator(
                "button.jobs-apply-button--top-card, "
                "button[aria-label*='Easy Apply'], "
                "button.jobs-apply-button"
            ).first
            btn2.click(timeout=5000)
            clicker.short_wait(3, 1)
        except Exception:
            print("[APPLY] Retry DOM click also failed — skipping")
            return "skipped:button_not_clickable"

    # ── Step 2: Multi-step form loop (DOM-first) ──────────────────────────────
    max_steps = 15
    last_text_joined = ""
    for step_i in range(max_steps):
        ss = browser.screenshot()
        all_text = ocr.summarize(ss)
        text_joined = " ".join(all_text)

        print(f"[APPLY] Step {step_i}: page_text_snippet={text_joined[:200]}")

        # ✅ Success detection
        if any(phrase in text_joined.lower() for phrase in [
            "application was sent", "your application was sent", "application submitted"
        ]) or ("applied" in text_joined.lower() and "easy apply" not in text_joined.lower()):
            print("[APPLY] ✅ Application submitted successfully!")
            return "success"

        has_submit  = _whole_word("submit application", text_joined) or _whole_word("submit", text_joined)
        has_review  = _whole_word("review", text_joined)
        has_next    = _whole_word("next", text_joined) and "next-generation" not in text_joined.lower()
        has_discard = _whole_word("discard", text_joined)
        modal_open  = _modal_is_open(all_text)

        if step_i > 0 and text_joined == last_text_joined:
            print(f"[APPLY] Form stalled at step {step_i} (text unchanged) — escalating to agent")
            fix = runner._signal_agent(f"apply_step_{step_i}_stalled", job_url, all_text, ss)
            if fix and fix.get("action") == "skip":
                return f"skipped:{fix.get('reason', 'form_stalled')}"
            # Re-take screenshot and read text after agent fixes it
            ss = browser.screenshot()
            all_text = ocr.summarize(ss)
            text_joined = " ".join(all_text)
        
        last_text_joined = text_joined

        # ── Resume step: select top existing CV before clicking Next ──────────
        is_resume_step = ("select or upload a resume" in text_joined.lower()
                          or ("resume" in text_joined.lower() and "2mb" in text_joined.lower()))
        if is_resume_step:
            print("[APPLY] Resume step — selecting top uploaded CV")
            try:
                # Force click the first radio button (bypasses Playwright visibility/interception checks)
                page.locator("input[type='radio']").first.evaluate("el => el.click()")
                print("[APPLY] Selected top resume via DOM evaluate")
                clicker.short_wait(1, 0.5)
            except Exception as e:
                print(f"[APPLY] Resume DOM select failed ({e})")

        # If modal closed unexpectedly, done
        if not modal_open and step_i > 0:
            print(f"[APPLY] Modal closed at step {step_i} — escalating")
            fix = runner._signal_agent(f"apply_step_{step_i}", job_url, all_text, ss)
            if fix and fix.get("action") == "skip":
                return f"skipped:{fix.get('reason', 'modal_closed')}"
            return "failed"

        # ── DOM-first button clicks ──────────────────────────────────────────
        clicked = False

        try:
            submit_btn = page.locator(
                "button[aria-label*='Submit'], "
                "button.artdeco-button--primary:has-text('Submit'), "
                "footer button:has-text('Submit')"
            ).first
            
            review_btn = page.locator(
                "button.artdeco-button--primary:has-text('Review'), "
                "footer button:has-text('Review')"
            ).first
            
            next_btn = page.locator(
                "button.artdeco-button--primary:has-text('Next'), "
                "footer button:has-text('Next'), "
                "div[role='dialog'] button:has-text('Next')"
            ).first

            if submit_btn.is_visible():
                submit_btn.click(timeout=5000)
                print(f"[APPLY] DOM clicked Submit application")
                clicker.short_wait(3, 2)
                ss2 = browser.screenshot()
                final = " ".join(ocr.summarize(ss2)).lower()
                if any(p in final for p in ["application was sent", "your application was sent"]):
                    return "success"
                clicked = True

            elif review_btn.is_visible():
                review_btn.click(timeout=5000)
                print(f"[APPLY] DOM clicked Review")
                clicker.short_wait(2, 2)
                clicked = True

            elif next_btn.is_visible():
                next_btn.click(timeout=5000)
                print(f"[APPLY] DOM clicked Next")
                clicker.short_wait(2, 2)
                clicked = True
        except Exception as e:
            print(f"[APPLY] DOM button click error: {e}")

        if has_discard:
            print("[APPLY] Discard confirmation detected — clicking Cancel to return to application!")
            try:
                # We strictly only click buttons with the exact text "Cancel" or "Return"
                cancel_btn = page.locator("button:has-text('Cancel'), button:has-text('Return')").first
                if cancel_btn.is_visible(timeout=1000):
                    cancel_btn.click()
                    clicker.short_wait(1, 1)
            except Exception as e:
                print(f"[APPLY] Failed to click Cancel on Discard modal: {e}")

        if _whole_word("sign in", text_joined) or _whole_word("join now", text_joined):
            return "failed"

        if not clicked and not modal_open:
            # Unknown state — escalate to agent
            print(f"[APPLY] Unknown state at step {step_i}, escalating")
            fix = runner._signal_agent(f"apply_step_{step_i}", job_url, all_text, ss)
            if fix and fix.get("action") == "skip":
                return f"skipped:{fix.get('reason', 'unknown_state')}"
            return "failed"
        
        if not clicked and modal_open:
            print(f"[APPLY] Modal open but no buttons clicked. Step {step_i} stalled.")

    print("[APPLY] Max steps reached without submission")
    return "failed"


