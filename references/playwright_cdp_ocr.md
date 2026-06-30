# Playwright CDP + OCR: The Architecture

Autobot completely abandons DOM selectors for actions and standard OS clicks.

### 1. Browser Layer (CDP vs. OS clicks)
We launch Chromium with remote debugging port 9222.
Why not standard OS-level mouse events?
- macOS Retina display DPR (Device Pixel Ratio) coordinate scaling wraps and breaks clicks.
- Requires macOS Accessibility/Screen Recording permissions.
- Binds up the user's actual mouse.

CDP dispatches native mouse events directly into Chromium's Blink rendering pipeline, bypassing all Playwright actionability checks and OS coordinate warping. Clicks are absolute to the viewport.

### 2. Vision Layer (OCR vs. DOM)
DOM elements break on code changes, and dynamic selectors trigger bot-detection.
OCR localization resolves what a human actually sees, rendering the site rendering as the ultimate source of truth.
