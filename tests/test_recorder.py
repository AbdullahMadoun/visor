"""The recorder keeps what changed after each action and turns it into a flow that checks itself."""
import json

import pytest

from conftest import page_url
from visor.core import recorder


def event(kind, t, **kw):
    return {"type": kind, "t": t, **kw}


TRACE = {
    "flow": "club", "url": "http://club.test/", "description": "join the book club",
    "recorded_at": "2026-10-31T10:00:00",
    "events": [
        event("navigate", 0, url="http://club.test/"),
        event("fill", 1, label="Email", value="me@example.com", secret=False, appeared=["me@example.com"]),
        event("fill", 2, label="Password", value=None, secret=True, note="use the club account"),
        event("scroll", 3, y=400),
        event("select", 4, label="Plan", option="Yearly"),
        event("click", 5, label="Join club", appeared=["3", "Plan Yearly", "Welcome aboard", "A very long paragraph " * 5],
              disappeared=[]),
        event("navigate", 6, url="http://club.test/welcome"),  # caused by the click
        event("navigate", 20, url="http://club.test/settings"),  # typed by the person
        event("click", 21, label="Delete draft", appeared=[], disappeared=["Delete draft"]),
        event("fill", 22, label="Search", value="dune", secret=False),
        event("enter", 23, appeared=["Results for dune"]),
    ],
}


def test_flow_checks_each_step_and_ends_with_a_goal():
    source = recorder.synthesize(TRACE)
    compile(source, "club.py", "exec")
    assert "GOAL = 'Results for dune'" in source
    assert "visor.click('Join club', expect='Welcome aboard')" in source  # not "3", not the echoed choice, not the paragraph
    assert "visor.fill('Email', 'me@example.com')" in source
    assert "visor.select('Plan', 'Yearly')" in source
    assert "visor.goto('http://club.test/settings')" in source
    assert "club.test/welcome" not in source  # that page load came from the click
    assert "visor.wait_gone('Delete draft')" in source  # nothing appeared, but the button went away
    assert "visor.fill('Search', 'dune', enter=True)" in source
    assert "visor.wait_for('Results for dune')" in source
    assert "# use the club account" in source


def test_passwords_come_from_the_environment():
    source = recorder.synthesize(TRACE)
    assert "visor.fill('Password', os.environ['VISOR_PASSWORD'])" in source
    assert "import os" in source and "VISOR_PASSWORD" in source.split('"""')[1]


def test_no_proof_means_no_goal_and_no_replay(tmp_path):
    trace = dict(TRACE, events=[event("click", 1, label="Open", appeared=["12:04"], disappeared=[])])
    assert "GOAL = None" in recorder.synthesize(trace)
    status = recorder.write_flow(trace, str(tmp_path / "f.py"))
    assert status.startswith("not run")
    assert status in (tmp_path / "f.py").read_text()


def test_pick_expect_skips_numbers_long_text_and_the_label_itself():
    assert recorder._pick_expect(["Join", "$9.99", "x" * 50, "Pending"], "Join") == "Pending"
    assert recorder._pick_expect(["12", "4:05"]) is None


@pytest.mark.browser
def test_record_a_form_and_replay_it(live, tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "TRACE_DIR", str(tmp_path))
    monkeypatch.setattr(recorder, "SETTLE", 0.6)
    monkeypatch.setenv("VISOR_PASSWORD", "hunter2")
    url = page_url("signup.html")

    page = live.new_tab()
    rec = recorder.Recorder(page, "club", url, "join the book club")
    rec.attach()
    page.goto(url)
    rec.screen = rec.read_screen()

    def settle():
        for _ in range(20):
            rec.tick()
            page.wait_for_timeout(60)

    page.click("#email"); page.keyboard.type("me@example.com"); page.keyboard.press("Tab"); settle()
    page.click("#pw"); page.keyboard.type("hunter2"); page.keyboard.press("Tab"); settle()
    page.select_option("#plan", "Yearly"); settle()
    page.click("text=Join club"); settle()
    rec.finish()
    live.close_tab()

    trace = rec.trace()
    assert "hunter2" not in json.dumps(trace)  # the password never reaches the trace
    kinds = [(e["type"], e.get("label")) for e in trace["events"] if e["type"] != "navigate"]
    assert kinds == [("fill", "Email"), ("fill", "Password"), ("select", "Plan"), ("click", "Join club")]
    assert "Welcome aboard" in trace["events"][-1]["appeared"]
    assert not any("Recording" in t for e in trace["events"] for t in e.get("appeared", []))

    out = tmp_path / "club.py"
    status = recorder.write_flow(trace, str(out))
    assert status.startswith("reached the goal"), out.read_text()
    assert "GOAL = 'Welcome aboard'" in out.read_text()
