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

from cohort_generate import data_completeness_veto  # noqa: E402

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
