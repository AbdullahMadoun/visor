"""CLI: targets, flow loading, commands."""
import sys

import pytest

from visor import cli
from visor.core import runner


def test_targets_from_csv_skip_finished_rows(tmp_path):
    f = tmp_path / "t.csv"
    f.write_text("url,status\nhttps://a,pending\nhttps://b,success\nhttps://c,skipped:private\nhttps://d,failed\n")
    assert cli.load_targets(str(f)) == ["https://a", "https://d"]


def test_targets_from_text_file(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("https://a\n\n# a comment\nhttps://b\n")
    assert cli.load_targets(str(f)) == ["https://a", "https://b"]


def test_load_flow_by_path_registers_module_for_hot_reload(tmp_path):
    f = tmp_path / "my_flow.py"
    f.write_text("def main(url):\n    return 'v1'\n")
    fn = cli.load_flow(str(f))
    assert fn("x") == "v1"
    assert sys.modules["visor_user_flow_my_flow"] is runner._active_module
    f.write_text("def main(url):\n    return 'version two'\n")
    assert runner._reload_module(runner._active_module).main("x") == "version two"


def test_load_flow_falls_back_to_the_file_name(tmp_path):
    f = tmp_path / "scrape.py"
    f.write_text("def scrape(url):\n    return 'ok'\n")
    assert cli.load_flow(str(f))("x") == "ok"


def test_load_flow_without_entry_point_says_so(tmp_path):
    f = tmp_path / "empty.py"
    f.write_text("x = 1\n")
    with pytest.raises(AttributeError, match="main/run/run_task"):
        cli.load_flow(str(f))


def test_run_needs_targets(capsys):
    with pytest.raises(SystemExit):
        cli.cmd_run(["--flow", "x.py"])


def test_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    assert "visor login" in capsys.readouterr().out


def test_run_end_to_end_with_a_python_file_flow(tmp_path, monkeypatch):
    flow = tmp_path / "count.py"
    flow.write_text("seen = []\ndef main(url):\n    seen.append(url)\n    return 'success'\n")
    out = tmp_path / "results.csv"
    monkeypatch.setattr(cli, "WORKSPACE_DIR", str(tmp_path))
    code = cli.cmd_run(["--flow", str(flow), "--url", "https://a", "--url", "https://b",
                        "--results", str(out), "--no-agent"])
    assert code == 0
    assert out.read_text().count("success") == 2
