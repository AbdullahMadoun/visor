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


def test_flow_ends_on_the_users_goal_and_keeps_changes_as_notes():
    source = recorder.synthesize(TRACE, goal="Results for dune")
    compile(source, "club.py", "exec")
    assert "GOAL = 'Results for dune'" in source
    assert "expect=" not in source and "wait_for" not in source  # no guessed checks per step
    assert "visor.click('Join club')  # then saw '3', 'Plan Yearly', 'Welcome aboard'" in source
    assert "visor.fill('Email', VALUES['Email'])" in source
    assert "visor.select('Plan', VALUES['Plan'])" in source
    assert "    'Email': 'me@example.com'," in source and "    'Plan': 'Yearly'," in source
    assert "visor.goto('http://club.test/settings')" in source
    assert "club.test/welcome" not in source  # that page load came from the click
    assert "visor.click('Delete draft')  # gone 'Delete draft'" in source
    assert "visor.fill('Search', VALUES['Search'], enter=True)  # then saw 'Results for dune'" in source
    assert "# use the club account" in source


def test_the_same_field_typed_twice_keeps_both_values():
    trace = dict(TRACE, events=[event("fill", 1, label="Name", value="Ann", secret=False),
                                event("fill", 2, label="Name", value="Bob", secret=False),
                                event("fill", 3, label="Name", value="Ann", secret=False)])
    source = recorder.synthesize(trace)
    compile(source, "f.py", "exec")
    assert "'Name': 'Ann'," in source and "'Name (2)': 'Bob'," in source
    assert source.count("VALUES['Name']") == 2 and source.count("VALUES['Name (2)']") == 1


def test_passwords_come_from_the_environment():
    source = recorder.synthesize(TRACE)
    assert "visor.fill('Password', os.environ['VISOR_PASSWORD'])" in source
    assert "import os" in source and "VISOR_PASSWORD" in source.split('"""')[1]


def test_without_a_goal_nothing_is_guessed_and_nothing_replayed(tmp_path):
    assert "GOAL = None" in recorder.synthesize(TRACE)
    status = recorder.write_flow(TRACE, str(tmp_path / "f.py"))
    assert status.startswith("not run")
    assert status in (tmp_path / "f.py").read_text()


def test_goal_hints_come_from_the_last_step():
    assert recorder.goal_hints(TRACE) == ["Results for dune"]


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
    assert "Welcome aboard" in recorder.goal_hints(trace)
    status = recorder.write_flow(trace, str(out), goal="Welcome aboard")
    assert status.startswith("reached the goal"), out.read_text()
    assert "GOAL = 'Welcome aboard'" in out.read_text()
