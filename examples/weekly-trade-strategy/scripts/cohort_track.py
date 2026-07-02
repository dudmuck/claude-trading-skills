#!/usr/bin/env python3
"""Forward-test tracker — marks logged cohorts to market and measures the edge.

Reads every ~/shortlong_cohorts/cohort_*.json, fetches current prices, computes
each name's signed forward return from its entry-ref price, and aggregates the
two questions that decide whether this strategy earns real cash:

  1. Does the Markov-gated rule have edge?   (long vs short basket return,
     and regime-alignment buckets: do aligned names beat fighting names?)
  2. Does the short-side gate earn its keep?  (of the shorts it VETOED, how many
     would have lost money as shorts — i.e., did the veto dodge losers?)

It also appends a dated snapshot per name to ~/shortlong_cohorts/marks.jsonl, so
repeated runs build the T+5/14/30/90 time series for proper horizon analysis.

This is a SIGNAL test: returns use entry-ref vs current price (no borrow cost,
slippage, or fills). Isolates the signal — execution realism comes later.

Usage:
    export FMP_API_KEY=...
    python3 ~/cohort_track.py                       # mark all cohorts, print report
    python3 ~/cohort_track.py --no-marks            # don't append to marks.jsonl
    python3 ~/cohort_track.py --dir ~/shortlong_cohorts
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from statistics import mean

FMP_BASE = "https://financialmodelingprep.com/stable"


def fmp_quote_price(symbol: str) -> float | None:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        sys.exit("Set FMP_API_KEY environment variable.")
    url = f"{FMP_BASE}/quote?" + urllib.parse.urlencode({"symbol": symbol, "apikey": key})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
        if isinstance(data, list) and data:
            return data[0].get("price")
    except Exception:
        return None
    return None


def signed_return(side: str, entry: float, cur: float) -> float:
    """Profit-positive return. long: up = +. short: down = +."""
    raw = cur / entry - 1.0
    return raw if side == "long" else -raw


def horizon_label(age: int) -> str:
    for h in (5, 14, 30, 90):
        if abs(age - h) <= 2:
            return f"~T+{h}"
    return f"T+{age}"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=str(Path.home() / "shortlong_cohorts"))
    p.add_argument("--no-marks", action="store_true", help="Do not append snapshots to marks.jsonl.")
    args = p.parse_args()

    cdir = Path(args.dir).expanduser()
    files = sorted(cdir.glob("cohort_*.json"))
    if not files:
        sys.exit(f"No cohort_*.json in {cdir}")
    today = date.today()

    cohorts = [json.loads(f.read_text()) for f in files]

    # Collect the signal set (anything assigned a side, incl. gated) across cohorts.
    def signal_rows(c):
        return [r for r in c["candidates"] if r.get("entry_side") in ("long", "short")]

    symbols = sorted({r["symbol"] for c in cohorts for r in signal_rows(c)})
    print(f"Fetching current prices for {len(symbols)} symbols...", file=sys.stderr)
    price = {s: fmp_quote_price(s) for s in symbols}
    missing = [s for s, v in price.items() if v is None]
    if missing:
        print(f"  ⚠ no price for: {', '.join(missing)}", file=sys.stderr)

    marks = []           # rows for marks.jsonl
    all_signal = []      # (entry_mode, row, ret) across everything, for cross-cohort stats
    out = [f"# Cohort tracker — as of {today.isoformat()}", ""]

    for c in cohorts:
        cdate = c["cohort_date"]
        cmode = c.get("entry_mode", "pre")
        rows = signal_rows(c)
        # entry_ref_date is uniform within a cohort (prices captured same day)
        eref = rows[0]["entry_ref_date"] if rows else cdate
        age = (today - datetime.strptime(eref, "%Y-%m-%d").date()).days
        long_rets, short_rets, veto_asif = [], [], []
        lines = []
        for r in rows:
            sym, side = r["symbol"], r["entry_side"]
            entry, cur = r.get("entry_ref_price"), price.get(r["symbol"])
            if not entry or not cur:
                lines.append(f"| {sym} | {side} | {entry or '—'} | {cur or '—'} | — | "
                             f"{r.get('regime') or '—'} | {r.get('aligned')} | "
                             f"{'VETO' if r['gated_out'] else 'enter'} |")
                continue
            ret = signed_return(side, entry, cur)
            marks.append({"run": today.isoformat(), "cohort": cdate, "mode": cmode,
                          "symbol": sym, "side": side, "entry_ref": entry, "current": cur,
                          "return": round(ret, 4), "age_days": age,
                          "gated_out": r["gated_out"], "aligned": r.get("aligned"),
                          "reaction_pct": r.get("reaction_pct")})
            if r["gated_out"]:
                # as-if we HAD shorted it: positive return here = veto missed a winner;
                # negative = veto dodged a loser.
                veto_asif.append((sym, ret))
            elif side == "long":
                long_rets.append((sym, ret)); all_signal.append((cmode, r, ret))
            else:
                short_rets.append((sym, ret)); all_signal.append((cmode, r, ret))
            tag = "VETO" if r["gated_out"] else "enter"
            lines.append(f"| {sym} | {side} | {entry:.2f} | {cur:.2f} | {ret*100:+.1f}% | "
                         f"{r.get('regime') or '—'} | {r.get('aligned')} | {tag} |")

        out.append(f"## Cohort {cdate} [{cmode}] — age {age}d ({horizon_label(age)})")
        we = c["would_enter"]
        out.append(f"- would-enter: {len(we['longs'])} long ({', '.join(we['longs']) or '—'}), "
                   f"{len(we['shorts'])} short ({', '.join(we['shorts']) or '—'}); "
                   f"vetoed: {', '.join(we['shorts_vetoed_by_gate']) or '—'}")
        out.append("")
        out.append("| Symbol | Side | Entry | Current | Return | Regime | Aligned | Decision |")
        out.append("|---|---|---:|---:|---:|---|:-:|:-:|")
        out += lines
        out.append("")
        lb = mean(r for _, r in long_rets) if long_rets else None
        sb = mean(r for _, r in short_rets) if short_rets else None
        parts = []
        if lb is not None:
            parts.append(f"long basket **{lb*100:+.1f}%** (n={len(long_rets)})")
        if sb is not None:
            parts.append(f"short basket **{sb*100:+.1f}%** (n={len(short_rets)})")
        if lb is not None and sb is not None:
            parts.append(f"combined **{(lb+sb)/2*100:+.1f}%** | spread **{(lb+sb)*100:+.1f}pp**")
        if parts:
            out.append("- " + "  |  ".join(parts))
        if veto_asif:
            dodged = [s for s, r in veto_asif if r < 0]
            out.append(f"- **Gate value:** vetoed " +
                       ", ".join(f"{s} (as-if-short {r*100:+.1f}%)" for s, r in veto_asif) +
                       f" → veto dodged {len(dodged)}/{len(veto_asif)} losers")
        out.append("")

    # ---- cross-cohort aggregates, broken out by entry mode (pre vs post/PEAD) ----
    out.append("## Cross-cohort aggregates (all entered signals, by entry mode)")
    modes_present = sorted({m for m, _, _ in all_signal})
    for mode in modes_present:
        sig = [(r, ret) for m, r, ret in all_signal if m == mode]
        label = "pre (enter before print)" if mode == "pre" else "post/PEAD (enter after print)"
        out.append(f"### {label} — n={len(sig)}")
        for b in ("aligned", "neutral", "fighting"):
            xs = [ret for r, ret in sig if r.get("aligned") == b]
            if xs:
                out.append(f"- **{b}**: avg {mean(xs)*100:+.1f}% (n={len(xs)})")
        longs = [ret for r, ret in sig if r["entry_side"] == "long"]
        shorts = [ret for r, ret in sig if r["entry_side"] == "short"]
        if longs:
            out.append(f"- all longs: avg {mean(longs)*100:+.1f}% (n={len(longs)})")
        if shorts:
            out.append(f"- all shorts (entered): avg {mean(shorts)*100:+.1f}% (n={len(shorts)})")
        if longs or shorts:
            allr = longs + shorts
            out.append(f"- **mode expectancy: {mean(allr)*100:+.1f}%/name** "
                       f"(win rate {sum(1 for x in allr if x > 0)}/{len(allr)})")
        out.append("")
    # gate scorecard across cohorts
    all_veto = []
    for c in cohorts:
        for r in c["candidates"]:
            if r.get("gated_out") and r.get("entry_side") and r.get("entry_ref_price") \
                    and price.get(r["symbol"]):
                all_veto.append((r["symbol"],
                                 signed_return(r["entry_side"], r["entry_ref_price"], price[r["symbol"]])))
    if all_veto:
        dodged = [s for s, r in all_veto if r < 0]
        out.append(f"- **Gate scorecard:** {len(dodged)}/{len(all_veto)} vetoed names would have lost "
                   f"on their vetoed side (avg as-if {mean(r for _, r in all_veto)*100:+.1f}%). "
                   f"Negative = veto correctly dodged a loser.")
    out.append("")
    out.append("_Marks are signal returns (entry-ref vs current price; no borrow/slippage). "
               "Each run appends a dated snapshot to marks.jsonl — read the mark nearest each "
               "target horizon (T+5/14/30/90) for the clean per-horizon series._")

    report = "\n".join(out)
    print(report)

    if not args.no_marks and marks:
        mpath = cdir / "marks.jsonl"
        with mpath.open("a") as f:
            for m in marks:
                f.write(json.dumps(m) + "\n")
        print(f"\nAppended {len(marks)} marks to {mpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
