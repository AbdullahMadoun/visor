# Visor 👁️

**Browser automation that reads the screen.** You tell Visor what to click by the text a person would see — "Sign in", "Add to cart", "Next" — and it finds that text with on-device OCR and clicks it with native browser mouse events. No CSS selectors to break when a site changes its markup.

When something unexpected happens inside a long run, Visor pauses, hands the screen's text to an AI agent, and saves the agent's fix to a strategy tree (`tree.json`), so the same problem is handled automatically next time.

```python
import visor

visor.goto("https://news.ycombinator.com")
visor.click("login")
visor.fill("username", "me")
visor.fill("password", "secret", enter=True)
visor.wait_for("logout")
```

---

## Install

```bash
git clone https://github.com/AbdullahMadoun/visor.git
cd visor
pip install -e .
playwright install chromium
visor doctor          # checks the browser, OCR and workspace
```

On macOS Visor uses Apple's on-device OCR (`ocrmac`): fast, word-accurate, and it reads Arabic and other scripts out of the box. On Linux and Windows it uses EasyOCR.

---

## Everyday use

### Clicking

```python
visor.click("Checkout")                          # the button, not the word "checkout" in a paragraph
visor.click("Add to cart", near="Blue mug")      # the one next to "Blue mug"
visor.click("Add to cart", index=1)              # the second one, in reading order
visor.click(["Accept all", "Accept", "OK"])      # whichever is on screen, in that order of preference
visor.click("Submit", expect="Thank you")        # verify the result; retried once if nothing happened
visor.double_click("Photo.jpg")
visor.hover("Products")                          # open hover menus
```

What `click` does for you, in order, until one works:

1. **Looks**, and keeps looking while the page is still loading (up to `timeout`, 8 s by default). On a page that has stopped changing it moves on after ~1.5 s instead of waiting out the timeout.
2. **Picks the real button.** OCR finds the text; Visor then asks the browser what sits under that pixel. Real controls beat plain text, enabled beats disabled. A button that is visible but disabled is waited on until it enables.
3. **Hands over walls.** If a captcha or two-factor prompt is on screen, it triggers a **HUMAN_HANDSHAKE**: it pauses, you solve it in the window, and it carries on by itself once the prompt is gone.
4. **Clears the way.** If a cookie banner or modal covers the target, it presses Escape or closes the overlay ("Reject all" is preferred over "Accept all").
5. **Scrolls** down (and then up) to find text that is off screen, and stops at the end of the page.
6. **Icon-only buttons** with no visible text (⚙, ×, 🛒) are found by their accessible name (`aria-label`, `title`, `alt`).
7. **Verifies the click.** It watches for a page change, a request, navigation, a new tab or a focus change. If absolutely nothing happens, it looks again and clicks once more. If the click opens a new tab, Visor switches to it, and returns to the original tab when that tab closes.

### Forms

```python
visor.fill("Email", "me@example.com")            # by visible label or placeholder
visor.fill("Search", "running shoes", enter=True)
visor.fill("Country", "Jordan")                  # native <select> boxes too
visor.check("Remember me")                       # reads the state first: never flips it back
visor.check("Newsletter", on=False)
visor.select("Choose a color", "Green")          # custom (non-native) dropdowns
visor.upload("Upload resume", "cv.pdf")
path = visor.download("Export CSV")              # saved under visor_workspace/downloads/
visor.type_text("free text into whatever has focus")
visor.press_key("Escape")
```

### Looking and waiting

```python
visor.see("Out of stock")            # True / False right now
visor.wait_for("Order confirmed")    # wait until it appears (raises TextNotFound)
visor.wait_gone("Loading…")          # wait until it disappears
visor.scroll_to("Reviews")
visor.read()                         # the visible text, line by line
visor.find("Price")                  # where it is: {"text", "x", "y", ...} or None
```

### Pages, tabs, sessions

```python
visor.goto("example.com")            # https:// added for you; waits until the page settles
visor.back(); visor.reload()
visor.tabs(); visor.switch_tab("Help"); visor.new_tab(url); visor.close_tab()
visor.screenshot("page.png")
visor.page()                         # the Playwright page, for anything Visor doesn't cover
visor.close()                        # saves the session (cookies + storage) when Visor owns the browser
```

**Staying logged in:** run `visor login https://site.com`, log in by hand, press Enter. Later runs start logged in. Delete `visor_workspace/session.json` to log out.

**Using your own Chrome:** start Chrome with `--remote-debugging-port=9222` and Visor attaches to it in its own tab. It never closes your tabs or your browser.

### Errors

| Exception | Meaning |
|---|---|
| `visor.TextNotFound` | The text never showed up. `.visible` lists what *was* on screen. |
| `visor.ElementDisabled` | Found, but the button stayed disabled. |
| `visor.NavigationError` | A page failed to load. |
| `visor.Skip("reason")` | Raise it in a flow to skip the current target. |
| `visor.RestartFlow` | Raise it in a flow to hot-reload your code and retry. |

