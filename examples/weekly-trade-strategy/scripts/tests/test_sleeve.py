"""Tests for the derived risk-sleeve helper and the plan-build assertion.

The anchor case is 2026-07-27: `order_plan_alpaca.json` recorded a pre-trade
sleeve of 59.49% and a band of [50, 58]. The band excluded its own documented
starting value, the Monday auto-fire tripped its own check, and the week's cut
never executed. Both numbers were already in the same file — nothing compared
them. test_the_2026_07_27_regression is that comparison.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sleeve import (  # noqa: E402
    CASH_EQUIVALENTS,
    compute_sleeve,
    normalize_alpaca,
    normalize_schwab,
    validate_plan,
)

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "sleeve.py")

# The real Alpaca book as of 2026-07-27 09:32 ET, equity $102,490.16.
ALPACA_POSITIONS = [
    {"symbol": "SPY", "market_value": "14891.8", "asset_class": "us_equity"},
    {"symbol": "QQQ", "market_value": "6909.7", "asset_class": "us_equity"},
    {"symbol": "IWM", "market_value": "9108.73", "asset_class": "us_equity"},
    {"symbol": "XLE", "market_value": "4294.59", "asset_class": "us_equity"},
    {"symbol": "ITA", "market_value": "5606.94", "asset_class": "us_equity"},
    {"symbol": "XLF", "market_value": "7577.01", "asset_class": "us_equity"},
    {"symbol": "XLV", "market_value": "5526.7", "asset_class": "us_equity"},
    {"symbol": "XLP", "market_value": "3045.96", "asset_class": "us_equity"},
    {"symbol": "XLU", "market_value": "2078.55", "asset_class": "us_equity"},
    {"symbol": "GLD", "market_value": "1121.895", "asset_class": "us_equity"},
    {"symbol": "TLT", "market_value": "1004.2812", "asset_class": "us_equity"},
    {"symbol": "SGOV", "market_value": "24154.8", "asset_class": "us_equity"},
    {"symbol": "SPY260731P00705000", "market_value": "50", "asset_class": "us_option"},
    {"symbol": "SPY260731P00680000", "market_value": "-18", "asset_class": "us_option"},
]
ALPACA_EQUITY = 102490.16
ALPACA_CASH = 17134.69


def alpaca_sleeve():
    return compute_sleeve(normalize_alpaca(ALPACA_POSITIONS), ALPACA_EQUITY, ALPACA_CASH)


class TestComputeSleeve:
    def test_reproduces_the_hand_computed_figure(self):
        # 59.68% was computed by hand during the live 2026-07-27 fire.
        assert alpaca_sleeve().risk_pct == 59.68

    def test_sgov_is_cash_not_risk(self):
        s = alpaca_sleeve()
        assert s.cash_equivalent_usd == pytest.approx(24154.8)
        assert "SGOV" not in s.risk_symbols
        # Misclassifying SGOV would be a ~23.6pp error on this book.
        assert s.cash_equivalent_usd / s.equity_usd * 100 > 23

    def test_options_excluded_from_risk(self):
        s = alpaca_sleeve()
        # Net of long 50 and short -18.
        assert s.option_net_usd == pytest.approx(32.0)
        assert not any(sym.startswith("SPY2607") for sym in s.risk_symbols)

    def test_short_option_leg_signs_through(self):
        s = compute_sleeve(
            normalize_alpaca(
                [{"symbol": "X260731P1", "market_value": "-18", "asset_class": "us_option"}]
            ),
            1000.0,
        )
        assert s.option_net_usd == -18.0
        assert s.risk_usd == 0.0

    def test_cash_plus_equivalent(self):
        s = alpaca_sleeve()
        assert s.cash_plus_equivalent_usd == pytest.approx(17134.69 + 24154.8)
        assert s.cash_plus_equivalent_pct == pytest.approx(40.28, abs=0.02)

    def test_max_position(self):
        # SPY is the largest at 14891.80 / 102490.16.
        assert alpaca_sleeve().max_position_pct == pytest.approx(14.53, abs=0.02)

    def test_zero_equity_does_not_divide_by_zero(self):
        s = compute_sleeve(normalize_alpaca(ALPACA_POSITIONS), 0.0)
        assert s.risk_pct == 0.0
        assert s.cash_plus_equivalent_pct == 0.0
        assert s.max_position_pct == 0.0

    def test_empty_book(self):
        s = compute_sleeve([], 1000.0, 1000.0)
        assert s.risk_pct == 0.0
        assert s.cash_plus_equivalent_pct == 100.0

    def test_cash_equivalent_set_is_overridable(self):
        s = compute_sleeve(
            normalize_alpaca(ALPACA_POSITIONS), ALPACA_EQUITY, cash_equivalents=frozenset()
        )
        # With SGOV reclassified as risk the sleeve jumps ~23.6pp.
        assert s.risk_pct == pytest.approx(83.24, abs=0.05)


class TestSchwabNormalizer:
    """One definition, both brokers — the schemas differ, the arithmetic must not."""

    SCHWAB = [
        {
            "instrument": {"symbol": "SPY", "assetType": "COLLECTIVE_INVESTMENT"},
            "marketValue": 2978.47,
        },
        {
            "instrument": {"symbol": "IWM", "assetType": "COLLECTIVE_INVESTMENT"},
            "marketValue": 1764.30,
        },
        {
            "instrument": {"symbol": "SGOV", "assetType": "COLLECTIVE_INVESTMENT"},
            "marketValue": 1000.0,
        },
    ]

    def test_schwab_shape_parses(self):
        s = compute_sleeve(normalize_schwab(self.SCHWAB), 10000.0)
        assert s.risk_usd == pytest.approx(4742.77)
        assert s.cash_equivalent_usd == pytest.approx(1000.0)

    def test_uniform_symbol_fallback(self):
        rows = normalize_schwab([{"instrument": {"uniformSymbol": "QQQ"}, "marketValue": 5.0}])
        assert rows[0]["symbol"] == "QQQ"

    def test_schwab_option_detected(self):
        rows = normalize_schwab(
            [
                {
                    "instrument": {"symbol": "SPY   260731P00705000", "assetType": "OPTION"},
                    "marketValue": 50,
                }
            ]
        )
        assert rows[0]["kind"] == "option"

    def test_both_normalizers_agree_on_identical_books(self):
        a = compute_sleeve(
            normalize_alpaca(
                [
                    {"symbol": "SPY", "market_value": "100", "asset_class": "us_equity"},
                    {"symbol": "SGOV", "market_value": "50", "asset_class": "us_equity"},
                ]
            ),
            200.0,
        )
        s = compute_sleeve(
            normalize_schwab(
                [
                    {
                        "instrument": {"symbol": "SPY", "assetType": "COLLECTIVE_INVESTMENT"},
                        "marketValue": 100,
                    },
                    {
                        "instrument": {"symbol": "SGOV", "assetType": "COLLECTIVE_INVESTMENT"},
                        "marketValue": 50,
                    },
                ]
            ),
            200.0,
        )
        assert a.risk_pct == s.risk_pct == 50.0


# --------------------------------------------------------------------------- #


def plan(**over):
    base = {
        "current_book_verified_2026-07-26": {"risk_sleeve_pct": 59.49},
        "expected_post_trade": {"risk_sleeve_pct": 54.51},
        "gap_safety_check": {"pre_trade_band_pct": [56, 62], "post_trade_band_pct": [50, 58]},
        "orders": [
            {"symbol": "SPY", "side": "sell", "qty": 2, "client_order_id": "wk0727-SPY-sell"}
        ],
    }
    base.update(over)
    return base


class TestValidatePlan:
    def test_a_correct_plan_passes(self):
        assert validate_plan(plan()) == []

    def test_the_2026_07_27_regression(self):
        """The exact plan that halted the live fire must now fail at build time."""
        bad = plan(gap_safety_check={"pre_trade_band_pct": [50, 58]})
        errs = validate_plan(bad)
        assert any("PRE-TRADE BAND EXCLUDES ITS OWN BOOK" in e for e in errs)
        assert any("59.49" in e for e in errs)

    def test_legacy_ambiguous_band_key_is_flagged(self):
        errs = validate_plan(plan(gap_safety_check={"risk_sleeve_band_pct": [50, 58]}))
        assert any("legacy ambiguous" in e for e in errs)

    def test_legacy_key_still_gets_containment_checked(self):
        # Flagging the naming must not swallow the substantive failure.
        errs = validate_plan(plan(gap_safety_check={"risk_sleeve_band_pct": [50, 58]}))
        assert any("EXCLUDES ITS OWN BOOK" in e for e in errs)

    def test_post_trade_band_excluding_target_is_caught(self):
        errs = validate_plan(
            plan(gap_safety_check={"pre_trade_band_pct": [56, 62], "post_trade_band_pct": [30, 40]})
        )
        assert any("post-trade sleeve 54.51%" in e for e in errs)

    def test_band_too_wide_to_discriminate(self):
        # A band containing both endpoints of a 5pp move cannot detect anything.
        errs = validate_plan(
            plan(gap_safety_check={"pre_trade_band_pct": [40, 70], "post_trade_band_pct": [50, 58]})
        )
        assert any("too wide to detect anything" in e for e in errs)

    def test_small_planned_move_may_share_a_band(self):
        # A 1pp move legitimately sits inside one band; do not cry wolf.
        p = plan(
            expected_post_trade={"risk_sleeve_pct": 53.5},
            gap_safety_check={"pre_trade_band_pct": [50, 58], "post_trade_band_pct": [50, 58]},
        )
        p["current_book_verified_2026-07-26"] = {"risk_sleeve_pct": 54.0}
        errs = validate_plan(p)
        assert not any("too wide" in e for e in errs), errs

    def test_two_book_keys_is_ambiguous_not_silently_resolved(self):
        p = plan()
        p["current_book_verified_2026-07-19"] = {"risk_sleeve_pct": 41.0}
        assert any("multiple current_book_verified" in e for e in validate_plan(p))

    def test_missing_pre_trade_record_is_an_error(self):
        p = plan()
        del p["current_book_verified_2026-07-26"]
        assert any("nothing to validate against" in e for e in validate_plan(p))

    def test_dated_key_suffix_is_discovered_whatever_the_date(self):
        p = plan()
        p["current_book_verified_2099-01-01"] = p.pop("current_book_verified_2026-07-26")
        assert validate_plan(p) == []

    @pytest.mark.parametrize(
        "order,expect",
        [
            ({"symbol": "SPY", "side": "sell", "qty": 2}, "no client_order_id"),
            (
                {"symbol": "SPY", "side": "sell", "qty": 0, "client_order_id": "x"},
                "non-positive qty",
            ),
            ({"symbol": "SPY", "side": "hold", "qty": 2, "client_order_id": "x"}, "invalid side"),
        ],
    )
    def test_order_level_checks(self, order, expect):
        assert any(expect in e for e in validate_plan(plan(orders=[order])))

    def test_duplicate_client_order_ids(self):
        o = {"symbol": "SPY", "side": "sell", "qty": 1, "client_order_id": "dup"}
        assert any(
            "duplicate client_order_id" in e for e in validate_plan(plan(orders=[o, dict(o)]))
        )

    def test_verify_only_plan_with_no_orders_is_fine(self):
        assert validate_plan(plan(orders=[])) == []


class TestCli:
    def test_exit_1_on_a_bad_plan(self, tmp_path):
        p = tmp_path / "order_plan_bad.json"
        p.write_text(json.dumps(plan(gap_safety_check={"pre_trade_band_pct": [50, 58]})))
        r = subprocess.run(
            [sys.executable, SCRIPT, "--plan", str(p)], capture_output=True, text=True
        )
        assert r.returncode == 1
        assert "EXCLUDES ITS OWN BOOK" in r.stdout

    def test_exit_0_on_a_good_plan(self, tmp_path):
        p = tmp_path / "order_plan_ok.json"
        p.write_text(json.dumps(plan()))
        r = subprocess.run(
            [sys.executable, SCRIPT, "--plan", str(p)], capture_output=True, text=True
        )
        assert r.returncode == 0, r.stdout + r.stderr

    def test_unreadable_plan_fails_loudly(self, tmp_path):
        p = tmp_path / "order_plan_broken.json"
        p.write_text("{not json")
        r = subprocess.run(
            [sys.executable, SCRIPT, "--plan", str(p)], capture_output=True, text=True
        )
        assert r.returncode == 1
        assert "unreadable" in r.stderr


def test_cash_equivalents_covers_the_holdings_we_actually_use():
    assert "SGOV" in CASH_EQUIVALENTS
