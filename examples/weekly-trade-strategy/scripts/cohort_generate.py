#!/usr/bin/env python3
"""Weekly forward-test cohort generator — earnings long/short strategy + Markov gate.

Each run logs a dated "would-enter" cohort (long + gated-short candidates) with
entry-reference prices, so a tracker can mark them to market at T+5/14/30/90 and
we accumulate the statistical evidence needed before risking real cash. This is a
SIGNAL test (reference-price marking), deliberately free of execution noise — no
paper orders are placed.

FMP-efficient pipeline (the mcap pre-filter is the key optimization):
  1. earnings-calendar [date, date+7d]                 -> 1 FMP call
  2. company-screener marketCapMoreThan=min_mcap        -> 1 FMP call  (pre-filter)
  3. intersect: reporting AND >= mcap, drop ETFs/funds  -> ~20-50 names, each
     already tagged with marketCap/sector/industry/beta from the screener
  4. rank_earnings_candidates.py on that subset          -> 7 calls x survivors
  5. Markov regime fit per candidate + SPY               -> 0 FMP (yfinance)
  6. short-side Markov gate (veto sticky Bull)           -> the T+5-validated rule
  7. write cohort_YYYY-MM-DD.{json,md}

Total ~150-280 FMP calls vs ~800 unoptimized (the ~660-call profile loop is gone).

Usage:
    export FMP_API_KEY=...
    python3 ~/cohort_generate.py --date 2026-06-08
    python3 ~/cohort_generate.py --date 2026-06-08 --min-mcap 20e9 --top 10 \
        --gate-persistence 0.80 --out-dir ~/shortlong_cohorts
    python3 ~/cohort_generate.py --date 2026-06-08 --dry-run   # don't write cohort files
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FMP_BASE = "https://financialmodelingprep.com/stable"
US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX"}


def _resolve_ranker() -> Path:
    """rank_earnings_candidates.py — env override, else sibling (repo copy),
    else the canonical repo location (so a $HOME convenience copy still works)."""
    env = os.environ.get("RANK_EARNINGS_SCRIPT")
    if env:
        return Path(env)
    sibling = Path(__file__).resolve().parent / "rank_earnings_candidates.py"
    if sibling.is_file():
        return sibling
    return (Path.home() / "src/claude-trading-skills/examples/weekly-trade-strategy"
            / "scripts/rank_earnings_candidates.py")


# markov_regime.py lives in the separate markov-hedge-fund-method repo; env-overridable.
RANKER = _resolve_ranker()
MARKOV = Path(os.environ.get(
    "MARKOV_REGIME_SCRIPT",
    Path.home() / "src/markov-hedge-fund-method/scripts/markov_regime.py"))


# ----------------------------------------------------------------------------- FMP
def _fmp(endpoint: str, params: dict) -> list | dict:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        sys.exit("Set FMP_API_KEY environment variable.")
    params = {**params, "apikey": key}
    url = f"{FMP_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=40) as r:
        return json.load(r)


def fetch_earnings_symbols(start: str, end: str) -> list[str]:
    """earnings-calendar -> unique symbols reporting in [start, end]. 1 FMP call."""
    rows = _fmp("earnings-calendar", {"from": start, "to": end})
    syms = {row.get("symbol") for row in rows if row.get("symbol")}
    print(f"  earnings-calendar: {len(rows)} rows, {len(syms)} unique symbols", file=sys.stderr)
    return sorted(syms)


def fetch_largecap_universe(min_mcap: float) -> dict[str, dict]:
    """company-screener -> {symbol: {marketCap, sector, industry, beta, ...}}.

    ONE call replaces the ~660-call per-symbol profile loop. Post-filters to US
    common stock (drops ETFs/funds and non-US exchanges).
    """
    rows = _fmp("company-screener", {
        "marketCapMoreThan": int(min_mcap),
        "isActivelyTrading": "true",
        "limit": 5000,
    })
    uni = {}
    for r in rows:
        if r.get("isEtf") or r.get("isFund"):
            continue
        if (r.get("exchangeShortName") or "").upper() not in US_EXCHANGES:
            continue
        sym = r.get("symbol")
        if sym:
            uni[sym] = r
    print(f"  company-screener: {len(rows)} rows >= ${min_mcap/1e9:.0f}B -> "
          f"{len(uni)} US common-stock names", file=sys.stderr)
    return uni


# -------------------------------------------------------------------------- Markov
def fit_markov(symbol: str) -> dict | None:
    """uv run markov_regime.py --ticker SYM --json. Returns summary or None."""
    if not MARKOV.is_file():
        return None
    try:
        r = subprocess.run(
            ["uv", "run", str(MARKOV), "--ticker", symbol, "--json"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            return None
        i = r.stdout.find("{")
        if i < 0:
            return None
        d = json.loads(r.stdout[i:])
        if "current_regime" not in d:
            return None
        reg = d["current_regime"]
        return {
            "regime": reg,
            "signal": d.get("signal"),
            "persistence": d.get("persistence_diagonal", {}).get(reg.lower()),
            "stationary_bull": d.get("stationary_distribution", {}).get("bull"),
            "stationary_bear": d.get("stationary_distribution", {}).get("bear"),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def alignment(side: str, regime: str | None) -> str:
    if regime is None:
        return "?"
    if regime == "Sideways":
        return "neutral"
    if side == "long" and regime == "Bull":
        return "aligned"
    if side == "short" and regime == "Bear":
        return "aligned"
    return "fighting"


# ----------------------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", required=True, help="Cohort/window-start date YYYY-MM-DD (e.g. upcoming Monday).")
    p.add_argument("--window-days", type=int, default=7, help="Earnings window length (default 7).")
    p.add_argument("--min-mcap", type=float, default=20e9, help="Market-cap floor (default 20e9 = $20B).")
    p.add_argument("--top", type=int, default=10, help="Top N per bias (default 10).")
    p.add_argument("--max-names", type=int, default=40, help="Hard cap on names the ranker fundamentals-fetches.")
    p.add_argument("--gate-persistence", type=float, default=0.80,
                   help="Short candidate is vetoed if in a Bull regime with persistence >= this (default 0.80).")
    p.add_argument("--min-score", type=int, default=6,
                   help="Min bias score for a name to be a would-enter candidate (default 6).")
    p.add_argument("--side-margin", type=int, default=2,
                   help="A name enters a side only if that side's score beats the other by >= this (default 2). "
                        "Prevents a name landing on both lists; ambiguous names are dropped from would-enter.")
    p.add_argument("--out-dir", default=str(Path.home() / "shortlong_cohorts"))
    p.add_argument("--dry-run", action="store_true", help="Print summary; do not write cohort files.")
    args = p.parse_args()

    d0 = datetime.strptime(args.date, "%Y-%m-%d").date()
    d1 = d0 + timedelta(days=args.window_days)
    print(f"Cohort {d0} (earnings window {d0} -> {d1}, mcap >= ${args.min_mcap/1e9:.0f}B)", file=sys.stderr)

    fmp_calls = 0
    # 1 + 2: the cheap pre-filter
    earnings_syms = fetch_earnings_symbols(args.date, d1.isoformat()); fmp_calls += 1
    universe = fetch_largecap_universe(args.min_mcap); fmp_calls += 1

    # 3: intersect -> ranker-compatible earnings rows (each carrying marketCap)
    keep = [s for s in earnings_syms if s in universe]
    print(f"  intersect: {len(keep)} names reporting AND >= mcap (pre-filter saved "
          f"~{len(earnings_syms)-len(keep)} profile calls)", file=sys.stderr)
    if not keep:
        sys.exit("No large-cap names reporting in the window — nothing to rank.")
    enriched = [{"symbol": s, "marketCap": universe[s].get("marketCap")} for s in keep]

    # 4: run the ranker (subprocess, JSON) on the pre-filtered set
    with tempfile.TemporaryDirectory(prefix="cohort-") as td:
        tmp = Path(td)
        (tmp / "earnings.json").write_text(json.dumps(enriched))
        cand_path = tmp / "candidates.json"
        print(f"  ranking {min(len(keep), args.max_names)} names "
              f"(~{min(len(keep), args.max_names)*7} FMP calls)...", file=sys.stderr)
        rr = subprocess.run([sys.executable, str(RANKER),
                             "--earnings-json", str(tmp / "earnings.json"),
                             "--min-mcap", str(args.min_mcap),
                             "--top", str(args.max_names),  # ALL scored names (each carries both scores)
                             "--max-names", str(args.max_names),
                             "--bias", "both", "--format", "json",
                             "--output", str(cand_path)],
                            capture_output=True, text=True)
        if rr.returncode != 0 or not cand_path.is_file():
            sys.exit(f"Ranker failed:\n{rr.stderr[-1500:]}")
        ranked = json.loads(cand_path.read_text())
    fmp_calls += min(len(keep), args.max_names) * 7  # ranker fundamentals estimate

    # Each ranker record carries BOTH long_score and short_score, so unioning the
    # two bias lists by symbol gives full per-name data in one pass.
    by_sym = {}
    for c in ranked.get("short_candidates", []) + ranked.get("long_candidates", []):
        by_sym.setdefault(c["fundamentals"]["symbol"], c)

    # 5: Markov on every candidate symbol + SPY (free, parallel)
    syms = sorted(set(by_sym) | {"SPY"})
    print(f"  Markov fitting {len(syms)} symbols (parallel)...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        markov = dict(zip(syms, ex.map(fit_markov, syms)))
    ok = sum(1 for v in markov.values() if v)
    print(f"  Markov ok {ok}/{len(syms)}", file=sys.stderr)
    spy = markov.get("SPY")

    # 6: per-symbol record — side assignment (min-score + margin) then short-side gate.
    def build(c: dict) -> dict:
        f = c["fundamentals"]
        sym = f["symbol"]
        m = markov.get(sym) or {}
        reg, pers = m.get("regime"), m.get("persistence")
        ls, ss = c["long_score"], c["short_score"]
        # Assign at most one side: clear winner by margin AND clears the min-score floor.
        side = None
        if ls >= args.min_score and ls - ss >= args.side_margin:
            side = "long"
        elif ss >= args.min_score and ss - ls >= args.side_margin:
            side = "short"
        gated_out, gate_reason = False, ""
        if side == "short" and reg == "Bull" and isinstance(pers, (int, float)) \
                and pers >= args.gate_persistence:
            gated_out = True
            gate_reason = f"sticky Bull (persistence {pers*100:.0f}% >= {args.gate_persistence*100:.0f}%)"
        return {
            "symbol": sym, "long_score": ls, "short_score": ss,
            "entry_side": side,
            "entry_flags": (c["long_flags"] if side == "long"
                            else c["short_flags"] if side == "short" else []),
            "entry_ref_price": f.get("price"),
            "entry_ref_date": date.today().isoformat(),  # when prices were actually captured
            "sector": f.get("sector"), "market_cap": f.get("market_cap"),
            "regime": reg, "signal": m.get("signal"), "persistence": pers,
            "aligned": alignment(side, reg) if side else "—",
            "gated_out": gated_out, "gate_reason": gate_reason,
        }

    records = sorted((build(c) for c in by_sym.values()),
                     key=lambda r: -max(r["long_score"], r["short_score"]))
    enter_longs = sorted([r for r in records if r["entry_side"] == "long"],
                         key=lambda r: -r["long_score"])[: args.top]
    enter_shorts = sorted([r for r in records if r["entry_side"] == "short" and not r["gated_out"]],
                          key=lambda r: -r["short_score"])[: args.top]
    vetoed = [r["symbol"] for r in records if r["entry_side"] == "short" and r["gated_out"]]

    cohort = {
        "cohort_date": args.date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"from": args.date, "to": d1.isoformat()},
        "params": {
            "min_mcap": args.min_mcap, "top": args.top, "max_names": args.max_names,
            "min_score": args.min_score, "side_margin": args.side_margin,
            "gate": f"short-side: veto Bull regime with persistence >= {args.gate_persistence}",
        },
        "spy_regime": spy,
        "fmp_calls_estimate": fmp_calls,
        "names_reporting": len(earnings_syms),
        "names_after_prefilter": len(keep),
        "candidates": records,
        "would_enter": {
            "longs": [r["symbol"] for r in enter_longs],
            "shorts": [r["symbol"] for r in enter_shorts],
            "shorts_vetoed_by_gate": vetoed,
        },
    }

    # 7: render + write
    md = render_md(cohort)
    print("\n" + md)
    if args.dry_run:
        print("\n[dry-run] no files written.", file=sys.stderr)
        return
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"cohort_{args.date}.json").write_text(json.dumps(cohort, indent=2, default=str))
    (out_dir / f"cohort_{args.date}.md").write_text(md)
    print(f"\nWrote {out_dir}/cohort_{args.date}.{{json,md}}  "
          f"(~{fmp_calls} FMP calls)", file=sys.stderr)


def _row(r: dict) -> str:
    sig = f"{r['signal']:+.2f}" if isinstance(r.get("signal"), (int, float)) else "—"
    pers = f"{r['persistence']*100:.0f}%" if isinstance(r.get("persistence"), (int, float)) else "—"
    px = f"{r['entry_ref_price']:.2f}" if isinstance(r.get("entry_ref_price"), (int, float)) else "—"
    if r["entry_side"] is None:
        decision = "— (no edge / ambiguous)"
    elif r["gated_out"]:
        decision = f"**SHORT→VETO** ({r['gate_reason']})"
    else:
        decision = f"**{r['entry_side'].upper()}**"
    flags = "; ".join(r["entry_flags"][:3]) if r.get("entry_flags") else "-"
    return (f"| {r['symbol']} | {r['long_score']} | {r['short_score']} | {px} "
            f"| {r.get('regime') or '—'} | {sig} | {pers} | {r['aligned']} | {decision} | {flags} |")


def render_md(c: dict) -> str:
    spy = c.get("spy_regime") or {}
    spy_str = (f"{spy.get('regime')} sig {spy.get('signal'):+.2f} "
               f"sticky {spy.get('persistence', 0)*100:.0f}%") if spy else "n/a"
    we = c["would_enter"]
    o = []
    o.append(f"# Cohort {c['cohort_date']} — earnings long/short + Markov gate")
    o.append("")
    o.append(f"- Window: {c['window']['from']} → {c['window']['to']}  | mcap floor "
             f"${c['params']['min_mcap']/1e9:.0f}B  | SPY regime: **{spy_str}**")
    o.append(f"- Pre-filter: {c['names_reporting']} reporting → {c['names_after_prefilter']} large-cap "
             f"(~{c['fmp_calls_estimate']} FMP calls)")
    o.append(f"- Side rule: enter a side only if its score ≥ {c['params']['min_score']} AND beats the "
             f"other side by ≥ {c['params']['side_margin']}. Gate: {c['params']['gate']}")
    o.append(f"- **Would-enter:** {len(we['longs'])} longs "
             f"({', '.join(we['longs']) or '—'}); {len(we['shorts'])} shorts "
             f"({', '.join(we['shorts']) or '—'})")
    if we["shorts_vetoed_by_gate"]:
        o.append(f"- **Gate vetoed shorts:** {', '.join(we['shorts_vetoed_by_gate'])} "
                 f"(would-enter ex-gate, blocked by sticky-Bull rule)")
    o.append("")
    o.append("## All ranked candidates (Lng / Sht = both bias scores; Decision = assigned side after gate)")
    o.append("| Symbol | Lng | Sht | Entry ref | Regime | Sig | Sticky | Aligned | Decision | Key flags |")
    o.append("|---|---:|---:|---:|---|---:|---:|:-:|:--|---|")
    o += [_row(r) for r in c["candidates"]]
    o.append("")
    o.append("_Forward-test cohort: would-enter names are logged at entry-ref price for mark-to-market "
             "at T+5/14/30/90 (no paper order placed). The short-side gate encodes the T+5 finding that "
             "shorting into a sticky Bull regime is a losing trade. Ambiguous/low-conviction names are "
             "logged but excluded from would-enter._")
    return "\n".join(o)


if __name__ == "__main__":
    main()
