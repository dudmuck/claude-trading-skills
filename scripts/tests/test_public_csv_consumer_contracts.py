"""Consumer contract tests for the trader-monty public CSV contracts (Issue #332).

Each test builds CSV text from a recorded contract fixture and feeds it to the
real consumer parser through a mocked HTTP layer (no live calls). Following
the FMP-consumer convention in ``test_provider_contracts.py``, the client
modules are loaded by path here so the skill suites never read ``config/``.

Two properties are pinned:

* the consumer parses the recorded fixture, and
* renaming any required column makes the consumer return an empty result and
  print exactly one ``schema drift: missing columns`` ERROR naming that
  column, with no per-line ``Skipping line`` WARN flood.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.provider_contracts import load_contracts  # noqa: E402

CONTRACTS = load_contracts(REPO_ROOT)
DRIFT = "schema drift: missing columns"


def _load_module(rel_path: str):
    abs_path = REPO_ROOT / rel_path
    skill = abs_path.parent.parent.name.replace("-", "_")
    name = f"_public_csv_contracts_{skill}_{abs_path.stem}"
    sys.modules.pop(name, None)
    sys.path.insert(0, str(abs_path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, str(abs_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(abs_path.parent))


def _csv_text(contract, rename: str | None = None) -> str:
    """Render the contract fixture as CSV text, optionally renaming one column."""
    header = list(contract.fixture[0])
    if rename is not None:
        header = [rename + "_renamed" if column == rename else column for column in header]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in contract.fixture:
        writer.writerow(["" if row[column] is None else row[column] for column in row])
    return buffer.getvalue()


def _response(text: str):
    return SimpleNamespace(text=text, status_code=200, raise_for_status=lambda: None)


@pytest.fixture(scope="module")
def breadth():
    return _load_module("skills/market-breadth-analyzer/scripts/csv_client.py")


@pytest.fixture(scope="module")
def uptrend():
    return _load_module("skills/uptrend-analyzer/scripts/data_fetcher.py")


def _stderr_lines(capsys) -> list[str]:
    return [line for line in capsys.readouterr().err.splitlines() if line.strip()]


def _assert_single_drift_error(lines: list[str], column: str) -> None:
    drift = [line for line in lines if DRIFT in line]
    assert len(drift) == 1, lines
    assert column in drift[0], drift[0]
    assert not any("Skipping line" in line for line in lines), lines
    assert not any("Skipping summary line" in line for line in lines), lines


# --- market-breadth-analyzer (csv_client.py) -------------------------------

BREADTH_DETAIL = CONTRACTS["market-breadth-data"]
BREADTH_SUMMARY = CONTRACTS["market-breadth-summary"]


def _patch_breadth(monkeypatch, breadth, text):
    monkeypatch.setattr(breadth.requests, "get", lambda *a, **k: _response(text))


def test_breadth_detail_parses_fixture(monkeypatch, capsys, breadth):
    _patch_breadth(monkeypatch, breadth, _csv_text(BREADTH_DETAIL))
    rows = breadth.fetch_detail_csv()
    assert len(rows) == len(BREADTH_DETAIL.fixture)
    assert [r["Date"] for r in rows] == sorted(r["Date"] for r in BREADTH_DETAIL.fixture)
    by_date = {r["Date"]: r for r in BREADTH_DETAIL.fixture}
    for row in rows:
        recorded = by_date[row["Date"]]
        assert row["S&P500_Price"] == pytest.approx(recorded["S&P500_Price"])
        assert row["Breadth_200MA_Trend"] == recorded["Breadth_200MA_Trend"]
        assert row["Bearish_Signal"] is recorded["Bearish_Signal"]
    assert DRIFT not in capsys.readouterr().err


@pytest.mark.parametrize("column", sorted(BREADTH_DETAIL.required_fields))
def test_breadth_detail_required_column_rename_is_one_drift_error(
    monkeypatch, capsys, breadth, column
):
    _patch_breadth(monkeypatch, breadth, _csv_text(BREADTH_DETAIL, rename=column))
    assert breadth.fetch_detail_csv() == []
    _assert_single_drift_error(_stderr_lines(capsys), column)


def test_breadth_detail_drift_message_names_file(monkeypatch, capsys, breadth):
    _patch_breadth(monkeypatch, breadth, _csv_text(BREADTH_DETAIL, rename="Date"))
    breadth.fetch_detail_csv()
    assert "ERROR: market_breadth_data.csv schema drift: missing columns" in (
        capsys.readouterr().err
    )


def test_breadth_summary_parses_fixture(monkeypatch, capsys, breadth):
    _patch_breadth(monkeypatch, breadth, _csv_text(BREADTH_SUMMARY))
    summary = breadth.fetch_summary_csv()
    recorded = {r["Metric"]: r["Value"] for r in BREADTH_SUMMARY.fixture}
    assert set(summary) == set(recorded)
    for metric in BREADTH_SUMMARY.required_values["Metric"]:
        assert float(summary[metric]) == pytest.approx(recorded[metric])
    err = capsys.readouterr().err
    assert "missing metric" not in err and DRIFT not in err


@pytest.mark.parametrize("column", sorted(BREADTH_SUMMARY.required_fields))
def test_breadth_summary_required_column_rename_is_one_drift_error(
    monkeypatch, capsys, breadth, column
):
    _patch_breadth(monkeypatch, breadth, _csv_text(BREADTH_SUMMARY, rename=column))
    assert not breadth.fetch_summary_csv()
    _assert_single_drift_error(_stderr_lines(capsys), column)


@pytest.mark.parametrize("metric", BREADTH_SUMMARY.required_values["Metric"])
def test_breadth_summary_missing_metric_warns(monkeypatch, capsys, breadth, metric):
    contract_rows = [r for r in BREADTH_SUMMARY.fixture if r["Metric"] != metric]
    text = "Metric,Value\n" + "".join(f"{r['Metric']},{r['Value']}\n" for r in contract_rows)
    _patch_breadth(monkeypatch, breadth, text)
    summary = breadth.fetch_summary_csv()
    assert metric not in summary
    lines = _stderr_lines(capsys)
    warns = [line for line in lines if "market_breadth_summary.csv missing metric" in line]
    assert len(warns) == 1 and metric in warns[0], lines


# --- uptrend-analyzer (data_fetcher.py) ------------------------------------

UPTREND_TS = CONTRACTS["uptrend-ratio-timeseries"]
UPTREND_SECTOR = CONTRACTS["uptrend-sector-summary"]


def _fetcher(monkeypatch, uptrend, text):
    fetcher = uptrend.UptrendDataFetcher()
    monkeypatch.setattr(fetcher.session, "get", lambda *a, **k: _response(text))
    return fetcher


def test_uptrend_timeseries_parses_fixture(monkeypatch, capsys, uptrend):
    fetcher = _fetcher(monkeypatch, uptrend, _csv_text(UPTREND_TS))
    rows = fetcher.fetch_timeseries()
    assert len(rows) == len(UPTREND_TS.fixture)
    for parsed, recorded in zip(rows, UPTREND_TS.fixture):
        assert parsed["worksheet"] == recorded["worksheet"]
        assert parsed["date"] == recorded["date"]
        assert parsed["count"] == recorded["count"]
        assert parsed["total"] == recorded["total"]
        assert parsed["ratio"] == pytest.approx(recorded["ratio"])
        assert parsed["ma_10"] == (
            pytest.approx(recorded["ma_10"]) if recorded["ma_10"] is not None else None
        )
        assert parsed["slope"] == (
            pytest.approx(recorded["slope"]) if recorded["slope"] is not None else None
        )
    assert any(r["ma_10"] is None for r in rows)
    assert fetcher.get_latest_all() is not None
    assert DRIFT not in capsys.readouterr().err


@pytest.mark.parametrize("column", sorted(UPTREND_TS.required_fields))
def test_uptrend_timeseries_required_column_rename_is_one_drift_error(
    monkeypatch, capsys, uptrend, column
):
    fetcher = _fetcher(monkeypatch, uptrend, _csv_text(UPTREND_TS, rename=column))
    assert fetcher.fetch_timeseries() == []
    _assert_single_drift_error(_stderr_lines(capsys), column)


def test_uptrend_timeseries_drift_message_names_file(monkeypatch, capsys, uptrend):
    fetcher = _fetcher(monkeypatch, uptrend, _csv_text(UPTREND_TS, rename="ratio"))
    fetcher.fetch_timeseries()
    assert "ERROR: uptrend_ratio_timeseries.csv schema drift: missing columns" in (
        capsys.readouterr().err
    )


def test_uptrend_sector_summary_parses_fixture(monkeypatch, capsys, uptrend):
    fetcher = _fetcher(monkeypatch, uptrend, _csv_text(UPTREND_SECTOR))
    rows = fetcher.fetch_sector_summary()
    assert len(rows) == len(UPTREND_SECTOR.fixture)
    for parsed, recorded in zip(rows, UPTREND_SECTOR.fixture):
        assert parsed["Sector"] == recorded["Sector"]
        assert parsed["Ratio"] == pytest.approx(recorded["Ratio"])
        assert parsed["Status"] == recorded["Status"]
    assert DRIFT not in capsys.readouterr().err


@pytest.mark.parametrize("column", sorted(UPTREND_SECTOR.required_fields))
def test_uptrend_sector_summary_required_column_rename_is_one_drift_error(
    monkeypatch, capsys, uptrend, column
):
    fetcher = _fetcher(monkeypatch, uptrend, _csv_text(UPTREND_SECTOR, rename=column))
    assert fetcher.fetch_sector_summary() == []
    _assert_single_drift_error(_stderr_lines(capsys), column)


def test_uptrend_sector_summary_drift_message_names_file(monkeypatch, capsys, uptrend):
    fetcher = _fetcher(monkeypatch, uptrend, _csv_text(UPTREND_SECTOR, rename="Sector"))
    fetcher.fetch_sector_summary()
    assert "ERROR: sector_summary.csv schema drift: missing columns" in capsys.readouterr().err
