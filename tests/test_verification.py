"""Verification: a flow's goal decides success, and agent fixes are saved only once proven."""
import csv
import json
import sys
import types

import pytest

from conftest import page_url
from visor.config import settings
from visor.core import runner
from visor.errors import TextNotFound
from visor.strategy import tree as strategy_tree


@pytest.fixture
def tree_file(tmp_path, monkeypatch):
    path = tmp_path / "tree.json"
    monkeypatch.setattr(strategy_tree, "TREE_PATH", str(path))
    monkeypatch.setattr(runner, "_probation", [])
    monkeypatch.setattr(runner, "_rejected", [])
    return path


def saved(path):
    return json.loads(path.read_text()) if path.exists() else {}


FIX = {"action": "ocr_click", "target": "More", "then": "retry", "reason": "Join moved under More",
       "save_to_tree": {"events.find_Join.not_found.More_visible":
                        {"action": "click_ocr", "target": "More", "then": "retry_find_Join"}}}


def test_fix_is_saved_only_after_it_is_proven(tree_file):
    runner._hold(FIX)
    assert saved(tree_file) == {}  # on probation, not in the tree yet
    runner._commit_probation("https://example.com/event/2")
    branch = saved(tree_file)["events"]["find_Join"]["not_found"]["More_visible"]
    assert branch["target"] == "More"
    assert branch["proven_on"] == "https://example.com/event/2"
    assert branch["reason"] == "Join moved under More"  # the agent's reasoning is kept with the rule


