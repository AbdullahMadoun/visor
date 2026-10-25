"""run_flow bookkeeping, statuses and the agent handshake (no browser needed)."""
import csv

import pytest

from visor.config import settings
from visor.core import runner
from visor.errors import Skip, RestartFlow, TextNotFound


def statuses(path):
    with open(path) as f:
        return {row["target"]: row["status"] for row in csv.DictReader(f)}


def test_statuses_from_return_values_and_exceptions(tmp_path):
    outcomes = {
        "a": lambda: None,          # finished without raising
        "b": lambda: True,
        "c": lambda: False,
        "d": lambda: "skipped:private",
        "e": lambda: (_ for _ in ()).throw(Skip("sold out")),
        "f": lambda: (_ for _ in ()).throw(TextNotFound("Buy")),
        "g": lambda: 1 / 0,
    }
    out = tmp_path / "results.csv"
    results = runner.run_flow(lambda t: outcomes[t](), list(outcomes), str(out))
    assert results == {"a": "success", "b": "success", "c": "failed", "d": "skipped:private",
                       "e": "skipped:sold out", "f": "failed", "g": "failed"}
    assert statuses(out) == results


def test_resume_skips_finished_targets_including_skipped_with_reason(tmp_path):
    out = tmp_path / "results.csv"
    runner._write_csv({"a": "success", "b": "skipped:private", "c": "failed"}, str(out))
    ran = []
    runner.run_flow(lambda t: ran.append(t) or "success", ["a", "b", "c"], str(out))
    assert ran == ["c"]


def test_report_counts_only_current_targets(tmp_path, capsys):
    out = tmp_path / "results.csv"
    runner._write_csv({f"old{i}": "success" for i in range(10)}, str(out))
    runner.run_flow(lambda t: "success", ["new"], str(out), max_retries=3)
    report = capsys.readouterr().out
    assert "1/1 actionable succeeded (100%)" in report
    assert report.count("[RUN] Attempt") == 1  # stopped as soon as everything passed
    assert "old3" in statuses(out)  # history kept


def test_retries_failed_targets(tmp_path):
    attempts = []
    def flow(t):
        attempts.append(t)
        return "success" if len(attempts) > 1 else "failed"
    results = runner.run_flow(flow, ["x"], str(tmp_path / "r.csv"), max_retries=2)
    assert results == {"x": "success"} and attempts == ["x", "x"]


def test_restart_flow_retries_the_target(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_active_module", None, raising=False)
    calls = []
    def flow(t):
        calls.append(t)
        if len(calls) == 1:
            raise RestartFlow()
        return "success"
    results = runner.run_flow(flow, ["x"], str(tmp_path / "r.csv"), max_retries=2)
    assert results == {"x": "success"}


def test_interrupt_saves_progress(tmp_path):
    out = tmp_path / "r.csv"
    def flow(t):
        if t == "b":
            raise KeyboardInterrupt
        return "success"
    with pytest.raises(KeyboardInterrupt):
        runner.run_flow(flow, ["a", "b"], str(out))
    assert statuses(out)["a"] == "success"


def test_heal_settings_are_restored(tmp_path):
    seen = []
    runner.run_flow(lambda t: seen.append((settings.heal, settings.flow)), ["x"], str(tmp_path / "r.csv"),
                    flow_key="shop_flow")
    assert seen == [(True, "shop_flow")]
    assert settings.heal is False and settings.flow == ""


def test_agent_disabled_fails_fast(monkeypatch):
    monkeypatch.setattr(settings, "agent", False)
    assert runner._signal_agent("find_X", "https://x", [], "")["action"] == "fail"


def test_default_tree_branch_applies_after_specific_ones(monkeypatch, tmp_path):
    tree = {"flow": {"find_Buy": {"not_found": {
        "default": {"action": "skip", "reason": "fallback"},
        "Sold_out_visible": {"action": "skip", "reason": "sold out"},
    }}}}
    monkeypatch.setattr(runner.strategy_tree, "load", lambda: tree)
    assert runner._recover("Buy", "u", "flow", True, None, None, "", ["Sold out"]) == "skipped:sold out"
    assert runner._recover("Buy", "u", "flow", True, None, None, "", ["Other"]) == "skipped:fallback"
