"""Tests for the cohort generator's fail-closed data guard.

The guard exists because the sticky-Bull short gate reads
``reg == "Bull" and pers >= threshold``: when the Markov fit fails ``reg`` is
None, the expression is False, and the short enters UNVETOED — passing by
absence of data rather than by evidence.

The regression anchor is FDXF (cohort 2026-06-22): entered long at 162.85 with
regime/signal/persistence all null and gated_out false. It is deliberately still
allowed to enter — see test_fdxf_long_still_enters — because on the long side
nothing was bypassed, and a guard that shrinks the book is worse than the hole it
closes. Its short-side twin is what must be held out.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cohort_generate import atr14, atr_fields, data_completeness_veto  # noqa: E402

# FDXF as it was actually written to cohort_2026-06-22.json.
FDXF = dict(
    side="long", mode="pre", entry_ref_price=162.85, regime=None, persistence=None, quality=None
)


def veto(**over):
    return data_completeness_veto(**{**FDXF, **over})


class TestEntryRefPrice:
    """Required on BOTH sides: without a mark, cohort_track drops the name from
    the basket return entirely — a shrinking denominator, not a wrong number."""

    @pytest.mark.parametrize("side", ["long", "short"])
    def test_present_and_positive_passes(self, side):
        assert veto(side=side, regime="Bull", persistence=0.9) is None

    @pytest.mark.parametrize("bad", [None, 0, 0.0, -1.5, "162.85", True, False])
    @pytest.mark.parametrize("side", ["long", "short"])
    def test_missing_or_unusable_is_vetoed(self, bad, side):
        reason = veto(side=side, entry_ref_price=bad, regime="Bull", persistence=0.9)
        assert reason is not None
        assert "entry_ref_price" in reason

    def test_bool_is_not_a_price(self):
        # True == 1 numerically; a bool reaching this field means upstream broke.
        assert "entry_ref_price" in veto(entry_ref_price=True)


class TestShortSideRegimeRequired:
    """Shorts are the only side the Markov gate can veto, so they are the only
    side where missing regime data buys a free pass."""

    def test_complete_short_passes(self):
        assert veto(side="short", regime="Bear", persistence=0.72) is None

    def test_null_regime_vetoes_the_short(self):
        reason = veto(side="short", regime=None, persistence=0.72)
        assert reason is not None
        assert "regime" in reason
        assert "sticky-Bull gate cannot evaluate" in reason

    @pytest.mark.parametrize("bad", [None, "0.72", True])
    def test_unusable_persistence_vetoes_the_short(self, bad):
        reason = veto(side="short", regime="Bull", persistence=bad)
        assert reason is not None
        assert "persistence" in reason

    def test_a_sticky_bull_short_is_not_this_guards_business(self):
        # Complete data — the real gate handles it upstream and owns the label.
        assert veto(side="short", regime="Bull", persistence=0.95) is None


class TestLongSideUnaffected:
    def test_fdxf_long_still_enters(self):
        """The observed live case. Null regime on a LONG bypasses no gate, so the
        guard must NOT hold it out — this is the shrink-the-book regression."""
        assert veto() is None

    def test_fdxf_short_twin_is_held_out(self):
        """Same record, short side: now the missing fit does buy a free pass."""
        assert veto(side="short") is not None


class TestQualityIsModeConditional:
    """quality is None in pre mode by design, and in post-mode cohorts predating
    the 2026-07-02 drift-quality commit. Requiring it unconditionally would
    retroactively veto most of the book."""

    def test_pre_mode_tolerates_null_quality(self):
        assert veto(mode="pre", quality=None) is None

    def test_post_mode_requires_quality(self):
        reason = veto(mode="post", quality=None, regime="Bull", persistence=0.9)
        assert reason is not None
        assert "drift-quality" in reason

    def test_post_mode_with_quality_passes(self):
        assert veto(mode="post", quality=0, regime="Bull", persistence=0.9) is None

    def test_quality_zero_is_a_value_not_an_absence(self):
        # 0/4 is a real score the drift-quality gate acts on; only None is missing.
        assert veto(mode="post", quality=0) is None


class TestReasonStrings:
    """gate_reason routes records into the data_vetoed bucket by prefix."""

    @pytest.mark.parametrize(
        "over",
        [
            dict(entry_ref_price=None),
            dict(side="short", regime=None),
            dict(side="short", regime="Bull", persistence=None),
            dict(mode="post", quality=None),
        ],
    )
    def test_every_veto_reason_carries_the_routing_prefix(self, over):
        reason = veto(**over)
        assert reason is not None
        assert reason.startswith("incomplete data — ")


# ─── ATR stop-reference (recorded only) ──────────────────────────────────────


def bars(*hlc):
    return [{"high": h, "low": lo, "close": c} for h, lo, c in hlc]


def flat_bars(n, high=102.0, low=100.0, close=101.0):
    """n identical bars: TR is exactly (high - low) every session, no gaps."""
    return bars(*[(high, low, close)] * n)


class TestAtr14:
    def test_mean_of_true_ranges(self):
        assert atr14(flat_bars(15)) == pytest.approx(2.0)

    def test_needs_period_plus_one_bars(self):
        # 14 true ranges require 15 closes.
        assert atr14(flat_bars(14)) is None
        assert atr14(flat_bars(15)) is not None

    def test_uses_only_the_last_period_bars(self):
        # A huge bar 20 sessions back must not leak into a 14-period window.
        old = bars((500.0, 100.0, 300.0))
        assert atr14(old + flat_bars(20)) == pytest.approx(2.0)

    def test_gap_up_uses_high_minus_prev_close(self):
        # prev close 101, next bar 150/148 -> TR = |150 - 101| = 49, not 2.
        series = flat_bars(14) + bars((150.0, 148.0, 149.0))
        # 13 sessions of TR 2 plus one of 49
        assert atr14(series) == pytest.approx((13 * 2.0 + 49.0) / 14)

    def test_gap_down_uses_low_minus_prev_close(self):
        series = flat_bars(14) + bars((60.0, 50.0, 55.0))
        assert atr14(series) == pytest.approx((13 * 2.0 + 51.0) / 14)

    def test_bars_missing_ohlc_are_skipped(self):
        series = flat_bars(15) + [{"high": None, "low": 1.0, "close": 2.0}]
        assert atr14(series) == pytest.approx(2.0)

    def test_all_unusable_returns_none(self):
        assert atr14([{"close": 5.0}] * 40) is None

    def test_empty(self):
        assert atr14([]) is None


class TestAtrFields:
    def test_percent_is_relative_to_entry_reference(self):
        f = atr_fields(2.5, 50.0, "pre-print")
        assert f == {"atr14": 2.5, "atr14_pct": 5.0, "atr14_basis": "pre-print"}

    def test_missing_atr_nulls_every_column_including_basis(self):
        # A basis label with no ATR behind it would imply a measurement was made.
        assert atr_fields(None, 100.0, "trailing") == {
            "atr14": None, "atr14_pct": None, "atr14_basis": None
        }

    @pytest.mark.parametrize("bad_ref", [None, 0, -10.0, "100", True])
    def test_unusable_reference_keeps_atr_but_drops_the_percent(self, bad_ref):
        f = atr_fields(2.0, bad_ref, "pre-print")
        assert f["atr14"] == 2.0
        assert f["atr14_pct"] is None

    def test_basis_is_recorded_so_modes_are_never_silently_compared(self):
        assert atr_fields(1.0, 100.0, "pre-print")["atr14_basis"] == "pre-print"
        assert atr_fields(1.0, 100.0, "trailing")["atr14_basis"] == "trailing"


class TestAtrNeverGates:
    """ATR is a recorded reference. If it ever reaches the veto it has become a
    gate, which is exactly what this field was scoped not to be."""

    def test_a_null_atr_does_not_hold_a_name_out(self):
        assert veto(entry_ref_price=100.0, regime="Bear", persistence=0.8, side="short") is None

    def test_veto_signature_has_no_atr_parameter(self):
        import inspect

        from cohort_generate import data_completeness_veto as f
        assert "atr" not in "".join(inspect.signature(f).parameters)
