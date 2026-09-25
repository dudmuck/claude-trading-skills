"""The earnings fetcher's bulk-screener path and its per-symbol fallback.

`/stable/profile` costs one HTTP request per symbol, which made this script the
weekly pipeline's long pole (~2 min for 318 symbols; ~15 min in peak season).
`/stable/company-screener` returns the same fields for every US company above a
market-cap threshold in one request. These tests pin the two properties that
make the swap safe: the fallback still exists, and a response that might be
truncated is refused rather than silently dropping names.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FETCHERS = {
    "pipeline": ROOT / "examples/weekly-trade-strategy/skills/earnings-calendar/scripts/fetch_earnings_fmp.py",
    "skill": ROOT / "skills/earnings-calendar/scripts/fetch_earnings_fmp.py",
}


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"fetch_earnings_{path.parent.parent.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=sorted(FETCHERS), ids=sorted(FETCHERS))
def module(request):
    return _load(FETCHERS[request.param])


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_empty_screener_falls_back_to_per_symbol(module):
    client = module.FMPEarningsCalendar("dummy")
    with patch.object(client, "_fetch_profiles_bulk", return_value={}), patch.object(
        client, "_fetch_profiles_per_symbol", return_value={"AAPL": {"symbol": "AAPL"}}
    ) as per_symbol:
        assert client.fetch_company_profiles(["AAPL"]) == {"AAPL": {"symbol": "AAPL"}}
    assert per_symbol.called


def test_working_screener_never_touches_the_per_symbol_loop(module):
    client = module.FMPEarningsCalendar("dummy")
    with patch.object(
        client, "_fetch_profiles_bulk", return_value={"AAPL": {"symbol": "AAPL"}}
    ), patch.object(client, "_fetch_profiles_per_symbol") as per_symbol:
        client.fetch_company_profiles(["AAPL"])
    assert not per_symbol.called, "the point of the screener is to avoid N requests"


def test_response_at_the_row_limit_is_refused_as_possibly_truncated(module):
    """A truncated screener drops real names silently; fall back instead."""
    client = module.FMPEarningsCalendar("dummy")
    limit = module.FMPEarningsCalendar.SCREENER_ROW_LIMIT
    rows = [{"symbol": f"S{i}", "marketCap": 3_000_000_000} for i in range(limit)]
    with patch.object(module.requests, "get", return_value=_Response(rows)):
        assert client._fetch_profiles_bulk(["S1"]) == {}


def test_short_exchange_code_is_what_reaches_the_us_exchange_filter(module):
    """filter_by_market_cap matches US_EXCHANGES, which holds SHORT codes.

    /profile returns "NASDAQ"; the screener returns "NASDAQ Global Select" in
    `exchange` and "NASDAQ" in `exchangeShortName`. Taking the wrong one would
    filter out every US name.
    """
    client = module.FMPEarningsCalendar("dummy")
    rows = [
        {
            "symbol": "AAPL",
            "marketCap": 4_000_000_000_000,
            "companyName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NASDAQ Global Select",
            "exchangeShortName": "NASDAQ",
        }
    ]
    with patch.object(module.requests, "get", return_value=_Response(rows)):
        profiles = client._fetch_profiles_bulk(["AAPL"])
    assert profiles["AAPL"]["exchange"] == "NASDAQ"
    assert profiles["AAPL"]["exchange"] in module.FMPEarningsCalendar.US_EXCHANGES


def test_market_cap_keeps_the_api_numeric_type(module):
    """The per-symbol path emitted ints; the JSON contract should not change."""
    client = module.FMPEarningsCalendar("dummy")
    rows = [{"symbol": "AAPL", "marketCap": 4_000_000_000_000, "exchangeShortName": "NASDAQ"}]
    with patch.object(module.requests, "get", return_value=_Response(rows)):
        profiles = client._fetch_profiles_bulk(["AAPL"])
    assert isinstance(profiles["AAPL"]["marketCap"], int)


def test_symbols_below_the_threshold_are_simply_absent(module):
    """The screener only returns names above MIN_MARKET_CAP.

    A missing profile is exactly what the old path produced for a sub-threshold
    symbol, so filter_by_market_cap drops it unchanged.
    """
    client = module.FMPEarningsCalendar("dummy")
    rows = [{"symbol": "AAPL", "marketCap": 4_000_000_000_000, "exchangeShortName": "NASDAQ"}]
    with patch.object(module.requests, "get", return_value=_Response(rows)):
        profiles = client._fetch_profiles_bulk(["AAPL", "TINYCO"])
    assert "TINYCO" not in profiles


def test_api_key_never_comes_from_argv(module, monkeypatch):
    """argv is world-readable via `ps` for the life of the process."""
    monkeypatch.setattr(
        module.sys, "argv", ["fetch_earnings_fmp.py", "2026-09-28", "2026-10-05", "leaked-key"]
    )
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    assert module.get_api_key() is None

    monkeypatch.setenv("FMP_API_KEY", "env-key")
    assert module.get_api_key() == "env-key"
