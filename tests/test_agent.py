"""visor agent: a model's answer is checked before it becomes a fix, and the whole loop heals a flow."""
import json
import sys
import threading

import pytest

from conftest import page_url
from visor import agent
from visor.config import settings
from visor.core import runner
from visor.strategy import tree as strategy_tree

FAILURE = {"kind": "text_not_found", "step": "find_Join", "flow": "events", "url": "https://x/2",
           "timestamp": "t1", "ocr_results": ["Community meetup", "Learn more about our events", "More"],
           "controls": [{"role": "button", "name": "Settings", "on_screen_text": False}]}

MENU = {"action": "ocr_click", "target": "More", "then": "retry", "reason": "Join is in the More menu",
        "save_rule": True, "condition": "More"}


def test_a_visible_click_becomes_a_fix_with_a_rule_shaped_by_visor():
    fix = agent.to_fix(MENU, FAILURE)
    assert fix == {"action": "ocr_click", "target": "More", "then": "retry", "reason": "Join is in the More menu",
                   "save_to_tree": {"events.find_Join.not_found.More_visible":
                                    {"action": "click_ocr", "target": "More", "then": "retry"}}}


def test_a_control_name_counts_as_on_screen():
    assert agent.to_fix(dict(MENU, target="Settings", save_rule=False), FAILURE)["target"] == "Settings"


@pytest.mark.parametrize("answer, why", [
    (dict(MENU, target="Delete account"), "not on screen"),       # injected or invented
    (dict(MENU, target="events on"), "not on screen"),            # not a run of whole words in one text
    (dict(MENU, action="restart_flow"), "unknown action"),
])
def test_answers_that_could_do_harm_become_skips(answer, why):
    fix = agent.to_fix(answer, FAILURE)
    assert fix["action"] == "skip" and why in fix["reason"]


def test_a_rejected_fix_is_not_repeated():
    failure = dict(FAILURE, rejected_fixes=[{"branch": "events.find_Join.not_found.More_visible",
                                             "fix": {"action": "click_ocr", "target": "More"}}])
    assert agent.to_fix(MENU, failure)["action"] == "skip"


def test_no_rule_without_a_visible_condition_or_for_a_goal():
    assert "save_to_tree" not in agent.to_fix(dict(MENU, condition="Menu"), FAILURE)
    goal = dict(FAILURE, step="goal:Joined", kind="goal_not_met")
    fix = agent.to_fix(MENU, goal)
    assert "save_to_tree" not in fix and "then" not in fix


def test_labels_with_punctuation_keep_the_runners_spelling():
    failure = dict(FAILURE, step="find_Sign-in", ocr_results=["Sign-in options"])
    fix = agent.to_fix(dict(MENU, target="Sign-in options", condition="Sign-in options"), failure)
    assert list(fix["save_to_tree"]) == ["events.find_Sign-in.not_found.Sign-in_options_visible"]


def test_a_broken_reply_becomes_a_skip_never_an_exception():
    assert agent.answer(FAILURE, lambda p: "Sure! " + json.dumps(MENU) + " Hope that helps.")["target"] == "More"
    assert agent.answer(FAILURE, lambda p: "no idea")["action"] == "skip"
    def boom(p):
        raise RuntimeError("network down")
    assert "network down" in agent.answer(FAILURE, boom)["reason"]


def test_any_program_can_answer(tmp_path):
    script = tmp_path / "model.py"
    script.write_text("import sys, json\nsys.stdin.read()\nprint(json.dumps(%r))\n" % MENU)
    ask = agent.ask_command(f"{sys.executable} {script}")
    assert agent.answer(FAILURE, ask)["target"] == "More"


def test_watch_answers_one_failure(tmp_path):
    (tmp_path / "failure.json").write_text(json.dumps(FAILURE))
    fix = agent.watch(str(tmp_path), lambda p: json.dumps(MENU), once=True, poll=0.05)
    assert json.loads((tmp_path / "fix.json").read_text()) == fix


def test_the_page_text_is_sent_but_not_the_screenshot_path():
    prompt = agent.prompt_for(dict(FAILURE, screenshot_path="/secret/shot.png"))
    assert "Learn more about our events" in prompt and "shot.png" not in prompt


# ── The whole loop on a real page ────────────────────────────────────────────

@pytest.mark.browser
def test_the_agent_heals_a_flow_once_and_the_tree_handles_the_next_target(live, tmp_path, monkeypatch):
    import visor
    monkeypatch.setattr(strategy_tree, "TREE_PATH", str(tmp_path / "tree.json"))
    for name in ("_probation", "_rejected", "_unreviewed"):
        monkeypatch.setattr(runner, name, [])
    monkeypatch.setattr(runner, "HANDSHAKE_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "FAILURE_JSON", str(tmp_path / "failure.json"))
    monkeypatch.setattr(runner, "FIX_JSON", str(tmp_path / "fix.json"))
    monkeypatch.setattr(settings, "agent", True)
    monkeypatch.setattr(settings, "agent_timeout", 20)
    monkeypatch.setattr(settings, "timeout", 2)

    asked = []
    def model(prompt):  # stands in for Claude: reads the report, answers like a model would
        asked.append(json.loads(prompt))
        return json.dumps(MENU)
    threading.Thread(target=agent.watch, args=(str(tmp_path), model),
                     kwargs={"once": True, "poll": 0.1}, daemon=True).start()

    def flow(url):
        visor.goto(url)
        visor.click("Join")
        return "success" if visor.see("joined") else "failed"

    url = page_url("learn_more.html") + "?menu=1"
    results = runner.run_flow(flow, [url, url + "&again=1"], str(tmp_path / "r.csv"), flow_key="events")
    assert results == {url: "success", url + "&again=1": "success"}
    assert len(asked) == 1 and "More" in asked[0]["ocr_results"]  # one model call for two targets
    branch = json.loads((tmp_path / "tree.json").read_text())["events"]["find_Join"]["not_found"]["More_visible"]
    assert branch["target"] == "More" and branch["proven_on"] == url
