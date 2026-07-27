#!/usr/bin/env python3
"""Risk-sleeve arithmetic — ONE definition, shared by every consumer.

Why this file exists
--------------------
The "risk sleeve" (equity exposure as a percentage of account equity) is the
number the whole weekly pipeline turns on, and until now it was defined NOWHERE:
no code computed it, `~/CLAUDE.md` never defined it, and the slash command never
mentioned it. It existed only as hand-typed fields re-invented in each week's
`order_plan_*.json`.

That drifted, and on 2026-07-27 it broke a live rebalance. The plan recorded
`current_book_verified.risk_sleeve_pct: 59.49` AND set a pre-trade band of
[50, 58] — a band that excludes its own documented starting value. The Monday
auto-fire tripped its own safety check, halted before placing a single order,
and the week's cut never executed. The band history shows the drift plainly:
absent -> [48,58] -> [55,62] (correct) -> [50,58] (broken).

The root cause was not the number. It was that the number was TYPED rather than
DERIVED, and that nothing compared the two numbers already sitting in the same
file. Both fixes live here:

  compute_sleeve()  - derive it, once, from a broker positions payload
  validate_plan()   - assert a plan's bands actually contain its own values

Usage:
    python3 sleeve.py --plan reports/2026-08-03/order_plan_alpaca.json
    python3 sleeve.py --plan reports/*/order_plan_*.json --quiet
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass, field

# Cash-equivalent ETFs: held in the equity account but economically cash, so they
# belong in the cash floor (>= 25%), NOT in the risk sleeve. Getting this wrong
# is a ~24pp error on the current book — SGOV alone is ~23.6% of equity.
CASH_EQUIVALENTS = frozenset({"SGOV", "BIL", "SHV", "USFR", "TFLO", "ICSH", "JPST", "SHY"})


@dataclass
class Sleeve:
    """A book decomposed into the three buckets the framework reasons about."""

    equity_usd: float
    risk_usd: float
    cash_equivalent_usd: float
    option_net_usd: float
    free_cash_usd: float | None = None
    risk_symbols: dict = field(default_factory=dict)

    @property
    def risk_pct(self) -> float:
        return round(self.risk_usd / self.equity_usd * 100, 2) if self.equity_usd else 0.0

    @property
    def cash_plus_equivalent_usd(self) -> float:
        return (self.free_cash_usd or 0.0) + self.cash_equivalent_usd

    @property
    def cash_plus_equivalent_pct(self) -> float:
        if not self.equity_usd:
            return 0.0
        return round(self.cash_plus_equivalent_usd / self.equity_usd * 100, 2)

    @property
    def max_position_pct(self) -> float:
        if not self.equity_usd or not self.risk_symbols:
            return 0.0
        return round(max(self.risk_symbols.values()) / self.equity_usd * 100, 2)

    def as_dict(self) -> dict:
        return {
            "equity_usd": round(self.equity_usd, 2),
            "risk_usd": round(self.risk_usd, 2),
            "risk_pct": self.risk_pct,
            "cash_equivalent_usd": round(self.cash_equivalent_usd, 2),
            "free_cash_usd": round(self.free_cash_usd, 2)
            if self.free_cash_usd is not None
            else None,
            "cash_plus_equivalent_pct": self.cash_plus_equivalent_pct,
            "option_net_usd": round(self.option_net_usd, 2),
            "max_position_pct": self.max_position_pct,
        }


def _f(v) -> float:
    """Alpaca returns numbers as strings; Schwab returns floats."""
    if v is None or v == "":
        return 0.0
    return float(v)


def normalize_alpaca(positions: list[dict]) -> list[dict]:
    """Alpaca `get_all_positions` -> [{symbol, market_value, kind}]."""
    out = []
    for p in positions:
        cls = (p.get("asset_class") or "").lower()
        out.append(
            {
                "symbol": p.get("symbol", ""),
                "market_value": _f(p.get("market_value")),
                "kind": "option" if "option" in cls else "equity",
            }
        )
    return out


def normalize_schwab(positions: list[dict]) -> list[dict]:
    """Schwab `get_account_with_positions` -> [{symbol, market_value, kind}].

    Schwab reports long and short quantities separately and marketValue already
    carries the sign, so it needs no side handling the way Alpaca does.
    """
    out = []
    for p in positions:
        inst = p.get("instrument") or {}
        atype = (inst.get("assetType") or "").upper()
        out.append(
            {
                "symbol": inst.get("symbol") or inst.get("uniformSymbol") or "",
                "market_value": _f(p.get("marketValue")),
                "kind": "option" if atype == "OPTION" else "equity",
            }
        )
    return out


def compute_sleeve(
    positions: list[dict],
    equity_usd: float,
    free_cash_usd: float | None = None,
    cash_equivalents: frozenset = CASH_EQUIVALENTS,
) -> Sleeve:
    """Decompose a normalized positions list into risk / cash-equivalent / option.

    `positions` must already be normalized (see normalize_alpaca/normalize_schwab).
    Options are EXCLUDED from the risk sleeve: the hedge is a separate line in the
    posture, its market value is tiny relative to the book (it decayed to $32 of a
    $102k account in the week this file was written), and folding a short put's
    negative market value into an "equity exposure" figure is meaningless.
    """
    risk = 0.0
    cash_eq = 0.0
    opt = 0.0
    risk_symbols: dict[str, float] = {}
    for p in positions:
        mv = _f(p.get("market_value"))
        sym = (p.get("symbol") or "").upper()
        if p.get("kind") == "option":
            opt += mv
        elif sym in cash_equivalents:
            cash_eq += mv
        else:
            risk += mv
            risk_symbols[sym] = risk_symbols.get(sym, 0.0) + mv
    return Sleeve(
        equity_usd=equity_usd,
        risk_usd=risk,
        cash_equivalent_usd=cash_eq,
        option_net_usd=opt,
        free_cash_usd=free_cash_usd,
        risk_symbols=risk_symbols,
    )


# --------------------------------------------------------------------------- #
# Plan validation — the assertion that would have prevented 2026-07-27
# --------------------------------------------------------------------------- #

SINGLE_POSITION_CAP_PCT = 20.0
CASH_FLOOR_PCT = 25.0


def _band_contains(band, value) -> bool:
    if not band or value is None:
        return True  # nothing to check
    lo, hi = band[0], band[1]
    return lo <= value <= hi


def validate_plan(plan: dict) -> list[str]:
    """Return a list of problems with an order plan. Empty list == valid.

    The headline check is the one that was missing: a band must CONTAIN the value
    it is meant to bound, and both numbers are already in the file. On 2026-07-27
    `pre_trade_band` [50,58] and `risk_sleeve_pct` 59.49 sat two blocks apart in
    the same JSON and nothing compared them.
    """
    errs: list[str] = []
    gsc = plan.get("gap_safety_check") or {}

    # Locate the recorded pre-trade sleeve under any of the dated key spellings.
    # More than one is ambiguous: picking the first silently validates against an
    # arbitrary book. Refuse rather than guess.
    book_keys = [
        k for k, v in plan.items() if k.startswith("current_book_verified") and isinstance(v, dict)
    ]
    if len(book_keys) > 1:
        errs.append(
            f"multiple current_book_verified* keys {sorted(book_keys)} — ambiguous which "
            "book the bands are meant to bound; keep exactly one"
        )
    pre = plan[book_keys[0]].get("risk_sleeve_pct") if book_keys else None
    post = (plan.get("expected_post_trade") or {}).get("risk_sleeve_pct")

    pre_band = gsc.get("pre_trade_band_pct")
    post_band = gsc.get("post_trade_band_pct")
    legacy_band = gsc.get("risk_sleeve_band_pct")

    if legacy_band and not (pre_band or post_band):
        errs.append(
            f"gap_safety_check uses the legacy ambiguous 'risk_sleeve_band_pct' {legacy_band}. "
            "Split it into 'pre_trade_band_pct' (anchored to the CURRENT book) and "
            "'post_trade_band_pct' (anchored to the YAML target). Conflating them is "
            "what broke the 2026-07-27 fire."
        )
        # Fall back so the containment check below still runs against something.
        pre_band = pre_band or legacy_band

    if pre is None:
        errs.append(
            "no current_book_verified*.risk_sleeve_pct recorded — nothing to validate against"
        )
    elif not _band_contains(pre_band, pre):
        errs.append(
            f"PRE-TRADE BAND EXCLUDES ITS OWN BOOK: recorded pre-trade sleeve {pre}% "
            f"is outside pre_trade_band_pct {pre_band}. This plan would halt its own "
            f"Monday fire before placing an order."
        )

    if post is not None and not _band_contains(post_band, post):
        errs.append(f"post-trade sleeve {post}% is outside post_trade_band_pct {post_band}")

    # A pre-trade band that also contains the post-trade target is not doing its job:
    # it cannot distinguish "book is as expected" from "cut already happened".
    if pre_band and post is not None and _band_contains(pre_band, post) and pre is not None:
        if abs(pre - post) > 2:
            errs.append(
                f"pre_trade_band_pct {pre_band} contains BOTH the pre-trade sleeve "
                f"({pre}%) and the post-trade target ({post}%) despite a "
                f"{abs(pre - post):.1f}pp planned move — the band is too wide to detect anything"
            )

    # Order-level sanity.
    for o in plan.get("orders") or []:
        if not o.get("client_order_id"):
            errs.append(f"order {o.get('symbol')} has no client_order_id (idempotency key)")
        if _f(o.get("qty")) <= 0:
            errs.append(f"order {o.get('symbol')} has non-positive qty {o.get('qty')!r}")
        if o.get("side") not in ("buy", "sell"):
            errs.append(f"order {o.get('symbol')} has invalid side {o.get('side')!r}")

    # Duplicate client_order_ids inside one plan would collide at the broker.
    ids = [o.get("client_order_id") for o in (plan.get("orders") or [])]
    if len(ids) != len(set(ids)):
        errs.append(f"duplicate client_order_id within the plan: {ids}")

    return errs


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--plan", nargs="+", required=True, help="order_plan_*.json path(s); globs allowed"
    )
    ap.add_argument("--quiet", action="store_true", help="only print failures")
    args = ap.parse_args()

    paths: list[str] = []
    for p in args.plan:
        paths.extend(sorted(glob.glob(p)) or [p])

    bad = 0
    for path in paths:
        try:
            plan = _load(path)
        except (OSError, json.JSONDecodeError) as e:
            print(f"FAIL {path}: unreadable ({e})", file=sys.stderr)
            bad += 1
            continue
        errs = validate_plan(plan)
        if errs:
            bad += 1
            print(f"FAIL {path}")
            for e in errs:
                print(f"   - {e}")
        elif not args.quiet:
            print(f"OK   {path}")
    if bad:
        print(f"\n{bad} plan(s) failed validation", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
