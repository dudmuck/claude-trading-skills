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


# ─── central-bank disambiguation ─────────────────────────────────────────────
# Generic event wording is told apart only by the issuing bank. "Fed Press
# Conference" shares {press, conference} with the BOJ card's "BoJ Press
# Conference" alias — Jaccard 0.5, over the 0.3 floor — so it matched BOJ and
# shipped a spurious foreign-policy card into the 2026-07-20 and 2026-07-27
# pipeline runs, in weeks with no BOJ meeting. Downstream steps read these cards
# as ground truth, so a wrong card is worse than no card.


def test_fed_press_conference_does_not_match_boj():
    r = _run("Fed Press Conference")
    assert "BOJ" not in r.stdout and "Bank of Japan" not in r.stdout


def test_fed_decision_still_resolves_to_fomc():
    r = _run("Fed Interest Rate Decision")
    assert r.returncode == 0
    assert "FOMC" in r.stdout


def test_fed_and_fomc_are_same_bank_not_exclusive():
    # Same bank identity, so the gate must not fire between them.
    r = _run("FOMC Minutes")
    assert r.returncode == 0
    assert "FOMC" in r.stdout


def test_genuine_boj_queries_still_match():
    for q in ("BOJ Interest Rate Decision", "BoJ Press Conference"):
        r = _run(q)
        assert r.returncode == 0, q
        assert "BOJ" in r.stdout, q


def test_genuine_ecb_query_still_matches():
    r = _run("ECB Interest Rate Decision")
    assert r.returncode == 0
    assert "ECB" in r.stdout


def test_bank_agnostic_cards_are_not_narrowed():
    # A query naming a bank must still reach a card that names none.
    r = _run("Core PCE Price Index MoM")
    assert r.returncode == 0
    assert "PCE" in r.stdout