---

## Running a flow over many targets

A flow is a Python file with a `main(target)` function:

```python
# apply.py
import visor

def main(url):
    visor.goto(url)
    if visor.see("No longer accepting applications"):
        raise visor.Skip("closed")
    visor.click("Apply")
    visor.fill("Email", "me@example.com")
    visor.click("Submit", expect="Application sent")
    # returning nothing means success; return "failed" or raise to mark a failure
```

```bash
visor run --flow apply.py --targets jobs.csv            # CSV with a 'url' (or 'target') column, or a .txt file
visor run --flow apply.py --url https://example.com/job/1
visor run --flow apply.py --targets jobs.csv --retries 3 --headless --pace 2-5
```

Results go to `visor_workspace/logs/results.csv` after every target, so you can stop with Ctrl+C at any time and run the same command again to resume. Finished and skipped targets are not repeated. Failed targets are retried up to `--retries` times.

### Self-healing

While a flow runs, a `visor.click` that cannot find its target doesn't just fail:

1. **Strategy tree.** Visor checks `tree.json` for a known fix for this flow and step, such as "if *More* is visible, click it, then look again". Known fixes run instantly, with no AI involved.
2. **Agent handshake.** If the tree has no answer, Visor writes `agent_handshake/failure.json` (the step, URL and all visible text) and waits for an agent (Claude, Gemini, or you) to write `fix.json`. A fix can include `save_to_tree`, which turns it into a permanent tree branch.

3. **Human handshake.** Captchas and 2FA prompts go to you, not the agent (see above). Call `visor.human_handshake("log in please", until="Dashboard")` yourself for anything else only a person should do. It resumes when the text appears, or when you create `agent_handshake/human_done`.

Run with `--no-agent` to fail such steps immediately instead of waiting. `visor tree` shows what has been learned. The `fix.json` actions (`ocr_click`, `retry`, `skip`, `agent_fixed`, `restart_flow`) are documented in [SKILL.md](SKILL.md).

---

## Configuration

Set environment variables before starting, or call `visor.configure(...)` at runtime:

| Setting | Env var | Default | |
|---|---|---|---|
| `headless` | `VISOR_HEADLESS` | `False` | run without a window |
| `timeout` | `VISOR_TIMEOUT` | `8` | seconds actions keep looking |
| `attach` | `VISOR_ATTACH` | `True` | reuse a Chrome running with a debug port |
| `cdp_url` | `VISOR_CDP_URL` | `http://localhost:9222` | where to find it |
| `ocr_engine` | `VISOR_OCR_ENGINE` | `auto` | `livetext`, `vision` or `easyocr` |
| `ocr_langs` | `VISOR_OCR_LANGS` | | e.g. `en,ar` |
| `agent` | `VISOR_AGENT` | `True` | wait for `fix.json` on unknown failures |
| `agent_timeout` | `VISOR_AGENT_TIMEOUT` | `600` | seconds |
| `human` | `VISOR_HUMAN` | `True` | pause for you on captchas / 2FA |
| `human_timeout` | `VISOR_HUMAN_TIMEOUT` | `900` | seconds |
| `pace` | `VISOR_PACE` | `4-9` | seconds between targets (`0` = none) |
| `save_session` | `VISOR_SAVE_SESSION` | `True` | save cookies when Visor closes its browser |
| workspace | `VISOR_WORKSPACE` | `./visor_workspace` | sessions, logs, screenshots, learned tree |

Also: `scroll_search`, `dom_fallback`, `auto_dismiss`, `verify_clicks`, `follow_tabs` (all `True`).

---

## Debugging

```bash
visor ocr --url https://example.com --find "Sign in"   # every phrase Visor sees, with click coordinates
visor ocr screenshot.png
visor doctor
```

Screenshots of failures are saved in `visor_workspace/logs/failures/`. Every action prints what it did, for example `[CLICK] 'Checkout' -> changed the page`.

The lower-level modules (`visor.core.ocr`, `browser`, `clicker`, `runner`) are still available for custom logic. For example, `ocr.find_all(image)` returns every phrase with its position and word boxes.

---

## Directory structure

- `src/visor/`: the library. `core/actions.py` (finding and clicking), `core/ocr.py` (perception), `core/browser.py` (tabs, sessions), `core/runner.py` (flows and self-healing), `strategy/` (the tree).
- `visor_workspace/` *(ignored by git)*: your runtime data: `session.json`, `tree.json`, `agent_handshake/`, `logs/`, `downloads/`, `videos/`.
- `tests/`: `pytest` runs the suite. Browser tests use local pages in `tests/pages/` and need no internet.

## License
MIT
