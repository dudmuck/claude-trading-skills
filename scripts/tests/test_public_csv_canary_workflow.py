"""Structural tests for the public CSV contract canary workflow (Issue #332).

The workflow probes keyless public CSVs, so unlike the FMP canary it has no
preflight job and must reference no secret at all. Drift stays report-only
(``continue-on-error``) but is surfaced through a step summary and annotations.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "public-csv-contract-canary.yml"
REPO_SLUG = "tradermonty/claude-trading-skills"
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
SYNC = "uv sync --locked --no-install-project --extra dev --extra ci"


@pytest.fixture(scope="module")
def text():
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def config(text):
    return yaml.load(text, Loader=yaml.BaseLoader)


@pytest.fixture(scope="module")
def canary(config):
    return config["jobs"]["canary"]


def test_top_level_permissions_read_only(config):
    assert config["permissions"] == {"contents": "read"}


def test_triggers_weekly_monday_1230_and_dispatch(config):
    on = config["on"]
    assert on["schedule"] == [{"cron": "30 12 * * 1"}]
    assert "workflow_dispatch" in on
    assert set(on) == {"schedule", "workflow_dispatch"}


def test_single_canary_job_with_repository_guard(config, canary):
    assert set(config["jobs"]) == {"canary"}
    assert canary["if"] == f"github.repository == '{REPO_SLUG}'"


def test_canary_is_report_only(canary):
    assert canary["continue-on-error"] == "true"


def test_no_secret_or_expression_in_run_steps(text, canary):
    assert "secrets." not in text
    assert "FMP_API_KEY" not in text
    for step in canary["steps"]:
        assert "${{" not in step.get("run", ""), step.get("name")
        assert "set -x" not in step.get("run", "")


def test_every_uses_is_sha_pinned(canary):
    uses = [s["uses"] for s in canary["steps"] if "uses" in s]
    assert uses
    for item in uses:
        assert SHA_RE.match(item), item


def test_locked_environment_sync(canary):
    sync_steps = [s for s in canary["steps"] if SYNC in s.get("run", "")]
    assert len(sync_steps) == 1
    assert 'echo "$PWD/.venv/bin" >> "$GITHUB_PATH"' in sync_steps[0]["run"]
    uv = [s for s in canary["steps"] if "astral-sh/setup-uv@" in s.get("uses", "")]
    assert len(uv) == 1 and uv[0]["with"]["version"] == "0.12.10"


def test_canary_step_probes_trader_monty_only(canary):
    runs = [
        s["run"]
        for s in canary["steps"]
        if "check_provider_contracts.py canary" in s.get("run", "")
    ]
    assert len(runs) == 1
    assert "--provider trader-monty" in runs[0]
    assert "reports/public-csv-canary-report.json" in runs[0]


def test_summarize_step_runs_always_with_fallback(canary):
    steps = [
        s for s in canary["steps"] if "check_provider_contracts.py summarize" in s.get("run", "")
    ]
    assert len(steps) == 1
    step = steps[0]
    assert step["if"] == "always()"
    assert "--provider trader-monty" in step["run"]
    assert "reports/public-csv-canary-report.json" in step["run"]
    assert '--summary-file "$GITHUB_STEP_SUMMARY"' in step["run"]
    assert "--github" in step["run"]
    assert "::error title=Public CSV canary summarize failed::" in step["run"]


def test_upload_step_runs_always_for_30_days(canary):
    uploads = [s for s in canary["steps"] if "upload-artifact" in s.get("uses", "")]
    assert len(uploads) == 1
    step = uploads[0]
    assert step["if"] == "always()"
    assert step["with"]["path"] == "reports/public-csv-canary-report.json"
    assert step["with"]["retention-days"] == "30"


def test_canary_does_not_touch_fmp_workflow_state(text):
    assert "financialmodelingprep" not in text.lower()
    assert "preflight" not in text.replace("# ", "").split("jobs:")[1]
