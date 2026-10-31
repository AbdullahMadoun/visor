"""
Self-healing, end to end, on your machine. No API key, no internet.

    python examples/self_healing_demo.py            # watch it in a window
    python examples/self_healing_demo.py --record   # also save visor_workspace/videos/self_healing.webm

A tiny local site serves three event pages. The flow clicks "RSVP" on each.

  page 1  old layout: "RSVP" is on screen        -> OCR finds it, clicks, done
  page 2  redesign:   "RSVP" moved under "More"  -> not found, tree has no fix -> AGENT_NEEDED
                                                    the agent answers with a fix and saves it to tree.json
  page 3  redesign again                         -> the tree already knows: More -> RSVP, no agent call

The "agent" here is a ten-line stand-in so the demo runs offline. In real use
it is Claude, Gemini, any coding agent, or you: something that reads
agent_handshake/failure.json (the visible text, no screenshot) and writes fix.json.
"""
import csv
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# A throwaway workspace, so the demo never touches your sessions or learned tree
os.environ.setdefault("VISOR_WORKSPACE", tempfile.mkdtemp(prefix="visor_demo_"))
os.environ.setdefault("VISOR_ATTACH", "0")
os.environ.setdefault("VISOR_PACE", "0")

import visor  # noqa: E402
from visor.core import browser, runner  # noqa: E402

RECORD = "--record" in sys.argv
FLOW = "rsvp"
state = {"agent_calls": 0, "t0": time.time()}
timeline = []  # (seconds since the browser opened, caption, detail): captions for the recorded video


def say(caption, detail="", hold=0.0):
    timeline.append((round(time.time() - state["t0"], 2), caption, detail))
    print(f"[DEMO] {caption}" + (f"  ({detail})" if detail else ""))
    time.sleep(hold)


# --- the local site ----------------------------------------------------------

