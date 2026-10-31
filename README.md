# Visor 👁️

**Browser automation that reads the screen.** You tell Visor what to click by the text a person would see — "Sign in", "Add to cart", "Next" — and it finds that text with on-device OCR and clicks it with native browser mouse events. No CSS selectors to break when a site changes its markup.

When something unexpected happens inside a long run, Visor pauses, hands the screen's text to an AI agent, and saves the agent's fix to a strategy tree (`tree.json`), so the same problem is handled automatically next time.

![A flow clicks RSVP on three event pages. Page 2 was redesigned, so the agent is called once and its fix is saved; page 3 uses the saved fix with no agent call.](examples/self_healing.gif)

*Three pages, one flow. Page 2 was redesigned: Visor asks the agent once and saves its answer. Page 3 has the same redesign and is solved from the saved fix, with no AI call. Run it yourself, offline: `python examples/self_healing_demo.py`.*

```python
import visor

visor.goto("https://news.ycombinator.com")
visor.click("login")
visor.fill("username", "me")
visor.fill("password", "secret", enter=True)
visor.wait_for("logout")
```

**Why it exists.** Agent browsers re-figure out the same task on every run, and pay for a screenshot at every step. Plain scripts are fast but break when a site renames a class. Visor sits in between: it runs ordinary code, sees the page through local OCR, and calls an AI only when something unexpected happens. The AI gets the visible text, not a screenshot, and what it decides is saved as a readable rule. The longer story is in [Why I built Visor](docs/why-i-built-visor.md).

---

## Install

```bash
git clone https://github.com/AbdullahMadoun/visor.git
cd visor
pip install -e .
playwright install chromium
visor doctor                          # checks the browser, OCR and workspace
python examples/self_healing_demo.py  # the demo above, on a local page, no API key
```

Visor isn't on PyPI yet: `pip install visor` installs an unrelated package with the same name.

On macOS Visor uses Apple's on-device OCR (`ocrmac`): fast, word-accurate, and it reads Arabic and other scripts out of the box. On Linux and Windows it uses EasyOCR (slower, and the least tested path: [help wanted](#help-wanted)).

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
# renew.py: renew every library loan in a list
import visor

def main(url):
    visor.goto(url)
    if visor.see("Not renewable"):
        raise visor.Skip("not renewable")
    visor.click("Renew")
    visor.click("Confirm", expect="Renewed until")
    # returning nothing means success; return "failed" or raise to mark a failure
