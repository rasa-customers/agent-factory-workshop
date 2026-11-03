"""`workshop eval`: run Mantle's simulated-conversation evals against the foreman or the latest built agent."""
from pathlib import Path

import pytest

from workshop import evals
from workshop.cli import main


def make_project(root: Path, scenarios: dict[str, str] | None = None) -> Path:
    (root / "eval" / "scenarios").mkdir(parents=True)
    (root / "eval" / "conftest.yml").write_text("simulation: {}\n")
    for name, text in (scenarios or {}).items():
        (root / "eval" / "scenarios" / name).write_text(text)
    return root


def test_all_scenarios_by_default_sorted_and_relative(tmp_path):
    project = make_project(tmp_path, {"b.yml": "x", "a.yml": "x", "notes.txt": "x"})
    assert evals.scenario_paths(project, []) == ["eval/scenarios/a.yml", "eval/scenarios/b.yml"]


def test_a_scenario_can_be_named_without_its_folder_or_extension(tmp_path):
    project = make_project(tmp_path, {"trip_check.yml": "x", "other.yml": "x"})
    assert evals.scenario_paths(project, ["trip_check"]) == ["eval/scenarios/trip_check.yml"]
    assert evals.scenario_paths(project, ["eval/scenarios/other.yml"]) == ["eval/scenarios/other.yml"]


def test_an_unknown_scenario_says_which_exist(tmp_path):
    project = make_project(tmp_path, {"trip_check.yml": "x"})
    with pytest.raises(SystemExit, match="trip_check"):
        evals.scenario_paths(project, ["nope"])


def test_seeding_fills_in_what_an_older_build_is_missing_and_keeps_edits(tmp_path):
    template = make_project(tmp_path / "template", {"trip_check.yml": "template", "dashboard_link.yml": "template"})
    build = tmp_path / "build"
    (build / "eval" / "scenarios").mkdir(parents=True)
    (build / "eval" / "scenarios" / "trip_check.yml").write_text("edited by the attendee")
    evals.seed_eval(build, template)
    assert (build / "eval" / "conftest.yml").exists()
    assert (build / "eval" / "scenarios" / "dashboard_link.yml").read_text() == "template"
    assert (build / "eval" / "scenarios" / "trip_check.yml").read_text() == "edited by the attendee"


def test_summary_lists_each_scenario_and_fails_when_any_run_failed():
    result = {"status": "complete", "summary_path": "/x/eval/results/T/summary.txt", "scenario_results": [
        {"scenario_name": "Trip check", "runs_total": 2, "runs_passed": 2, "runs_errored": 0},
        {"scenario_name": "Dashboard link", "runs_total": 2, "runs_passed": 1, "runs_errored": 0}]}
    text, code = evals.summarize(result)
    assert "✓ Trip check  2/2" in text and "✗ Dashboard link  1/2" in text
    assert "/x/eval/results/T" in text and code == 1


def test_summary_passes_when_every_run_passed():
    result = {"status": "complete", "summary_path": "/x/summary.txt",
              "scenario_results": [{"scenario_name": "Trip check", "runs_total": 1, "runs_passed": 1, "runs_errored": 0}]}
    assert evals.summarize(result)[1] == 0


def test_summary_reports_a_failed_batch():
    text, code = evals.summarize({"success": False, "error": "No running assistant at http://localhost:5006"})
    assert "No running assistant" in text and code == 1


def test_targets_are_the_foreman_and_the_latest_agent():
    assert evals.TARGETS["foreman"][1] == "http://localhost:5005"
    assert evals.TARGETS["agent"][0].name == "latest-agent" and evals.TARGETS["agent"][1] == "http://localhost:5006"


def test_cli_rejects_an_unknown_target():
    with pytest.raises(SystemExit):
        main(["eval", "dashboard"])


def test_the_agent_template_ships_evals():
    template = Path(__file__).resolve().parents[2] / "templates" / "mantle_agent" / "eval"
    assert (template / "conftest.yml").exists() and list((template / "scenarios").glob("*.yml"))
