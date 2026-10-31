"""
Record a flow by doing it once by hand, then turn it into a flow file that checks itself.

The person gives the goal: the text on screen that means the task is done. That is
the only success check written into the flow. Whether each step in between worked
is for the agent to judge; a page changes in too many ways after each action for a
fixed rule to say which change matters. So the recorder keeps what text appeared
and disappeared after each action, as evidence: in the trace, and as a short
comment next to each step. The new flow is replayed once, and the file says whether
that replay reached the goal.

Password and one-time-code fields are never recorded: the flow reads them from
environment variables instead.
"""
import datetime
import json
import os
import queue
import re
import time

from visor.core import browser, ocr, WORKSPACE_DIR

TRACE_DIR = os.path.join(WORKSPACE_DIR, "logs", "traces")
SETTLE = 1.0  # seconds to wait after an action before reading the result
NAV_AFTER_ACTION = 3.0  # a page load this soon after an action was caused by it

_JS = r"""
(() => {
  if (window.__visorRecorder) return;
  window.__visorRecorder = true;
  const send = (data) => { try { window.visorSendEvent(data); } catch (e) {} };
  const inOverlay = (el) => el && el.closest && el.closest('#visor-recorder-ui');
  const visible = (s) => (s || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  const secret = (el) => {
    const auto = (el.getAttribute('autocomplete') || '').toLowerCase();
    return el.type === 'password' || /password|one-time-code|cc-/.test(auto);
  };
  const fieldLabel = (el) => visible(
    (el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label') ||
    el.placeholder || el.title || el.name || '');
  const isTextField = (el) => el && (el.tagName === 'TEXTAREA' ||
    (el.tagName === 'INPUT' && !/^(checkbox|radio|button|submit|reset|file|image|range|color|hidden)$/.test(el.type)));
  const sent = new WeakMap();  // last value sent per field, so change + Enter don't record twice

  function sendFill(el) {
    if (!isTextField(el) || sent.get(el) === el.value) return;
    sent.set(el, el.value);
    send({type: 'fill', label: fieldLabel(el), secret: secret(el), value: secret(el) ? null : el.value});
  }

  document.addEventListener('click', (e) => {
    if (inOverlay(e.target)) return;
    const el = e.target.closest('button, a, [role], input, label, select, summary') || e.target;
    if (isTextField(el) || el.tagName === 'SELECT') return;  // focusing a field is not a step
    const r = el.getBoundingClientRect();
    send({type: 'click', x: e.clientX, y: e.clientY, rect: [r.left, r.top, r.right, r.bottom],
          text: visible(el.getAttribute('aria-label') || el.innerText || el.value || el.title || el.alt)});
  }, true);

  document.addEventListener('change', (e) => {
    const el = e.target;
    if (inOverlay(el)) return;
    if (el.tagName === 'SELECT') {
      const opt = el.options[el.selectedIndex];
      send({type: 'select', label: fieldLabel(el), option: visible(opt ? opt.text : el.value)});
    } else {
      sendFill(el);
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || inOverlay(e.target)) return;
    sendFill(e.target);
    send({type: 'enter'});
  }, true);

  let scrollTimer = null;
  window.addEventListener('scroll', () => {
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => send({type: 'scroll', y: Math.round(window.scrollY)}), 400);
  }, true);

  function make(tag, text, css) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    if (css) el.style.cssText = css;
    return el;
  }
  function overlay() {
    if (!document.body || document.getElementById('visor-recorder-ui')) return;
    const ui = make('div', '', 'position:fixed;bottom:16px;right:16px;z-index:2147483647;background:#0f172a;' +
      'color:#fff;font:13px system-ui,sans-serif;padding:10px 12px;border-radius:10px;display:flex;' +
      'gap:8px;align-items:center;box-shadow:0 8px 24px rgba(0,0,0,.4)');
    ui.id = 'visor-recorder-ui';
    const note = make('input', '', 'width:170px;padding:4px 6px;border-radius:6px;border:1px solid #334155;' +
      'background:#1e293b;color:#fff');
    note.placeholder = 'note for the next step';
    const undo = make('button', 'Undo', 'cursor:pointer');
    const stop = make('button', 'Stop', 'cursor:pointer');
    ui.append(make('span', '●', 'color:#ef4444'), make('span', 'Recording'), note, undo, stop);
    document.body.appendChild(ui);
    note.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && note.value.trim()) { send({type: 'note', text: note.value.trim()}); note.value = ''; }
    });
    undo.addEventListener('click', () => send({type: 'undo'}));
    stop.addEventListener('click', () => send({type: 'stop'}));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', overlay);
  else overlay();
  new MutationObserver(overlay).observe(document.documentElement, {childList: true, subtree: true});
})();
"""