def test_fix_that_fails_is_dropped_and_reported_to_the_agent(tree_file, monkeypatch, tmp_path):
    runner._hold(FIX)
    assert runner._run_target(lambda t: "failed", "https://example.com/event/2") == "failed"
    assert saved(tree_file) == {}
    assert runner._rejected[0]["branch"] == "events.find_Join.not_found.More_visible"

    # The next handshake tells the agent its last idea did not work
    monkeypatch.setattr(settings, "agent", True)
    monkeypatch.setattr(settings, "agent_timeout", 0.2)
    monkeypatch.setattr(runner, "HANDSHAKE_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "FAILURE_JSON", str(tmp_path / "failure.json"))
    monkeypatch.setattr(runner, "FIX_JSON", str(tmp_path / "fix.json"))
    runner._signal_agent("find_Join", "https://example.com/event/3", ["Share", "More"], "")
    payload = json.loads((tmp_path / "failure.json").read_text())
    assert payload["kind"] == "text_not_found"
    assert payload["rejected_fixes"][0]["branch"] == "events.find_Join.not_found.More_visible"


def test_fix_made_during_a_successful_target_is_saved(tree_file):
    def flow(t):
        runner._hold(FIX)  # as if the agent answered mid-flow
        return "success"
    assert runner._run_target(flow, "https://example.com/event/2") == "success"
    assert "events" in saved(tree_file)


def test_global_branch_applies_to_every_flow(monkeypatch):
    tree = {"_global": {"find_Join": {"not_found": {"Sold_out_visible": {"action": "skip", "reason": "sold out"}}}}}
    monkeypatch.setattr(runner.strategy_tree, "load", lambda: tree)
    assert runner._recover("Join", "u", "any_flow", True, None, None, "", ["Sold out"]) == "skipped:sold out"


def test_flow_specific_branch_wins_over_global(monkeypatch):
    tree = {"_global": {"find_Join": {"not_found": {"default": {"action": "skip", "reason": "global"}}}},
            "mine": {"find_Join": {"not_found": {"default": {"action": "skip", "reason": "mine"}}}}}
    monkeypatch.setattr(runner.strategy_tree, "load", lambda: tree)
    assert runner._recover("Join", "u", "mine", True, None, None, "", []) == "skipped:mine"


@pytest.fixture
def fake_page(monkeypatch):
    monkeypatch.setattr(runner.browser, "_page", object())
    monkeypatch.setattr(runner, "_save_screenshot", lambda label: "")


def test_goal_on_screen_beats_a_reported_failure(fake_page, monkeypatch):
    monkeypatch.setattr(runner, "goal_met", lambda goal, timeout=None: True)
    def flow(t):
        raise TextNotFound("Send")  # e.g. the request went straight to Pending, no modal
    assert runner._run_one(flow, "x", goal="Pending") == "success"


def test_finished_flow_without_its_goal_fails(fake_page, monkeypatch):
    monkeypatch.setattr(runner, "goal_met", lambda goal, timeout=None: False)
    monkeypatch.setattr(settings, "agent", False)
    assert runner._run_one(lambda t: "success", "x", goal="Pending") == "failed"


def test_goal_must_still_be_there_a_moment_later(monkeypatch):
    # Seen once, then gone: a flash or a glitch is not success
    monkeypatch.setattr(runner.actions, "wait_for", lambda labels, timeout=None, **kw: {"label": labels[0]})
    monkeypatch.setattr(runner.actions, "see", lambda labels, **kw: False)
    monkeypatch.setattr(runner.browser, "wait", lambda ms: None)
    assert runner.goal_met("Request sent") is False
    monkeypatch.setattr(runner.actions, "see", lambda labels, **kw: True)
    assert runner.goal_met("Request sent") is True


def test_goal_comes_from_the_flow_module(tmp_path, monkeypatch):
    module = types.ModuleType("visor_user_flow_goal_test")
    module.GOAL = "Request sent"
    monkeypatch.setitem(sys.modules, module.__name__, module)
    def flow(t):
        return "success"
    flow.__module__ = module.__name__
    seen = []
    monkeypatch.setattr(runner, "_run_target", lambda fn, url, goal=None: seen.append(goal) or "success")
    runner.run_flow(flow, ["x"], str(tmp_path / "r.csv"))
    assert seen == ["Request sent"]


@pytest.mark.browser
def test_goal_checked_on_a_real_page(live, tmp_path):
    import visor

    def flow(button):
        visor.goto(page_url("goal.html"))
        visor.click(button)

    out = tmp_path / "r.csv"
    results = runner.run_flow(flow, ["Join", "Nothing"], str(out), goal="Request sent")
    # "Nothing" was clicked fine, but the goal never appeared: that is a failure
    assert results == {"Join": "success", "Nothing": "failed"}
    with open(out) as f:
        assert {r["target"]: r["status"] for r in csv.DictReader(f)} == results


def test_skip_with_the_goal_on_screen_counts_as_success(fake_page, monkeypatch):
    monkeypatch.setattr(runner, "goal_met", lambda goal, timeout=None: True)
    def flow(t):
        raise runner.Skip("already pending")  # it went straight to Pending, no modal
    assert runner._run_one(flow, "x", goal="Pending") == "success"
    monkeypatch.setattr(runner, "goal_met", lambda goal, timeout=None: False)
    assert runner._run_one(flow, "x", goal="Pending") == "skipped:already pending"


def test_failure_json_says_where_the_browser_really_is(monkeypatch, tmp_path):
    class Page:
        url = "https://site.test/profile/9"
    monkeypatch.setattr(runner.browser, "_page", Page())
    monkeypatch.setattr(runner, "_current_target", "https://site.test/search?q=x")
    monkeypatch.setattr(settings, "agent", True)
    monkeypatch.setattr(settings, "agent_timeout", 0.2)
    monkeypatch.setattr(runner.browser, "wait", lambda ms: None)
    monkeypatch.setattr(runner, "HANDSHAKE_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "FAILURE_JSON", str(tmp_path / "failure.json"))
    monkeypatch.setattr(runner, "FIX_JSON", str(tmp_path / "fix.json"))
    runner._signal_agent("find_Next", "https://site.test/search?q=x", [], "")
    payload = json.loads((tmp_path / "failure.json").read_text())
    assert payload["target"] == "https://site.test/search?q=x"
    assert payload["page_url"] == "https://site.test/profile/9"


def test_goal_can_depend_on_the_target(fake_page, monkeypatch):
    seen = []
    monkeypatch.setattr(runner, "goal_met", lambda goal, timeout=None: seen.append(goal) or True)
    status = runner._run_target(lambda t: "success", "omar", goal=lambda t: f"Booked for {t}")
    assert status == "success" and seen == ["Booked for omar"]


def test_a_skip_never_saves_the_agents_branch(tree_file):
    runner._hold(dict(FIX, action="skip"))
    assert runner._run_target(lambda t: "skipped:agent", "https://example.com/event/9") == "skipped:agent"
    assert saved(tree_file) == {}


def test_tree_fallback_that_does_not_reveal_the_label_fails(monkeypatch):
    # Inside a re-check, a matching branch must not claim success without finding the label
    tree = {"f": {"find_Submit": {"not_found": {"More_visible": {
        "action": "click_ocr", "target": "More", "then": "retry_find_Submit"}}}}}
    monkeypatch.setattr(runner.strategy_tree, "load", lambda: tree)
    pressed = []
    monkeypatch.setattr(runner.actions, "press", lambda m: pressed.append(m))
    assert runner._recover("Submit", "u", "f", False, None, None, "", ["More"]) == "failed"
    assert pressed == []  # and it doesn't click More again (that would close the menu)


def _handshake_files(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agent", True)
    monkeypatch.setattr(settings, "agent_timeout", 0.2)
    monkeypatch.setattr(runner, "HANDSHAKE_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "FAILURE_JSON", str(tmp_path / "failure.json"))
    monkeypatch.setattr(runner, "FIX_JSON", str(tmp_path / "fix.json"))


def test_rejected_fixes_are_remembered_by_the_next_run(tree_file, monkeypatch, tmp_path):
    runner._hold(FIX)
    runner._run_target(lambda t: "failed", "https://example.com/event/2")
    monkeypatch.setattr(runner, "_rejected", [])  # a new run starts with nothing in memory
    monkeypatch.setattr(settings, "flow", "events")
    _handshake_files(monkeypatch, tmp_path)
    runner._signal_agent("find_Join", "https://example.com/event/3", ["More"], "")
    payload = json.loads((tmp_path / "failure.json").read_text())
    assert payload["rejected_fixes"][0]["branch"] == "events.find_Join.not_found.More_visible"


def test_another_flows_rejected_fixes_are_not_shown(tree_file, monkeypatch, tmp_path):
    runner._hold(FIX)
    runner._run_target(lambda t: "failed", "https://example.com/event/2")
    monkeypatch.setattr(runner, "_rejected", [])
    monkeypatch.setattr(settings, "flow", "shop")
    _handshake_files(monkeypatch, tmp_path)
    runner._signal_agent("find_Buy", "https://example.com/item", ["Cart"], "")
    assert "rejected_fixes" not in json.loads((tmp_path / "failure.json").read_text())


def test_review_mode_holds_proven_fixes_until_approved(tree_file, monkeypatch):
    monkeypatch.setattr(settings, "review", True)
    runner._hold(FIX)
    runner._commit_probation("https://example.com/event/2")
    assert saved(tree_file) == {}  # proven, but a person hasn't approved it
    assert strategy_tree.load_side(strategy_tree.PENDING)[0]["branch"] == "events.find_Join.not_found.More_visible"
    assert strategy_tree.review(ask=lambda prompt: "a") == 0
    assert saved(tree_file)["events"]["find_Join"]["not_found"]["More_visible"]["target"] == "More"
    assert strategy_tree.load_side(strategy_tree.PENDING) == []


def test_review_can_reject_or_defer(tree_file, monkeypatch):
    monkeypatch.setattr(settings, "review", True)
    other = {"save_to_tree": {"events.find_Leave.not_found.Menu_visible": {"action": "click_ocr", "target": "Menu"}}}
    runner._hold(FIX)
    runner._hold(other)
    runner._commit_probation("https://example.com/event/2")
    answers = iter(["r", ""])
    assert strategy_tree.review(ask=lambda prompt: next(answers)) == 1
    assert saved(tree_file) == {}
    assert strategy_tree.load_side(strategy_tree.REJECTED)[-1]["why"] == "rejected by a reviewer"
    assert strategy_tree.load_side(strategy_tree.PENDING)[0]["branch"] == "events.find_Leave.not_found.Menu_visible"


# ── The controls list: what the agent can name besides visible text ──────────

def test_controls_lists_icon_buttons_by_name_and_skips_covered_or_offscreen(live):
    import visor
    from visor.core import actions
    visor.goto(page_url("shop.html"))
    found = {(c["role"], c["name"]): c for c in actions.controls(visible_text=visor.read())}
    assert found[("button", "Settings")]["on_screen_text"] is False  # icon only: ⚙
    assert found[("button", "Checkout")]["on_screen_text"] is True
    assert ("textbox", "Email address") in found  # named by its <label>
    assert ("button", "Load more") not in found   # below the fold

    visor.goto(page_url("covered.html"))
    names = [c["name"] for c in actions.controls()]
    assert "Open settings" in names
    assert "View profile" not in names  # painted over by "Language"; a click would hit that instead


def test_agent_can_name_an_icon_only_control_from_the_list(live):
    import visor
    from conftest import log_text
    visor.goto(page_url("shop.html"))
    status = runner._apply_fix({"action": "ocr_click", "target": "Settings"}, "Preferences",
                               visor.page().url, "shop", None, None)
    assert status == "agent_fixed" and log_text() == "settings"


def test_failure_json_includes_the_controls(live, monkeypatch, tmp_path):
    import visor
    visor.goto(page_url("shop.html"))
    _handshake_files(monkeypatch, tmp_path)
    runner._signal_agent("find_Preferences", visor.page().url, visor.read(), "")
    payload = json.loads((tmp_path / "failure.json").read_text())
    assert {"role": "button", "name": "Settings"}.items() <= next(
        c for c in payload["controls"] if c["name"] == "Settings").items()
