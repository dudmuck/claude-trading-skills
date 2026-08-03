"""Tests for analyze_gex.py — OCC parsing, signed GEX aggregation, walls, flip, max pain.

All tests run offline against a saved CBOE JSON fixture (fixtures/cboe_ztest.json).
The fixture is hand-built with round numbers (spot=100, so spot^2=10000) so every
aggregate is exactly hand-computable:

  Call $-gamma/1% (OI*gamma*10000) : 95->300k 100->600k 105->700k(600k+100k) 110->900k
  Put  $-gamma/1% (magnitude)      : 90->155k(80k+75k) 95->100k 100->120k
  call_total=2,500,000  put_total=375,000
  net (A) = +2,125,000  gross (B) = +2,875,000
"""

import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from analyze_gex import (
    aggregate_gex,
    analyze,
    atm_iv_pct,
    classify_regime,
    compute_max_pain,
    dollar_gamma_1pct,
    expiry_to_date,
    extract_spot,
    filter_by_dte,
    find_call_wall,
    find_gamma_flip,
    find_put_wall,
    generate_markdown_report,
    oi_stats,
    parse_occ,
    report_to_dict,
    rows_from_cboe,
    underlying_for,
    window_slug,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cboe_ztest.json"


@pytest.fixture
def payload():
    with open(FIXTURE) as f:
        return json.load(f)


# ─── OCC symbol parsing ──────────────────────────────────────────────────────


class TestParseOcc:
    def test_call_symbol(self):
        root, ymd, is_call, strike = parse_occ("ZTEST260116C00105000")
        assert root == "ZTEST"
        assert ymd == "260116"
        assert is_call is True
        assert strike == 105.0

    def test_put_symbol(self):
        root, ymd, is_call, strike = parse_occ("ZTEST260220P00090000")
        assert is_call is False
        assert strike == 90.0
        assert ymd == "260220"

    def test_index_root_with_underscore(self):
        parsed = parse_occ("_SPX260116C05000000")
        assert parsed is not None
        assert parsed[0] == "_SPX"
        assert parsed[3] == 5000.0  # 05000000 / 1000

    def test_fractional_strike(self):
        # 00092500 / 1000 = 92.5
        assert parse_occ("ABC260116C00092500")[3] == 92.5

    def test_garbage_returns_none(self):
        assert parse_occ("NOTASYMBOL") is None
        assert parse_occ("") is None
        assert parse_occ(None) is None


# ─── Index-underlying ticker mapping ─────────────────────────────────────────


class TestUnderlyingFor:
    def test_index_alias(self):
        assert underlying_for("SPX") == "_SPX"
        assert underlying_for("SP500") == "_SPX"
        assert underlying_for("NDX") == "_NDX"
        assert underlying_for("RUT") == "_RUT"
        assert underlying_for("VIX") == "_VIX"

    def test_equity_passthrough(self):
        assert underlying_for("NVDA") == "NVDA"
        assert underlying_for("aapl") == "AAPL"

    def test_strips_caret_and_dollar(self):
        assert underlying_for("^SPX") == "_SPX"
        assert underlying_for("$NDX") == "_NDX"

    def test_already_prefixed_passthrough(self):
        assert underlying_for("_SPX") == "_SPX"


# ─── Payload parsing ─────────────────────────────────────────────────────────


class TestRowsFromCboe:
    def test_spot_and_count(self, payload):
        spot, rows = rows_from_cboe(payload)
        assert spot == 100.0
        assert len(rows) == 9

    def test_call_put_split(self, payload):
        _spot, rows = rows_from_cboe(payload)
        assert sum(1 for r in rows if r.is_call) == 5
        assert sum(1 for r in rows if not r.is_call) == 4

    def test_falls_back_to_close(self):
        spot, _rows = rows_from_cboe({"data": {"close": 42.0, "options": []}})
        assert spot == 42.0


# ─── Dollar gamma primitive ──────────────────────────────────────────────────


class TestDollarGamma:
    def test_multiplier_and_pct_cancel(self):
        # OI * gamma * spot^2 ; spot=100 -> 1000 * 0.03 * 10000 = 300,000
        assert dollar_gamma_1pct(0.03, 1000, 100.0) == 300_000.0


# ─── Signed aggregation ──────────────────────────────────────────────────────


class TestAggregate:
    def test_totals(self, payload):
        spot, rows = rows_from_cboe(payload)
        agg = aggregate_gex(rows, spot)
        assert agg["call_total"] == pytest.approx(2_500_000.0)
        assert agg["put_total"] == pytest.approx(375_000.0)
        assert agg["net_total"] == pytest.approx(2_125_000.0)
        assert agg["gross_total"] == pytest.approx(2_875_000.0)

    def test_per_strike_call_gamma(self, payload):
        spot, rows = rows_from_cboe(payload)
        agg = aggregate_gex(rows, spot)
        assert agg["call_gex"][105.0] == pytest.approx(700_000.0)  # 600k Jan + 100k Feb
        assert agg["call_gex"][110.0] == pytest.approx(900_000.0)

    def test_per_strike_put_gamma_is_magnitude(self, payload):
        spot, rows = rows_from_cboe(payload)
        agg = aggregate_gex(rows, spot)
        assert agg["put_gex"][90.0] == pytest.approx(155_000.0)  # 80k Jan + 75k Feb

    def test_net_by_strike_sign(self, payload):
        spot, rows = rows_from_cboe(payload)
        agg = aggregate_gex(rows, spot)
        assert agg["net_by_strike"][90.0] == pytest.approx(-155_000.0)  # pure put
        assert agg["net_by_strike"][110.0] == pytest.approx(900_000.0)  # pure call


# ─── Walls, flip, max pain ───────────────────────────────────────────────────


class TestLevels:
    def test_call_wall(self, payload):
        spot, rows = rows_from_cboe(payload)
        agg = aggregate_gex(rows, spot)
        assert find_call_wall(agg["call_gex"], spot) == 110.0  # biggest call gamma >= spot

    def test_put_wall(self, payload):
        spot, rows = rows_from_cboe(payload)
        agg = aggregate_gex(rows, spot)
        assert find_put_wall(agg["put_gex"], spot) == 90.0  # biggest put gamma <= spot

    def test_gamma_flip(self, payload):
        spot, rows = rows_from_cboe(payload)
        agg = aggregate_gex(rows, spot)
        # cum net: 90 -155k, 95 +45k -> crosses zero at 95
        assert find_gamma_flip(agg["net_by_strike"]) == 95.0

    def test_gamma_flip_none_when_no_sign_change(self):
        # All-negative net gamma (only puts): cumulative never crosses zero.
        assert find_gamma_flip({90.0: -100.0, 95.0: -50.0}) is None

    def test_max_pain_nearest_expiry(self, payload):
        _spot, rows = rows_from_cboe(payload)
        # Nearest expiry 260116; hand-computed minimum holder value at strike 95.
        assert compute_max_pain(rows, nearest_expiry_only=True) == 95.0

    def test_max_pain_empty(self):
        assert compute_max_pain([]) is None


# ─── Risk indicators ─────────────────────────────────────────────────────────


class TestRiskIndicators:
    def test_oi_ratio(self, payload):
        _spot, rows = rows_from_cboe(payload)
        call_oi, put_oi, ratio = oi_stats(rows)
        assert call_oi == 8000  # 1000+1500+2000+3000+500
        assert put_oi == 1600  # 400+400+300+500
        assert ratio == 5.0

    def test_atm_iv(self, payload):
        spot, rows = rows_from_cboe(payload)
        # ATM strike = 100 (nearest expiry); mean(call 0.28, put 0.30) = 0.29 -> 29.0%
        assert atm_iv_pct(rows, spot) == 29.0


# ─── Regime classification ───────────────────────────────────────────────────


class TestRegime:
    def test_positive(self):
        assert classify_regime(1_000_000) == "positive_gamma"
        assert classify_regime(0) == "positive_gamma"

    def test_negative(self):
        assert classify_regime(-500_000) == "negative_gamma"

    def test_fixture_regime_positive(self, payload):
        rep = analyze(payload)
        assert rep.regime == "positive_gamma"  # net +2.125M


# ─── End-to-end analyze() ────────────────────────────────────────────────────


class TestAnalyze:
    def test_full_report_values(self, payload):
        rep = analyze(payload)
        assert rep.ticker == "ZTEST"
        assert rep.spot == 100.0
        assert rep.net_gex_mm == pytest.approx(2.125)
        assert rep.gross_hedge_mm == pytest.approx(2.875)
        assert rep.call_wall == 110.0
        assert rep.put_wall == 90.0
        assert rep.gamma_flip == 95.0
        assert rep.max_pain == 95.0
        assert rep.call_put_oi_ratio == 5.0
        assert rep.atm_iv_pct == 29.0
        assert rep.n_contracts == 9

    def test_magnet_strikes_ranked(self, payload):
        rep = analyze(payload, top_n_magnets=3)
        strikes = [m["strike"] for m in rep.magnets]
        # |net|: 110(900k) 105(700k) 100(480k) 95(200k) 90(155k)
        assert strikes == [110.0, 105.0, 100.0]

    def test_ticker_override(self, payload):
        rep = analyze(payload, ticker="_SPX")
        assert rep.ticker == "_SPX"

    def test_empty_payload_unknown(self):
        rep = analyze({"data": {"current_price": 0, "options": []}})
        assert rep.regime == "unknown"
        assert rep.net_gex_mm == 0.0

    def test_report_dict_serializable(self, payload):
        d = report_to_dict(analyze(payload))
        # Round-trips through JSON without error.
        parsed = json.loads(json.dumps(d))
        assert parsed["schema_version"] == "1.0"
        sr = parsed["support_resistance"]
        assert sr["resistance_call_wall"] == 110.0
        assert sr["support_put_wall"] == 90.0
        assert sr["gamma_flip"] == 95.0
        # % from spot signs: call wall above (+), put wall below (-)
        assert sr["resistance_call_wall_pct_from_spot"] == 10.0
        assert sr["support_put_wall_pct_from_spot"] == -10.0

    def test_markdown_has_sr_and_regime(self, payload):
        md = generate_markdown_report(analyze(payload))
        assert "# Dealer Gamma (GEX) Analysis — ZTEST" in md
        assert "Support / Resistance Map" in md
        assert "Call Wall" in md
        assert "Put Wall" in md
        assert "Max Pain" in md
        assert "PIN" in md  # positive-gamma regime label


# ─── CLI (offline via --payload-json) ────────────────────────────────────────


class TestCli:
    def test_cli_offline(self):
        repo_root = Path(__file__).resolve().parents[4]
        script = "skills/dealer-gamma-analyzer/scripts/analyze_gex.py"
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    script,
                    "ZTEST",
                    "--payload-json",
                    str(FIXTURE),
                    "--output-dir",
                    tmp,
                ],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )
            assert result.returncode == 0, result.stderr
            assert "regime positive_gamma" in result.stdout
            outputs = list(Path(tmp).glob("dealer_gex_ZTEST_*"))
            assert any(p.suffix == ".json" for p in outputs)
            assert any(p.suffix == ".md" for p in outputs)

    def test_cli_bad_payload_path(self):
        repo_root = Path(__file__).resolve().parents[4]
        script = "skills/dealer-gamma-analyzer/scripts/analyze_gex.py"
        result = subprocess.run(
            [sys.executable, script, "ZTEST", "--payload-json", "/no/such/file.json"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert result.returncode == 1
        assert "Error" in result.stderr


class TestDteWindow:
    """Fork-local --min-dte/--max-dte expiry filter.

    The fixture carries two expiries: 260116 (7 contracts) and 260220 (2).
    With as_of=2026-01-01 that is DTE 15 and DTE 50.
    """

    AS_OF = date(2026, 1, 1)

    def _rows(self):
        payload = json.loads(FIXTURE.read_text())
        _spot, rows = rows_from_cboe(payload)
        return rows

    def test_expiry_to_date_parses_occ_yymmdd(self):
        assert expiry_to_date("260116") == date(2026, 1, 16)

    @pytest.mark.parametrize("bad", ["", "26011", "261332", "notadate", None])
    def test_expiry_to_date_rejects_malformed(self, bad):
        assert expiry_to_date(bad) is None

    def test_no_bounds_keeps_everything(self):
        rows = self._rows()
        assert len(filter_by_dte(rows, self.AS_OF)) == len(rows) == 9

    def test_max_dte_keeps_only_near_expiry(self):
        kept = filter_by_dte(self._rows(), self.AS_OF, max_dte=20)
        assert len(kept) == 7
        assert {r.expiry for r in kept} == {"260116"}

    def test_min_dte_keeps_only_far_expiry(self):
        kept = filter_by_dte(self._rows(), self.AS_OF, min_dte=20)
        assert len(kept) == 2
        assert {r.expiry for r in kept} == {"260220"}

    def test_bounds_are_inclusive_on_both_ends(self):
        # DTE 15 and 50 exactly — both must survive their own boundary.
        assert len(filter_by_dte(self._rows(), self.AS_OF, min_dte=15, max_dte=50)) == 9
        assert len(filter_by_dte(self._rows(), self.AS_OF, min_dte=16, max_dte=49)) == 0

    def test_unparseable_expiry_dropped_when_bounded(self):
        rows = self._rows()
        rows[0] = replace(rows[0], expiry="garbg")
        # Dropped, not silently treated as 0DTE and leaked into the window.
        assert len(filter_by_dte(rows, self.AS_OF, max_dte=20)) == 6

    def test_analyze_records_the_window(self):
        payload = json.loads(FIXTURE.read_text())
        rep = analyze(payload, ticker="ZTEST", min_dte=20, as_of=self.AS_OF)
        assert rep.dte_window == {
            "min_dte": 20,
            "max_dte": None,
            "as_of": "2026-01-01",
            "contracts_kept": 2,
            "contracts_dropped": 7,
        }
        assert rep.n_contracts == 2

    def test_analyze_unbounded_leaves_window_none(self):
        rep = analyze(json.loads(FIXTURE.read_text()), ticker="ZTEST")
        assert rep.dte_window is None
        assert "entire chain" in generate_markdown_report(rep)

    def test_windowed_report_states_the_window(self):
        rep = analyze(json.loads(FIXTURE.read_text()), ticker="ZTEST", max_dte=20, as_of=self.AS_OF)
        md = generate_markdown_report(rep)
        assert "DTE 0-20 as of 2026-01-01" in md
        assert "7 contracts kept" in md
        assert report_to_dict(rep)["dte_window"]["contracts_kept"] == 7

    def test_window_that_excludes_everything_fails_loudly(self):
        rep = analyze(
            json.loads(FIXTURE.read_text()), ticker="ZTEST", min_dte=999, as_of=self.AS_OF
        )
        assert rep.regime == "unknown"
        assert "widen" in rep.note

    def test_cli_rejects_inverted_window(self):
        repo_root = Path(__file__).resolve().parents[4]
        result = subprocess.run(
            [
                sys.executable,
                "skills/dealer-gamma-analyzer/scripts/analyze_gex.py",
                "ZTEST",
                "--payload-json",
                str(FIXTURE),
                "--min-dte",
                "40",
                "--max-dte",
                "10",
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert result.returncode == 1
        assert "empty window" in result.stderr

    def test_cli_rejects_bad_as_of(self):
        repo_root = Path(__file__).resolve().parents[4]
        result = subprocess.run(
            [
                sys.executable,
                "skills/dealer-gamma-analyzer/scripts/analyze_gex.py",
                "ZTEST",
                "--payload-json",
                str(FIXTURE),
                "--as-of",
                "07/25/2026",
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert result.returncode == 1
        assert "YYYY-MM-DD" in result.stderr


class TestWindowSlug:
    """Two windows on one symbol must not collide.

    The timestamp is second-resolution, so a near-window and a structural-window
    run landing in the same second wrote the same path and the second silently
    clobbered the first (observed 2026-07-26: the whole 0-7 DTE half of a pipeline
    overlay vanished with no error).
    """

    def test_unbounded_keeps_the_plain_name(self):
        assert window_slug(None, None) == ""

    def test_both_bounds(self):
        assert window_slug(21, 45) == "_dte21-45"

    def test_max_only_is_anchored_at_zero(self):
        assert window_slug(None, 7) == "_dte0-7"

    def test_min_only(self):
        assert window_slug(30, None) == "_dte30plus"

    def test_the_two_pipeline_windows_differ(self):
        assert window_slug(None, 7) != window_slug(21, 45)

    def test_slug_is_filename_safe(self):
        for slug in (window_slug(None, 7), window_slug(21, 45), window_slug(30, None)):
            assert all(ch.isalnum() or ch in "_-" for ch in slug), slug

    def test_cli_writes_distinct_files_for_two_windows(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[4]
        script = "skills/dealer-gamma-analyzer/scripts/analyze_gex.py"
        for args in (["--max-dte", "400"], ["--min-dte", "1", "--max-dte", "400"]):
            r = subprocess.run(
                [
                    sys.executable,
                    script,
                    "ZTEST",
                    "--payload-json",
                    str(FIXTURE),
                    "--as-of",
                    "2026-01-01",
                    "--output-dir",
                    str(tmp_path),
                    *args,
                ],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
            )
            assert r.returncode == 0, r.stderr
        mds = sorted(p.name for p in tmp_path.glob("*.md"))
        assert len(mds) == 2, mds  # would be 1 before the slug existed
        assert any("_dte0-400_" in n for n in mds)
        assert any("_dte1-400_" in n for n in mds)


# ─── Spot source selection (fork-local) ──────────────────────────────────────


class TestSpotSource:
    """CBOE ships two prices. Picking the wrong one silently mislabels the close.

    `current_price` is QUOTE-derived, so after hours it is a post-market quote
    rather than the closing trade. `close` is the last consolidated TRADE, which
    once a session ends is that session's closing trade. `prev_day_close` — NOT
    `close` — carries the prior session. Rule: prefer `close` when --as-of is
    set, because that flag already means "analyze a completed session".

    Measured directly on the live QQQ payload:
        2026-08-02 (closed)  current_price 684.47 (== ask) / close 687.99
        2026-08-03 (open)    current_price 701.08 (~ quote) / close 700.07
                             prev_day_close 687.99 in BOTH
    The 684.47 propagated into the weekly pipeline as "QQQ Friday close" and
    produced a "+0.02% flat week" reading; the true week was +0.55%.
    """

    QQQ = {
        "data": {
            "symbol": "QQQ",
            "current_price": 684.47,
            "close": 687.99,
            "prev_day_close": 687.99,
            "options": [],
        }
    }

    def test_default_prefers_current_price(self):
        """Unchanged default — live/intraday runs must keep using current_price."""
        spot, _ = rows_from_cboe(self.QQQ)
        assert spot == 684.47

    def test_prefer_session_close_picks_close(self):
        spot, _ = rows_from_cboe(self.QQQ, prefer_session_close=True)
        assert spot == 687.99

    def test_prefer_session_close_falls_back_when_close_absent(self):
        """A payload with no `close` must not yield spot=0 and kill the run."""
        spot, _ = rows_from_cboe(
            {"data": {"current_price": 55.0, "options": []}}, prefer_session_close=True
        )
        assert spot == 55.0

    def test_prefer_session_close_ignores_zero_close(self):
        """CBOE sometimes ships close=0 pre-open; 0 is not a usable spot."""
        spot, _ = rows_from_cboe(
            {"data": {"current_price": 55.0, "close": 0, "options": []}},
            prefer_session_close=True,
        )
        assert spot == 55.0

    def test_extract_spot_reports_source_and_candidates(self):
        spot, source, candidates = extract_spot(self.QQQ["data"], prefer_session_close=True)
        assert spot == 687.99
        assert source == "close"
        # Both values recorded so a future divergence is visible, not silent.
        assert candidates == {"current_price": 684.47, "close": 687.99}

    def test_prev_day_close_is_never_used_as_spot(self):
        """`prev_day_close` is the PRIOR session and must never become spot.

        Pins the semantics measured 2026-08-03 intraday, where close (700.07)
        and prev_day_close (687.99) were 12 points apart. Confusing the two
        would silently price a live chain off yesterday's close.
        """
        data = {"current_price": 701.08, "close": 700.07, "prev_day_close": 687.99}
        for prefer in (True, False):
            spot, source, candidates = extract_spot(data, prefer_session_close=prefer)
            assert spot != 687.99
            assert source in ("close", "current_price")
            assert "prev_day_close" not in candidates

    def test_extract_spot_default_source_label(self):
        _spot, source, _c = extract_spot(self.QQQ["data"], prefer_session_close=False)
        assert source == "current_price"


class TestAnalyzeSpotSource:
    def test_as_of_implies_session_close(self, payload):
        """--as-of means 'a completed session', so the close is the right price."""
        payload["data"]["current_price"] = 111.0
        payload["data"]["close"] = 100.0
        rep = analyze(payload, as_of=date(2026, 1, 1))
        assert rep.spot == 100.0
        assert rep.spot_source == "close"

    def test_no_as_of_uses_current_price(self, payload):
        payload["data"]["current_price"] = 111.0
        payload["data"]["close"] = 100.0
        rep = analyze(payload)
        assert rep.spot == 111.0
        assert rep.spot_source == "current_price"

    def test_explicit_override_beats_as_of_inference(self, payload):
        payload["data"]["current_price"] = 111.0
        payload["data"]["close"] = 100.0
        rep = analyze(payload, as_of=date(2026, 1, 1), prefer_session_close=False)
        assert rep.spot == 111.0
        assert rep.spot_source == "current_price"

    def test_strike_levels_are_unaffected_by_spot_source(self, payload):
        """The load-bearing claim: walls/flip/max-pain come from OPEN INTEREST.

        This is why the 2026-08-02 bug was survivable rather than fatal — the
        gamma STRIKES in every report were correct; only spot-relative figures
        were wrong. If this test ever fails, that reassurance no longer holds.
        """
        payload["data"]["current_price"] = 100.0
        payload["data"]["close"] = 100.0
        base = analyze(payload)

        shifted = json.loads(json.dumps(payload))
        shifted["data"]["close"] = 96.0  # a different, still in-chain spot
        alt = analyze(shifted, as_of=date(2026, 1, 1))

        assert alt.spot == 96.0 and base.spot == 100.0
        assert alt.max_pain == base.max_pain
        assert alt.gamma_flip == base.gamma_flip
        # Walls are defined relative to spot, so they may legitimately move; the
        # per-strike gamma that produces them must not.
        assert [m["strike"] for m in alt.magnets] == [m["strike"] for m in base.magnets]

    def test_report_to_dict_records_source_and_candidates(self, payload):
        payload["data"]["current_price"] = 111.0
        payload["data"]["close"] = 100.0
        d = report_to_dict(analyze(payload, as_of=date(2026, 1, 1)))
        assert d["spot"] == 100.0
        assert d["spot_source"] == "close"
        assert d["spot_candidates"]["current_price"] == 111.0
        assert d["spot_candidates"]["close"] == 100.0


class TestSpotSourceCli:
    """The --spot-source flag and the divergence warning in the markdown."""

    def _payload_file(self, tmpdir, cur, close):
        with open(FIXTURE) as f:
            p = json.load(f)
        p["data"]["current_price"] = cur
        p["data"]["close"] = close
        path = Path(tmpdir) / "p.json"
        path.write_text(json.dumps(p))
        return path

    def _run(self, path, outdir, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "analyze_gex.py"),
                "ZTEST",
                "--payload-json",
                str(path),
                "--output-dir",
                str(outdir),
                *extra,
            ],
            capture_output=True,
            text=True,
        )

    def test_close_flag_overrides_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._payload_file(td, 111.0, 100.0)
            r = self._run(p, td, "--spot-source", "close")
            assert r.returncode == 0, r.stderr
            data = [json.loads(f.read_text()) for f in Path(td).glob("dealer_gex_*.json")][0]
            assert data["spot"] == 100.0
            assert data["spot_source"] == "close"

    def test_current_flag_overrides_as_of_inference(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._payload_file(td, 111.0, 100.0)
            r = self._run(p, td, "--as-of", "2026-01-01", "--spot-source", "current")
            assert r.returncode == 0, r.stderr
            data = [json.loads(f.read_text()) for f in Path(td).glob("dealer_gex_*.json")][0]
            assert data["spot"] == 111.0
            assert data["spot_source"] == "current_price"

    def test_markdown_warns_on_divergence(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._payload_file(td, 111.0, 100.0)
            r = self._run(p, td, "--as-of", "2026-01-01")
            assert r.returncode == 0, r.stderr
            md = [f.read_text() for f in Path(td).glob("dealer_gex_*.md")][0]
            assert "Spot source:" in md
            assert "diverges" in md
            assert "111" in md and "100" in md

    def test_markdown_quiet_when_prices_agree(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._payload_file(td, 100.0, 100.0)
            r = self._run(p, td, "--as-of", "2026-01-01")
            assert r.returncode == 0, r.stderr
            md = [f.read_text() for f in Path(td).glob("dealer_gex_*.md")][0]
            assert "Spot source:" in md
            assert "diverges" not in md