class Recorder:
    """Watches one page and turns what the person does into steps with before/after text."""

    def __init__(self, page, flow_name: str, url: str = "", description: str = ""):
        self.page = page
        self.flow_name = flow_name
        self.url = url
        self.description = description
        self.events = []
        self.active = True
        self.note = None
        self.queue = queue.Queue()
        self.screen = []  # OCR items of the last settled screen
        self.pending = None  # event still waiting for its after-screen
        self.pending_at = 0.0
        self.shot = os.path.join(TRACE_DIR, f"{flow_name}_screen.png")

    # ── wiring ────────────────────────────────────────────────────────────
    def attach(self):
        os.makedirs(TRACE_DIR, exist_ok=True)
        self.page.expose_function("visorSendEvent", self._receive)
        self.page.add_init_script(_JS)
        self.page.on("framenavigated", self._navigated)
        try:
            self.page.evaluate(_JS)  # the page that is already open
        except Exception:
            pass

    def _receive(self, data):
        if isinstance(data, dict) and data.get("type"):
            data["t"] = time.time()
            self.queue.put(data)

    def _navigated(self, frame):
        if frame == self.page.main_frame:
            self.queue.put({"type": "navigate", "url": frame.url, "t": time.time()})

    # ── reading the screen ────────────────────────────────────────────────
    def read_screen(self) -> list:
        """OCR of the page as a person sees it, with the recorder's own panel hidden."""
        hide = "v => { const ui = document.getElementById('visor-recorder-ui'); if (ui) ui.style.visibility = v; }"
        try:
            self.page.evaluate(hide, "hidden")
            self.page.screenshot(path=self.shot)
            return ocr.find_all(self.shot, self.page)
        except Exception as e:
            print(f"[RECORDER] Could not read the screen: {e}")
            return []
        finally:
            try:
                self.page.evaluate(hide, "visible")
            except Exception:
                pass

    def _settle_pending(self):
        """Read the screen after the last action and store what changed."""
        after = self.read_screen()
        if self.pending is not None:
            before = [i["text"] for i in self.screen]
            now = [i["text"] for i in after]
            self.pending["appeared"] = [t for t in now if t not in before]
            self.pending["disappeared"] = [t for t in before if t not in now]
        self.screen = after
        self.pending = None

    # ── events ────────────────────────────────────────────────────────────
    def process(self, event: dict):
        kind = event["type"]
        if kind == "note":
            self.note = event["text"]
            return
        if kind == "undo":
            if self.events:
                removed = self.events.pop()
                print(f"[RECORDER] Undid {removed['type']} {removed.get('label', '')!r}")
            return
        if kind == "stop":
            self.active = False
            return
        if self.pending is not None:
            self._settle_pending()  # the person moved on before the page settled
        if kind == "click":
            event["label"] = _click_label(event, self.screen)
        if self.note and kind != "navigate":
            event["note"], self.note = self.note, None
        self.events.append(event)
        print(f"[RECORDER] {kind} {event.get('label') or event.get('url') or ''!r}")
        self.pending, self.pending_at = event, time.time()

    def tick(self):
        while not self.queue.empty():
            self.process(self.queue.get_nowait())
        if self.pending is not None and time.time() - self.pending_at >= SETTLE:
            self._settle_pending()

    def finish(self):
        self.tick()
        if self.pending is not None:
            self._settle_pending()
        try:
            os.remove(self.shot)
        except OSError:
            pass

    def trace(self) -> dict:
        return {"flow": self.flow_name, "url": self.url, "description": self.description,
                "recorded_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "events": self.events}


def _click_label(event: dict, screen: list) -> str:
    """The text a person would say they clicked: OCR inside the element, else its label."""
    x, y = event["x"], event["y"]
    left, top, right, bottom = event.get("rect") or (x, y, x, y)
    inside = [i for i in screen if i["x1"] <= x <= i["x2"] and i["y1"] <= y <= i["y2"]]
    if not inside:
        inside = [i for i in screen if left - 2 <= i["x"] <= right + 2 and top - 2 <= i["y"] <= bottom + 2]
    if inside:
        return min(inside, key=lambda i: (i["x"] - x) ** 2 + (i["y"] - y) ** 2)["text"]
    return event.get("text") or ""


# ── turning a trace into a flow ──────────────────────────────────────────────

def _evidence(e: dict) -> str:
    """A short note of what changed after a step, for whoever reads or fixes the flow."""
    def few(texts):
        texts = [t if len(t) <= 30 else t[:27] + "..." for t in texts[:3]]
        return ", ".join(repr(t) for t in texts)
    parts = []
    if e.get("appeared"):
        parts.append("then saw " + few(e["appeared"]))
    if e.get("disappeared"):
        parts.append("gone " + few(e["disappeared"]))
    return "; ".join(parts)


def _env_name(label: str) -> str:
    name = re.sub(r"[^A-Z0-9]+", "_", (label or "").upper()).strip("_")
    return f"VISOR_{name or 'SECRET'}"


def _steps(trace: dict):
    """The trace as flow steps: ([(call, args, comment)], env vars needed)."""
    steps, envs = [], []
    last_action_at = None

    def add(call, *args, comment=""):
        steps.append([call, list(args), comment])

    for i, e in enumerate(trace.get("events", [])):
        kind = e["type"]
        if kind == "navigate":
            caused = last_action_at is not None and e["t"] - last_action_at <= NAV_AFTER_ACTION
            if not (i == 0 or caused or e["url"] in ("about:blank", trace.get("url"))):
                add("goto", repr(e["url"]))
            continue
        if kind == "scroll":
            continue  # visor scrolls to find text by itself
        last_action_at = e["t"]
        if e.get("note"):
            add("#", comment=e["note"])
        seen = _evidence(e)

        if kind == "click":
            if not e.get("label"):
                add("#", comment=f"clicked at ({e['x']:.0f}, {e['y']:.0f}) on something without text: add this step by hand")
                continue
            add("click", repr(e["label"]), comment=seen)
        elif kind == "fill":
            if e.get("secret"):
                env = _env_name(e["label"])
                envs.append(env)
                add("fill", repr(e["label"]), f"os.environ[{env!r}]", comment="value not recorded")
            else:
                add("fill", repr(e["label"]), repr(e.get("value") or ""))
        elif kind == "select":
            add("select", repr(e["label"]), repr(e["option"]), comment=seen)
        elif kind == "enter":
            if steps and steps[-1][0] == "fill":
                steps[-1][1].append("enter=True")
                steps[-1][2] = "; ".join(c for c in (steps[-1][2], seen) if c)
            else:
                add("press_key", '"Enter"', comment=seen)
    return steps, sorted(set(envs))


def synthesize(trace: dict, goal=None, replay: str = "not run yet") -> str:
    """Python source for a flow that repeats the trace and ends on the person's goal."""
    steps, envs = _steps(trace)
    doc = [f"Recorded with `visor record` on {trace.get('recorded_at', '')[:10]} from {trace.get('url', '')}"]
    if trace.get("description"):
        doc.append(f"Task: {trace['description']}")
    doc.append(f"Replay check: {replay}")
    if envs:
        doc.append("Set before running: " + ", ".join(envs))
    doc.append("Read it before running it on many targets.")

    out = ['"""', *doc, '"""']
    if envs:
        out.append("import os")
    out += ["import visor", "", ""]
    out.append(f"GOAL = {goal!r}" if goal else
               "GOAL = None  # put the text that means the task is done here")
    out += ["", "", "def run(target):", "    visor.goto(target)"]
    for call, args, comment in steps:
        if call == "#":
            out.append(f"    # {comment}")
        else:
            out.append(f"    visor.{call}({', '.join(args)})" + (f"  # {comment}" if comment else ""))
    out += ['    return "success"', ""]
    return "\n".join(out)


# ── recording, end to end ────────────────────────────────────────────────────

def record(flow_name: str, url: str, description: str = "") -> dict:
    """Open the URL in a new tab and record until Stop, Ctrl+C or the tab closes."""
    page = browser.new_tab()
    rec = Recorder(page, flow_name, url, description)
    rec.attach()
    print(f"[RECORDER] Opening {url}")
    page.goto(url, wait_until="domcontentloaded")
    browser.settle(page)
    rec.screen = rec.read_screen()
    print("[RECORDER] Do the task once. Click Stop (bottom right) or press Ctrl+C when done.")
    try:
        while rec.active and not page.is_closed():
            rec.tick()
            page.wait_for_timeout(50)
    except KeyboardInterrupt:
        print("\n[RECORDER] Stopped with Ctrl+C.")
    except Exception as e:
        print(f"\n[RECORDER] Tab or browser closed ({e}).")
    finally:
        try:
            rec.finish()
        except Exception:
            pass
    trace = rec.trace()
    path = os.path.join(TRACE_DIR, f"{flow_name}_trace.json")
    with open(path, "w") as f:
        json.dump(trace, f, indent=2, ensure_ascii=False)
    print(f"[RECORDER] Saved trace -> {path}")
    try:
        browser.close_tab()  # the recording panel stays out of the replay
    except Exception:
        pass
    return trace


def replay(flow_path: str, url: str) -> str:
    """Run the new flow once on the URL it was recorded on, with no agent, and return the status."""
    from visor.cli import load_flow
    from visor.config import settings
    from visor.core import runner

    flow_fn = load_flow(flow_path)
    results_csv = os.path.join(TRACE_DIR, f"{os.path.splitext(os.path.basename(flow_path))[0]}_replay.csv")
    if os.path.exists(results_csv):
        os.remove(results_csv)
    agent, settings.agent = settings.agent, False
    try:
        return runner.run_flow(flow_fn, [url], results_csv).get(url, "failed")
    finally:
        settings.agent = agent


def goal_hints(trace: dict) -> list:
    """Texts that appeared after the last action: candidates the person can pick a goal from."""
    for e in reversed(trace.get("events", [])):
        if e["type"] not in ("navigate", "scroll"):
            return [t for t in e.get("appeared", []) if len(t) <= 60][:8]
    return []


def write_flow(trace: dict, out_path: str, goal=None, verify: bool = True) -> str:
    """Write the flow file; if there is a goal, replay it once and note the result. Returns that result."""
    with open(out_path, "w") as f:
        f.write(synthesize(trace, goal))
    if not goal:
        status = "not run: no goal given"
    elif not verify:
        status = "skipped (--no-verify)"
    else:
        result = replay(out_path, trace["url"])
        status = (f"reached the goal on {trace['url']}" if result == "success"
                  else f"FAILED ({result}); fix this file before using it")
    with open(out_path, "w") as f:
        f.write(synthesize(trace, goal, replay=status))
    return status