EVENTS = {
    "1": ("Rust meetup", "Thursday 7 pm, Room 204"),
    "2": ("Board game night", "Friday 8 pm, the café"),
    "3": ("Morning run club", "Saturday 6 am, north gate"),
}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{font:22px -apple-system,system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}
header{background:#1f6f5c;color:#fff;padding:14px 32px;font-weight:600}
main{max-width:640px;margin:36px auto;background:#fff;border-radius:14px;padding:30px 36px;box-shadow:0 2px 10px #0001}
h1{margin:0 0 6px;font-size:34px} p{color:#5a6372;margin:0 0 26px}
.row{display:flex;gap:14px;align-items:flex-start}
button{font:inherit;padding:10px 24px;border-radius:9px;border:1px solid #c9ced8;background:#fff;cursor:pointer}
button.primary{background:#1f6f5c;color:#fff;border-color:#1f6f5c}
.menu{position:relative} .items{display:none;position:absolute;top:54px;left:0;background:#fff;border:1px solid #c9ced8;border-radius:9px;min-width:170px;box-shadow:0 6px 18px #0002}
.items.open{display:block} .items button{display:block;width:100%;border:0;text-align:left}
#cursor{position:fixed;width:30px;height:30px;margin:-15px 0 0 -15px;border-radius:50%;border:3px solid #ff2d55;pointer-events:none;opacity:0;transition:opacity .4s}
</style></head><body>
<header>Neighbourhood Events</header>
<main><h1>__TITLE__</h1><p>__WHEN__</p><div class="row">__BUTTONS__</div></main>
<div id="cursor"></div>
<script>
function rsvp(b){document.querySelectorAll('.items').forEach(m=>m.classList.remove('open'));
 const g=document.createElement('button');g.className='primary';g.textContent='Going \\u2713';
 if(b.closest('.items'))document.querySelector('.row').prepend(g);else b.replaceWith(g)}
// A ring where Visor clicks, so the recording shows it; it fades so it never covers text OCR needs
const c=document.getElementById('cursor');let fade;
addEventListener('mousedown',e=>{c.style.left=e.clientX+'px';c.style.top=e.clientY+'px';c.style.opacity=1;clearTimeout(fade);fade=setTimeout(()=>c.style.opacity=0,500)});
</script></body></html>"""

OLD = '<button onclick="rsvp(this)">RSVP</button><button>Share</button>'
NEW = ('<button>Share</button><div class="menu"><button onclick="this.nextElementSibling.classList.toggle(\'open\')">'
       'More ▾</button><div class="items"><button onclick="rsvp(this)">RSVP</button><button>Report</button></div></div>')


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        title, when = EVENTS.get(q.get("id", ["1"])[0], EVENTS["1"])
        buttons = NEW if q.get("layout") == ["new"] else OLD
        body = PAGE.replace("__TITLE__", title).replace("__WHEN__", when).replace("__BUTTONS__", buttons).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


# --- the stand-in agent --------------------------------------------------------

def stand_in_agent():
    """Watch for failure.json; answer once with a fix that also teaches the tree."""
    while not os.path.exists(runner.FAILURE_JSON):
        time.sleep(0.2)
    with open(runner.FAILURE_JSON) as f:
        failure = json.load(f)
    state["agent_calls"] += 1
    seen = ", ".join(repr(t) for t in failure["ocr_results"][:8])
    say("AGENT_NEEDED: Visor pauses and writes failure.json",
        f"step: {failure['step']}\nvisible text: {seen}", hold=3.5)

    # A real agent reasons about the visible text; this one knows the answer
    fix = {
        "action": "ocr_click", "target": "More", "then": "retry",
        "save_to_tree": {f"{FLOW}.find_RSVP.not_found.More_visible":
                         {"action": "click_ocr", "target": "More", "then": "retry_find_RSVP"}},
    }
    say("The agent answers in fix.json: open 'More', then look again",
        "save_to_tree: if 'More' is visible -> click it -> find 'RSVP'", hold=3.0)
    with open(runner.FIX_JSON + ".tmp", "w") as f:
        json.dump(fix, f)
    os.replace(runner.FIX_JSON + ".tmp", runner.FIX_JSON)


# --- the flow ------------------------------------------------------------------

CAPTIONS = {
    "1": ("Page 1: Visor reads the screen (local OCR) and clicks 'RSVP'", "visor.click('RSVP')"),
    "2": ("Page 2: the site was redesigned. 'RSVP' is not on screen", "visor.click('RSVP')  ->  not found, tree has no fix"),
    "3": ("Page 3: same redesign. The fix is already in tree.json", "tree: More -> RSVP   (no agent call)"),
}


def main(url):
    event = parse_qs(urlparse(url).query)["id"][0]
    visor.goto(url)
    say(*CAPTIONS[event], hold=2.2)
    visor.click("RSVP")
    visor.wait_for("Going")
    say("Done: the button says 'Going'", f"agent calls so far: {state['agent_calls']}", hold=2.0)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/event"
    targets = [f"{base}?id=1&layout=old", f"{base}?id=2&layout=new", f"{base}?id=3&layout=new"]

    visor.configure(viewport=(960, 400))
    browser.init_browser(record_video=RECORD)
    state["t0"] = time.time()  # the video starts with the browser
    threading.Thread(target=stand_in_agent, daemon=True).start()

    results = os.path.join(os.environ["VISOR_WORKSPACE"], "results.csv")
    runner.run_flow(main, targets, results, flow_key=FLOW)
    with open(results) as f:
        done = sum(row["status"] in runner.DONE_STATUSES for row in csv.DictReader(f))
    calls = state["agent_calls"]
    say(f"{done} of 3 done with {calls} agent call{'s' * (calls != 1)}. The fix is reused from now on",
        "visor tree   # shows what was learned", hold=3.0)

    video = browser.get_page().video.path() if RECORD else None
    browser.close(save=False)  # the video file is complete once the browser closes
    if video:
        out = os.path.join(os.getcwd(), "visor_workspace", "videos", "self_healing.webm")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy(video, out)
        with open(out.replace(".webm", ".captions.json"), "w") as f:
            json.dump(timeline, f, indent=1)
        print(f"[DEMO] Video: {out}  (captions: scripts/render_demo_gif.py)")
    server.shutdown()
