"""Smoke tests for the indicator lookup script.

Run with: python3 -m pytest skills/econ-indicator-explainer/scripts/tests/
"""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "lookup_indicator.py"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def test_list_runs():
    r = _run("--list")
    assert r.returncode == 0
    assert "CPI" in r.stdout
    assert "Total:" in r.stdout


def test_exact_canonical():
    r = _run("Core CPI YoY")
    assert r.returncode == 0
    assert "core" in r.stdout.lower()


def test_short_name():
    r = _run("NFP")
    assert r.returncode == 0
    assert "payroll" in r.stdout.lower()


def test_fmp_alias():
    r = _run("Consumer Price Index (CPI) YoY")
    assert r.returncode == 0
    assert "inflation" in r.stdout.lower() or "cpi" in r.stdout.lower()


def test_json_output():
    import json as jsonlib

    r = _run("--json", "FOMC")
    assert r.returncode == 0
    data = jsonlib.loads(r.stdout)
    assert "sections" in data
    assert "canonical" in data


def test_no_match():
    r = _run("nonexistent indicator xyz123")
    assert r.returncode == 2
    assert "No match" in r.stderr
