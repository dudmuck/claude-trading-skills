"""Tests for scripts/backfill_unit_tests_evidence.py (issue #496 step 1 collector)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "backfill_unit_tests_evidence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backfill_unit_tests_evidence", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def collector():
    return load_module()


def stub_rows(monkeypatch, run_exit: int = 0):
    module = load_module()
    monkeypatch.setattr(
        module,
        "run_row",
        lambda entry_id, check_only=False: {
            "install_exit": 0,
            "run_exit": run_exit,
            "recorded_command": f"stub {entry_id}",
        },
    )
    monkeypatch.setattr(
        module,
        "repo_scripts_row_check",
        lambda: {"repo_scripts_row_present": True, "repo_scripts_row": {"run_exit": 0}},
    )
    return module


def run(mod, argv, output_dir: Path):
    assert mod.main([*argv, "--output-dir", str(output_dir)]) == 0
    return json.loads((output_dir / "unit_tests_evidence.json").read_text(encoding="utf-8"))


def test_script_modules_are_reusable(collector):
    assert callable(collector.load_index)
    assert callable(collector.executable_scripts)
    assert callable(collector.propose_mapping)
    assert callable(collector.signals)
    assert callable(collector.run_row)


def test_load_index_returns_production_skills(collector):
    production = collector.load_index(ROOT / "skills-index.yaml")
    assert len(production) >= 59
    assert all(item.get("status") == "production" for item in production)
    ids = {str(item["id"]) for item in production}
    assert "position-sizer" in ids
    assert "market-news-analyst" in ids


def test_executable_scripts_matches_ci_matrix_rule(collector):
    scripts = collector.executable_scripts(ROOT / "skills" / "position-sizer")
    assert scripts, "position-sizer ships executable scripts"
    assert all(p.name != "__init__.py" for p in scripts)
    assert all("tests" not in p.relative_to(ROOT).parts for p in scripts)
    assert any(p.name == "position_sizer.py" for p in scripts)


def test_propose_mapping_reports_unmatched(collector, tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "tool.py"
    script.write_text("def main():\n    return 0\n")

    tests_dir = scripts_dir / "tests"
    tests_dir.mkdir()
    matched = tests_dir / "test_tool.py"
    matched.write_text("import tool\n")
    unrelated = tests_dir / "test_other.py"
    unrelated.write_text("import other_module\n")

    mapping, unmatched = collector.propose_mapping(
        [script], {"skill_local": [matched, unrelated], "repo_level": []}
    )
    assert unmatched == []
    assert mapping == {collector.rel_root(script): [collector.rel_root(matched)]}


def test_propose_mapping_flags_missing_mapping(collector, tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "orphan.py"
    script.write_text("def main():\n    return 0\n")
    mapping, unmatched = collector.propose_mapping([script], {"skill_local": [], "repo_level": []})
    assert mapping == {}
    assert unmatched == [script.as_posix()]


def test_signals_reject_when_no_schema_or_failopen_evidence(collector, tmp_path: Path):
    plain = tmp_path / "test_plain.py"
    plain.write_text("def test_happy():\n    assert True\n")
    sig, sources = collector.signals([plain], [])
    assert sig["schema_conformance_signal"] is False
    assert sig["fail_closed_signal"] is False
    assert sig["signal_sources_schema"] == "none"
    assert sources == []


def test_signals_ignore_conftest(collector, tmp_path: Path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        "def test_schema():\n"
        "    with pytest.raises(ValueError):\n"
        "        invalid()\n"
        "    assert required_keys\n"
    )
    sig, sources = collector.signals([conftest], [])
    assert sig["schema_conformance_signal"] is False
    assert sig["fail_closed_signal"] is False
    assert sources == []


def test_signals_accept_schema_and_failopen_evidence(collector, tmp_path: Path):
    rich = tmp_path / "test_rich.py"
    rich.write_text(
        "def test_error():\n"
        "    with pytest.raises(ValueError):\n"
        "        invalid_input()\n"
        "def test_schema():\n"
        "    assert required_keys.issubset(result)\n"
    )
    sig, sources = collector.signals([rich], [])
    assert sig["schema_conformance_signal"] is True
    assert sig["fail_closed_signal"] is True
    assert sig["schema_conformance_confirmed_by_reviewer"] is False
    assert sig["fixture_type_signal"] == "not_assessed"
    assert sig["signal_sources_fail_closed"].endswith("test_rich.py")
    assert sig["signal_sources_schema"].endswith("test_rich.py")


def test_signals_skip_docstring_only_schema_mention(collector, tmp_path: Path):
    docstring = tmp_path / "test_docstring.py"
    docstring.write_text('"""Read the company-screener schema."""\n')
    sig, sources = collector.signals([docstring], [])
    assert sig["schema_conformance_signal"] is False
    assert sources == []


def test_signals_accept_exit_code_error_paths(collector, tmp_path: Path):
    cli_fail = tmp_path / "test_cli_fail.py"
    cli_fail.write_text('def test_error():\n    assert proc.returncode == 2, "must fail closed"\n')
    sig, sources = collector.signals([cli_fail], [])
    assert sig["fail_closed_signal"] is True
    assert sources == [cli_fail.as_posix()]


def test_main_writes_structured_report(tmp_path: Path, monkeypatch):
    mod = stub_rows(monkeypatch)
    report = run(mod, ["--skip-run"], tmp_path / "reports")
    assert report["issue"].endswith("issues/496")
    assert report["results"], "expected non-empty production skill collection"
    for item in report["results"]:
        assert item["proposed_value"] in {"passed", "gap", "not_applicable"}
        if item["proposed_value"] == "gap":
            assert item["gap_reasons"]


def test_main_skips_row_execution_for_script_free_skill(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def fake_run_row(entry_id, check_only=False):
        calls.append(entry_id)
        return {"install_exit": 0, "run_exit": 0, "recorded_command": f"stub {entry_id}"}

    mod = load_module()
    monkeypatch.setattr(mod, "run_row", fake_run_row)
    monkeypatch.setattr(mod, "repo_scripts_row_check", lambda: {"repo_scripts_row_present": True})
    report = run(mod, ["--skill", "us-stock-analysis"], tmp_path / "reports")
    item = report["results"][0]
    assert item["proposed_value"] == "not_applicable"
    assert calls == [], "no rows should execute for a script-free skill"


def test_main_respects_skill_filter(tmp_path: Path, monkeypatch):
    mod = stub_rows(monkeypatch)
    report = run(mod, ["--skill", "position-sizer", "--skip-run"], tmp_path / "reports_filter")
    assert [item["skill_id"] for item in report["results"]] == ["position-sizer"]
    assert report["results"][0]["current_value"] in {"not_verified", "passed"}


def test_main_runs_recorded_row_and_cites_it(tmp_path: Path, monkeypatch):
    mod = stub_rows(monkeypatch)
    report = run(mod, ["--skill", "position-sizer"], tmp_path / "reports_run")
    item = report["results"][0]
    assert item["row_execution"]["run_exit"] == 0
    assert item["row_execution"]["recorded_command"].endswith("position-sizer")
    assert item["row_execution"]["install_exit"] == 0


def test_main_marks_gap_when_row_fails(tmp_path: Path, monkeypatch):
    mod = stub_rows(monkeypatch, run_exit=1)
    report = run(mod, ["--skill", "position-sizer"], tmp_path / "reports_fail")
    item = report["results"][0]
    assert item["proposed_value"] == "gap"
    assert any("did not exit 0" in reason for reason in item["gap_reasons"])


def test_fresh_module_reports_baseline_rationale_untruncated():
    """Regression guard: YAML '#...' comment truncation must not swallow rationale text."""
    yaml = pytest.importorskip("yaml")
    baseline = yaml.safe_load(
        (ROOT / "docs" / "dev" / "production-verification-baseline.yaml").read_text(
            encoding="utf-8"
        )
    )
    passed_overrides = [
        entry
        for entry in baseline["skills"]
        if isinstance(entry.get("overrides", {}).get("unit_tests"), dict)
        and entry["overrides"]["unit_tests"].get("value") == "passed"
    ]
    assert 10 <= len(passed_overrides) <= 20
    for entry in passed_overrides:
        override = entry["overrides"]["unit_tests"]
        assert len(override.get("rationale", "")) > 50, entry["id"]
        starts = (
            "Single executable script",
            "Plan output",
            "Produced",
            "Ticket payload",
            "thesis.schema.json",
            "E2E orchestrates",
            "E2E asserts",
            "build_run_context",
            "CLI e2e asserts",
            "TestOutput",
        )
        assert override["rationale"].startswith(starts), entry["id"]
        assert "schema" in override["rationale"] or "JSON" in override["rationale"], entry["id"]
        evidence_values = [str(value) for item in override["evidence"] for value in item.values()]
        assert evidence_values, entry["id"]


def test_main_skips_repo_row_without_repo_level_mapping(tmp_path: Path, monkeypatch):
    repo_calls: list[str] = []

    def fake_repo_row():
        repo_calls.append("repo-scripts")
        return {"run_exit": 0, "recorded_command": "stub repo-scripts"}

    mod = load_module()
    monkeypatch.setattr(mod, "repo_scripts_row_check", fake_repo_row)
    monkeypatch.setattr(
        mod,
        "run_row",
        lambda entry_id, check_only=False: {
            "install_exit": 0,
            "run_exit": 0,
            "recorded_command": f"stub {entry_id}",
        },
    )
    monkeypatch.setattr(
        mod,
        "propose_mapping",
        lambda scripts, locations: (
            {f"{scripts[0]}x": []},
            [],
        ),
    )
    run(mod, ["--skill", "position-sizer"], tmp_path / "reports_no_repo")
    assert repo_calls == [], "repo-scripts row must not run when mapping has no repo-level tests"


@pytest.mark.parametrize(
    ("skill_result", "repo_result", "expected_gap"),
    [
        ({"install_exit": 1, "run_exit": 0}, {"install_exit": 0, "run_exit": 0}, True),
        ({"install_exit": 0, "run_exit": 0}, {"install_exit": 1, "run_exit": 0}, True),
        ({"install_exit": 0, "run_exit": 0}, {"install_exit": 0, "run_exit": 1}, True),
        ({"install_exit": 0, "run_exit": 0}, {}, True),
        ({"run_exit": 0}, {"install_exit": 0, "run_exit": 0}, True),
        ({"install_exit": 0, "run_exit": 0}, {"install_exit": 0, "run_exit": 0}, False),
    ],
)
def test_proposal_requires_successful_install_and_all_mapped_rows(
    tmp_path, monkeypatch, skill_result, repo_result, expected_gap
):
    mod = load_module()
    monkeypatch.setattr(mod, "run_row", lambda *a, **k: dict(skill_result))
    monkeypatch.setattr(mod, "repo_scripts_row_check", lambda: dict(repo_result))
    monkeypatch.setattr(
        mod,
        "propose_mapping",
        lambda scripts, locations: (
            {str(scripts[0]): ["scripts/tests/test_provider_contracts.py"]},
            [],
        ),
    )
    monkeypatch.setattr(
        mod,
        "signals",
        lambda *a, **k: ({"fail_closed_signal": True, "schema_conformance_signal": True}, []),
    )
    item = run(mod, ["--skill", "position-sizer"], tmp_path / "report")["results"][0]
    assert item["proposed_value"] == ("gap" if expected_gap else "passed")
    assert bool(item["gap_reasons"]) == expected_gap


def test_run_row_stops_after_install_failure(tmp_path, monkeypatch):
    mod = load_module()
    calls = []

    def failed_install(cmd, **kwargs):
        calls.append(cmd)
        return mod.subprocess.CompletedProcess(cmd, 1, "", "install failed")

    monkeypatch.setattr(mod.subprocess, "run", failed_install)
    result = mod.run_row("position-sizer")
    assert len(calls) == 1
    assert result["install_exit"] == 1
    assert result["run_exit"] is None
    assert "; exit" not in result["recorded_command"]


def test_run_row_records_actual_check_command(monkeypatch):
    mod = load_module()
    calls = []

    def success(cmd, **kwargs):
        calls.append(cmd)
        return mod.subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(mod.subprocess, "run", success)
    result = mod.run_row("repo-scripts", check_only=True)
    assert len(calls) == 2
    assert "--check &&" in result["recorded_command"]
    assert "; exit" not in result["recorded_command"]