```

```bash
visor run --flow renew.py --targets loans.csv           # CSV with a 'url' (or 'target') column, or a .txt file
visor run --flow renew.py --url https://library.example.com/loan/1
visor run --flow renew.py --targets loans.csv --retries 3 --headless --pace 2-5
```

Results go to `visor_workspace/logs/results.csv` after every target, so you can stop with Ctrl+C at any time and run the same command again to resume. Finished and skipped targets are not repeated. Failed targets are retried up to `--retries` times.

### Self-healing

While a flow runs, a `visor.click` that cannot find its target doesn't just fail:

1. **Strategy tree.** Visor checks `tree.json` for a known fix for this flow and step, such as "if *More* is visible, click it, then look again". Known fixes run instantly, with no AI involved.
2. **Agent handshake.** If the tree has no answer, Visor writes `agent_handshake/failure.json` (the step, URL and all visible text) and waits for an agent (Claude, Gemini, or you) to write `fix.json`. A fix can include `save_to_tree`, which turns it into a permanent tree branch.

3. **Human handshake.** Captchas and 2FA prompts go to you, not the agent (see above). Call `visor.human_handshake("log in please", until="Dashboard")` yourself for anything else only a person should do. It resumes when the text appears, or when you create `agent_handshake/human_done`.

Run with `--no-agent` to fail such steps immediately instead of waiting. `visor tree` shows what has been learned. The `fix.json` actions (`ocr_click`, `retry`, `skip`, `agent_fixed`, `restart_flow`) are documented in [SKILL.md](SKILL.md).

---

### Driving Visor from a coding agent

[SKILL.md](SKILL.md) teaches a coding agent (Claude Code, Gemini CLI, Codex and the like) to write Visor flows and to answer `AGENT_NEEDED` pauses itself. Drop it into your agent's skills or instructions. This is how the [benchmark](#a-small-benchmark) runs were driven.

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

## What it can't do (yet)

- **It needs text to aim at.** Icon-only buttons are found through their accessible name (`aria-label`, `title`, `alt`); an unlabeled icon, a canvas app or a game is out of reach.
- **The screen is the source of truth, not the only source.** OCR finds the text; the browser is then asked what sits under that pixel, so a real button beats the same word in a paragraph. "No DOM" here means no selectors in your code, not that the DOM is never read.
- **Same words in two places.** Two "Follow" buttons need `near=`, `index=` or a `region`. Visor picks the main control first, but it can't read your mind.
- **Chromium only**, through Playwright.
- **Linux and Windows use EasyOCR**, which is slower and less accurate than Apple's on-device OCR. Most of the testing so far is on macOS.
- **It does not get around bot protection.** Captchas and two-factor prompts are handed to you. Use it on sites and accounts you're allowed to automate.

## How it compares

| | Finds elements by | When a site changes | Remembers fixes as |
|---|---|---|---|
| Playwright / Selenium scripts | selectors you write | the script breaks | your next commit |
| Agent browsers (screenshot or DOM per step) | a model, every step | the model re-plans, every run | usually nothing |
| [Stagehand](https://docs.stagehand.dev) | a model over the DOM, cached | cached actions self-heal | cached selectors |
| [workflow-use](https://github.com/browser-use/workflow-use) | recorded steps | falls back to an agent | the workflow file (self-healing is on its roadmap) |
| RPA OCR clicks ([Ui.Vision](https://ui.vision), UiPath) | OCR on screen | the macro breaks | your next edit |
| **Visor** | local OCR, checked against the element under the pixel | strategy tree, then one agent call | a readable rule in `tree.json` |

The bet: for repeatable tasks, the expensive part (a model looking at the page) should happen once per *change*, not once per *step*. The agent can be anything that reads one JSON file and writes another, so Visor isn't tied to a model or an SDK.

## A small benchmark

So far, Visor has been run on part of the BU Bench V1 task set (Online-Mind2Web, GAIA, BrowseComp, WebBench read tasks and interaction tests). The agent was Gemini 3.8 Flash, which reached the web *only* through Python scripts it wrote with Visor: built-in browser, screenshot and web tools were blocked.

| Category | Passed |
|---|---|
| Interaction tests | 7 / 7 |
| GAIA | 7 / 7 |
| Online-Mind2Web | 7 / 8 |
| BrowseComp | 4 / 5 |
| WebBench (read) | 3 / 3 |
| **Total** | **28 / 30** |

Both failures timed out at the 20-minute limit. Median time per task: 7.8 minutes. **The model looked at 0 screenshots in all 30 runs**; everything it knew about the pages came from OCR text.

Read this as a smoke test, not a leaderboard entry: 30 of 100 tasks, graded by hand by me, one model, and no same-model baseline yet. The full run and a comparison against plain Playwright are in progress.

## Help wanted

Contributions are welcome, small ones included. Good places to start:

- **Linux and Windows.** Run `pytest` with EasyOCR and report what breaks; an option for a faster local OCR engine would be even better.
- **More test pages.** A small HTML page in `tests/pages/` that reproduces a real-world trap (sticky headers, virtual lists, shadow DOM, right-to-left layouts) and a test that clicks it.
- **Agent adapters.** A small script that answers `failure.json` using a model API or a local model, so the handshake works without a coding agent watching.
- **Docs.** If something in this README confused you, that's a bug. Open an issue.

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup; the full test suite runs offline in about a minute.

---

## Directory structure

- `src/visor/`: the library. `core/actions.py` (finding and clicking), `core/ocr.py` (perception), `core/browser.py` (tabs, sessions), `core/runner.py` (flows and self-healing), `strategy/` (the tree).
- `visor_workspace/` *(ignored by git)*: your runtime data: `session.json`, `tree.json`, `agent_handshake/`, `logs/`, `downloads/`, `videos/`.
- `tests/`: `pytest` runs the suite. Browser tests use local pages in `tests/pages/` and need no internet.

## License
MIT
