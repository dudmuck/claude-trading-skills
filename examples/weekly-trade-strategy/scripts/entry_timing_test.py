#!/usr/bin/env python3
"""Pullback-vs-immediate entry test for the PEAD gap-up long pocket.

Reads the cached backtest events + price series (no FMP calls) and compares
entry variants on the surviving pocket (gap-up longs, |reaction| >= 5%):

  A. immediate       — enter at the first close after the report (current rule)
  B. pullback+brk    — wait for the first down-close within WAIT days, then enter
                       on the first close that recovers above the pre-pullback
                       close (close-only proxy for pead-screener's red-candle ->
                       breakout); no setup completion within WAIT+RECOVER -> no trade
  C. pullback only   — enter at the first down-close itself (buy the dip, no confirm)
  D. delay+3         — enter unconditionally 3 trading days after A (tests whether
                       waiting alone, without a pattern, helps)

All variants hold HOLD trading days from their own entry. Two scoreboards:
per-entered-trade stats AND per-signal expectancy (missed setups count as 0),
because a filter that only trades winners but skips half the signals can still
lose the expectancy race.

Data limitation: cached series are close+volume (no OHLC), so candle bodies and
intraday highs are approximated by closes. Directional answer, not exact fills.
"""

import json
from glob import glob
from pathlib import Path
from statistics import mean, median

CACHE = Path.home() / "shortlong_cohorts/backtest_cache"
EVENTS = Path.home() / "shortlong_cohorts/backtest/backtest_events_20260611_1615.jsonl"
HOLD = 14          # trading days held from entry
WAIT = 5           # days allowed for the pullback to appear
RECOVER = 10       # further days allowed for the breakout/recovery
MIN_RX = 5.0


def load_px(sym: str):
    rows = []
    for f in glob(str(CACHE / f"px_{sym}_*.json")):
        rows += json.load(open(f)) or []
    pairs = sorted({(r["date"], r["price"]) for r in rows if r.get("price")})
    return [p[0] for p in pairs], [p[1] for p in pairs]


def first_after(dates, d):
    for i, dt in enumerate(dates):
        if dt > d:
            return i
    return None


def ret(closes, i_in, i_out):
    if i_in is None or i_out >= len(closes):
        return None
    return closes[i_out] / closes[i_in] - 1.0


def variants(dates, closes, i0):
    """Return {variant: entry_index_or_None} given immediate-entry index i0."""
    out = {"A_immediate": i0}
    # find first down-close in (i0, i0+WAIT]
    j = None
    for k in range(i0 + 1, min(i0 + 1 + WAIT, len(closes))):
        if closes[k] < closes[k - 1]:
            j = k
            break
    out["C_pullback"] = j
    # breakout: first close > pre-pullback close, within RECOVER days after j
    b = None
    if j is not None:
        ref = closes[j - 1]
        for k in range(j + 1, min(j + 1 + RECOVER, len(closes))):
            if closes[k] > ref:
                b = k
                break
    out["B_pullback_breakout"] = b
    out["D_delay3"] = i0 + 3 if i0 + 3 < len(closes) else None
    return out


def stats(xs):
    if not xs:
        return "n=0"
    w = sum(1 for x in xs if x > 0)
    return (f"n={len(xs)}, mean {mean(xs)*100:+.2f}%, median {median(xs)*100:+.2f}%, "
            f"win {w/len(xs)*100:.0f}%")


def main():
    events = [json.loads(l) for l in open(EVENTS)]
    pocket = [e for e in events if e["side"] == "long" and e["reaction_pct"] >= MIN_RX]
    print(f"pocket: {len(pocket)} gap-up (>= {MIN_RX}%) long events\n")

    px_cache = {}
    rows = []  # (event, {variant: signed_return_or_None})
    for e in pocket:
        sym = e["symbol"]
        if sym not in px_cache:
            px_cache[sym] = load_px(sym)
        dates, closes = px_cache[sym]
        if not dates:
            continue
        i0 = first_after(dates, e["report_date"])
        if i0 is None:
            continue
        vs = variants(dates, closes, i0)
        rets = {v: (ret(closes, i, i + HOLD) if i is not None else None)
                for v, i in vs.items()}
        rows.append((e, rets))

    for bucket, lo in (("|rx| >= 5%", 5.0), ("|rx| >= 10%", 10.0)):
        sub = [(e, r) for e, r in rows if e["reaction_pct"] >= lo]
        print(f"=== {bucket} (signals={len(sub)}) — hold {HOLD}d from entry ===")
        for v in ("A_immediate", "B_pullback_breakout", "C_pullback", "D_delay3"):
            entered = [r[v] for _, r in sub if r[v] is not None]
            per_signal = [r[v] if r[v] is not None else 0.0 for _, r in sub]
            fill = len(entered) / len(sub) * 100 if sub else 0
            print(f"  {v:<22} fill {fill:3.0f}% | entered: {stats(entered)}")
            print(f"  {'':<22}          | per-signal expectancy "
                  f"{mean(per_signal)*100:+.2f}%/signal")
        print()

    # by year for the head-to-head that matters (A vs B), >=5% pocket
    print("=== A vs B by year (entered trades, >=5%) ===")
    years = sorted({e["week"][:4] for e, _ in rows})
    for y in years:
        sub = [(e, r) for e, r in rows if e["week"].startswith(y)]
        a = [r["A_immediate"] for _, r in sub if r["A_immediate"] is not None]
        b = [r["B_pullback_breakout"] for _, r in sub if r["B_pullback_breakout"] is not None]
        print(f"  {y}: A {stats(a)}")
        print(f"        B {stats(b)}")


if __name__ == "__main__":
    main()
