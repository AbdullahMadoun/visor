# Autobot — Agent Rules

Whenever the user asks to automate a website through Autobot, treat it as a robust, production-grade workflow.
Do NOT write quick, one-off DOM-scraping scripts (e.g. `page.locator('a').all()`).

Instead, you MUST:
1. Follow the full Autobot architecture by creating a proper module in `platforms/<name>/<flow>.py`.
2. Use the `autobot` CLI entry point: `autobot --flow <platform>_<action> --targets <csv>`.
3. Use the `core.runner.run_flow` API for orchestration.
4. Rely on visual interaction natively (`core.ocr.find` + `core.clicker.click`) rather than DOM selectors for click targets.
5. Use DOM bounding boxes only as geometric anchors to scope OCR search via the `bounds` parameter.
6. When the runner encounters an unknown state (AUTONOMOUS HEALER protocol), read the failure screenshot, generate hypotheses, and mutate `strategy/tree.json` directly. Do not wait for human intervention.
7. Verify every action visually via post-action OCR state detection before proceeding.
