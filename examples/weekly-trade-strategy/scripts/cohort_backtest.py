#!/usr/bin/env python3
"""Historical backtest for the earnings long/short cohort strategy (FMP Premium).

Replays weekly earnings cohorts over multiple years and measures the questions the
forward test would otherwise take quarters to answer:

  1. POST/PEAD edge: enter AFTER the print, side = reaction direction
     (>= +R% long drift, <= -R% short drift). Expectancy at T+5/14/30 trading days.
  2. Markov gate value: does vetoing shorts that fight a sticky Bull regime
     (20d/±5% labeling, MLE transition matrix, persistence >= 0.80 — the exact
     markov-hedge-fund-method observable model, re-implemented natively for speed)
     improve the short book across hundreds of events?
  3. PRE-entry binary noise floor: the |print reaction| distribution quantifies the
     event risk a pre-earnings entry takes on (the reason for the PEAD pivot).
  4. Reaction x valuation/crowding interactions (point-in-time quarterly ratios with
     a 45-day reporting lag + monthly analyst-grade snapshots).

Survivorship: candidates come from the HISTORICAL earnings calendar + historical
market cap as-of each week (not today's universe). Names with revenueActual >=
$1.5B/qtr are kept even if absent from today's screener (delisting-proof fallback).

Data is cached to disk (--cache-dir), so re-runs are free and FMP Premium can be
cancelled after the initial fetch. Requires FMP Premium for: historical earnings
calendar, quarterly key-metrics/ratios, grades-historical depth.

Usage:
    export FMP_API_KEY=...
    python3 cohort_backtest.py --from 2023-07-03 --to 2026-05-25            # full run
    python3 cohort_backtest.py --from 2025-01-06 --to 2025-03-31 --smoke    # quick window
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median

FMP_BASE = "https://financialmodelingprep.com/stable"
SYM_RE = re.compile(r"^[A-Z]{1,5}$")          # drop OTC/foreign suffixed tickers
HORIZONS = (5, 14, 30)                         # trading days after entry
MARKOV_WINDOW, MARKOV_THRESHOLD = 20, 0.05     # match markov_regime.py defaults
REPORT_LAG_DAYS = 45                           # quarterly fundamentals known ~45d after period end


# ----------------------------------------------------------------- FMP + cache
class Fetcher:
    def __init__(self, cache_dir: Path, rate_per_min: int = 600):
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.min_interval = 60.0 / rate_per_min
        self._last = 0.0
        self.calls = 0
        key = os.environ.get("FMP_API_KEY")
        if not key:
            sys.exit("Set FMP_API_KEY")
        self.key = key

    def get(self, tag: str, endpoint: str, **params):
        """Cached GET. tag is the cache filename stem."""
        f = self.cache / f"{tag}.json"
        if f.exists():
            return json.loads(f.read_text())
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = f"{FMP_BASE}/{endpoint}?" + urllib.parse.urlencode({**params, "apikey": self.key})
        self._last = time.time()
        self.calls += 1
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.load(r)
        except Exception as e:
            print(f"    fetch FAIL {tag}: {e}", file=sys.stderr)
            data = None
        if data is not None:
            f.write_text(json.dumps(data))
        return data


# ------------------------------------------------------------- Markov (native)
def markov_gate(closes: list[float], persistence_gate: float) -> dict:
    """Replicates markov_regime.py's observable model on a close series ending at
    the entry date: 20d rolling-return labels (Bull/Sideways/Bear), MLE transition
    matrix, current regime + its persistence. Returns gate inputs."""
    n = len(closes)
    if n < 300:  # ~min_train 252 + window; not enough history -> gate unknown
        return {"regime": None, "persistence": None, "veto_short": False, "known": False}
    labels = []
    for i in range(MARKOV_WINDOW, n):
        r = closes[i] / closes[i - MARKOV_WINDOW] - 1.0
        labels.append(2 if r > MARKOV_THRESHOLD else 0 if r < -MARKOV_THRESHOLD else 1)
    counts = [[0.0] * 3 for _ in range(3)]
    for a, b in zip(labels, labels[1:]):
        counts[a][b] += 1.0
    cur = labels[-1]
    row = counts[cur]
    tot = sum(row)
    pers = (row[cur] / tot) if tot else None
    regime = ("Bear", "Sideways", "Bull")[cur]
    veto = regime == "Bull" and pers is not None and pers >= persistence_gate
    return {"regime": regime, "persistence": pers, "veto_short": veto, "known": True}


def alignment(side: str, regime: str | None) -> str:
    if regime is None:
        return "unknown"
    if regime == "Sideways":
        return "neutral"
    if (side == "long" and regime == "Bull") or (side == "short" and regime == "Bear"):
        return "aligned"
    return "fighting"


# ------------------------------------------------------------------ Px helpers
class PxSeries:
    """Sorted (date, close) lists with binary-search-free index lookups."""
    def __init__(self, rows: list[dict]):
        pairs = sorted({(r["date"], r["price"]) for r in rows if r.get("price")})
        self.dates = [p[0] for p in pairs]
        self.closes = [p[1] for p in pairs]

    def idx_last_before(self, d: str) -> int | None:
        """Index of last trading day strictly before date d."""
        lo = -1
        for i, dt in enumerate(self.dates):       # series are ~2.5k long; linear is fine cached
            if dt < d:
                lo = i
            else:
                break
        return lo if lo >= 0 else None

    def idx_first_after(self, d: str) -> int | None:
        for i, dt in enumerate(self.dates):
            if dt > d:
                return i
        return None


def fwd_return(px: PxSeries, entry_idx: int, horizon: int, side: str) -> float | None:
    j = entry_idx + horizon
    if j >= len(px.closes):
        return None
    raw = px.closes[j] / px.closes[entry_idx] - 1.0
    return raw if side == "long" else -raw


# ----------------------------------------------------------- point-in-time fdm
def latest_row_before(rows: list[dict], cutoff: str, lag_days: int = 0) -> dict | None:
    """Latest quarterly/monthly row whose date + lag <= cutoff (reporting lag)."""
    best = None
    for r in rows or []:
        d = (r.get("date") or "")[:10]
        if not d:
            continue
        eff = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=lag_days)).strftime("%Y-%m-%d")
        if eff <= cutoff and (best is None or d > best.get("date", "")[:10]):
            best = r
    return best


# ------------------------------------------------------------------------ main
def mondays(d_from: str, d_to: str):
    d = datetime.strptime(d_from, "%Y-%m-%d").date()
    d += timedelta(days=(7 - d.weekday()) % 7)  # advance to a Monday
    end = datetime.strptime(d_to, "%Y-%m-%d").date()
    while d <= end:
        yield d
        d += timedelta(days=7)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from", dest="d_from", default="2023-07-03",
                   help="First cohort Monday (default 2023-07-03 — grades history starts 2023-07).")
    p.add_argument("--to", dest="d_to", default="2026-05-25",
                   help="Last cohort Monday (default 2026-05-25 — leaves room for T+30 exits).")
    p.add_argument("--min-mcap", type=float, default=20e9)
    p.add_argument("--min-reaction", type=float, default=3.0)
    p.add_argument("--gate-persistence", type=float, default=0.80)
    p.add_argument("--cache-dir", default=str(Path.home() / "shortlong_cohorts/backtest_cache"))
    p.add_argument("--out-dir", default=str(Path.home() / "shortlong_cohorts/backtest"))
    p.add_argument("--smoke", action="store_true", help="Skip fundamentals annotations (faster smoke run).")
    args = p.parse_args()

    fx = Fetcher(Path(args.cache_dir).expanduser())
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    px_from = (datetime.strptime(args.d_from, "%Y-%m-%d") - timedelta(days=365 * 7)).strftime("%Y-%m-%d")
    px_to = (datetime.strptime(args.d_to, "%Y-%m-%d") + timedelta(days=80)).strftime("%Y-%m-%d")

    # Current screener: cheap first-pass trim only (final filter is HISTORICAL mcap).
    scr = fx.get("screener_1b", "company-screener",
                 marketCapMoreThan=1_000_000_000, isActivelyTrading="true", limit=10000) or []
    in_screener = {r["symbol"] for r in scr
                   if not r.get("isEtf") and not r.get("isFund") and r.get("symbol")}
    print(f"screener first-pass: {len(in_screener)} names >= $1B today", file=sys.stderr)

    px_cache: dict[str, PxSeries] = {}
    mcap_cache: dict[str, list] = {}

    def get_px(sym: str) -> PxSeries | None:
        if sym not in px_cache:
            rows = []
            # chunk by ~4y (observed ~1010-row responses suggest range limits)
            f0 = datetime.strptime(px_from, "%Y-%m-%d").date()
            end = datetime.strptime(px_to, "%Y-%m-%d").date()
            while f0 < end:
                f1 = min(f0 + timedelta(days=365 * 4), end)
                chunk = fx.get(f"px_{sym}_{f0.year}", "historical-price-eod/light",
                               symbol=sym, **{"from": f0.isoformat(), "to": f1.isoformat()})
                rows += chunk or []
                f0 = f1 + timedelta(days=1)
            px_cache[sym] = PxSeries(rows) if rows else None
        return px_cache[sym]

    def mcap_asof(sym: str, d: str) -> float | None:
        if sym not in mcap_cache:
            mcap_cache[sym] = fx.get(f"mcap_{sym}", "historical-market-capitalization",
                                     symbol=sym, **{"from": args.d_from, "to": args.d_to,
                                                    "limit": 5000}) or []
        best = None
        for r in mcap_cache[sym]:
            if r["date"] <= d and (best is None or r["date"] > best["date"]):
                best = r
        return best["marketCap"] if best else None

    results = []           # one row per (week, symbol) event
    weeks = list(mondays(args.d_from, args.d_to))
    print(f"replaying {len(weeks)} weeks {weeks[0]} .. {weeks[-1]}", file=sys.stderr)

    for wi, W in enumerate(weeks, 1):
        wfrom, wto = W.isoformat(), (W + timedelta(days=6)).isoformat()
        cal = fx.get(f"cal_{wfrom}", "earnings-calendar", **{"from": wfrom, "to": wto}) or []
        # one calendar row per symbol (prefer the one with actuals)
        rows = {}
        for r in cal:
            s = r.get("symbol") or ""
            if not SYM_RE.match(s):
                continue
            if s not in rows or (r.get("epsActual") is not None
                                 and rows[s].get("epsActual") is None):
                rows[s] = r
        # candidate trim: in today's screener OR big reported revenue (delisting-proof)
        cands = [s for s, r in rows.items()
                 if r.get("epsActual") is not None
                 and (s in in_screener or (r.get("revenueActual") or 0) >= 1.5e9)]
        kept = 0
        for s in cands:
            if (mcap_asof(s, wfrom) or 0) < args.min_mcap:
                continue
            r = rows[s]
            rep = r["date"][:10]
            px = get_px(s)
            if not px or not px.dates:
                continue
            i_pre = px.idx_last_before(rep)
            i_post = px.idx_first_after(rep)
            if i_pre is None or i_post is None or i_post >= len(px.closes):
                continue
            reaction = (px.closes[i_post] / px.closes[i_pre] - 1.0) * 100
            side = ("long" if reaction >= args.min_reaction
                    else "short" if reaction <= -args.min_reaction else None)
            gate = markov_gate(px.closes[: i_post + 1], args.gate_persistence)
            rec = {
                "week": wfrom, "symbol": s, "report_date": rep,
                "reaction_pct": round(reaction, 2),
                "side": side,
                "regime": gate["regime"], "persistence": gate["persistence"],
                "gate_known": gate["known"],
                "vetoed": bool(side == "short" and gate["veto_short"]),
                "aligned": alignment(side, gate["regime"]) if side else None,
                "mcap": mcap_asof(s, wfrom),
            }
            for h in HORIZONS:
                rec[f"ret_{h}"] = fwd_return(px, i_post, h, side) if side else None
                # pre-entry counterfactual: enter at last close before the print,
                # long side (the market's base rate), to quantify the binary
                rec[f"pre_long_ret_{h}"] = fwd_return(px, i_pre, h, "long")
            if not args.smoke:
                cutoff = wfrom
                ratios = latest_row_before(
                    fx.get(f"ratios_{s}", "ratios", symbol=s, period="quarter", limit=14),
                    cutoff, REPORT_LAG_DAYS)
                grades = latest_row_before(
                    fx.get(f"grades_{s}", "grades-historical", symbol=s, limit=40), cutoff)
                rec["pe"] = ratios.get("priceToEarningsRatio") if ratios else None
                rec["peg"] = ratios.get("priceToEarningsGrowthRatio") if ratios else None
                if grades:
                    nb = (grades.get("analystRatingsStrongBuy") or 0) + (grades.get("analystRatingsBuy") or 0)
                    ns = (grades.get("analystRatingsSell") or 0) + (grades.get("analystRatingsStrongSell") or 0)
                    nh = grades.get("analystRatingsHold") or 0
                    rec["crowded_long"] = bool((nb + nh + ns) >= 10 and ns == 0 and nb > nh)
                else:
                    rec["crowded_long"] = None
            results.append(rec)
            kept += 1
        print(f"  [{wi}/{len(weeks)}] {wfrom}: {len(cands)} reported, {kept} kept "
              f"(calls so far {fx.calls})", file=sys.stderr)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    raw_path = out_dir / f"backtest_events_{ts}.jsonl"
    with raw_path.open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    report = analyze(results, args)
    rep_path = out_dir / f"backtest_report_{ts}.md"
    rep_path.write_text(report)
    print(report)
    print(f"\nevents: {raw_path}\nreport: {rep_path}\nFMP calls this run: {fx.calls}", file=sys.stderr)


# -------------------------------------------------------------------- analysis
def _stats(xs: list[float]) -> str:
    if not xs:
        return "n=0"
    wins = sum(1 for x in xs if x > 0)
    return (f"n={len(xs)}, mean {mean(xs)*100:+.2f}%, median {median(xs)*100:+.2f}%, "
            f"win {wins}/{len(xs)} ({wins/len(xs)*100:.0f}%)")


def analyze(results: list[dict], args) -> str:
    o = [f"# Cohort backtest — {args.d_from} .. {args.d_to}",
         "",
         f"- Events (reported large-caps >= ${args.min_mcap/1e9:.0f}B): **{len(results)}**",
         f"- Post/PEAD side rule: |print reaction| >= {args.min_reaction}%  | "
         f"Gate: veto shorts in Bull regime with persistence >= {args.gate_persistence}",
         ""]
    sided = [r for r in results if r["side"]]
    o.append(f"## 1. POST/PEAD expectancy (entered after the print; n={len(sided)} sided events)")
    for side in ("long", "short"):
        o.append(f"### {side}s (reaction {'>= +' if side=='long' else '<= -'}{args.min_reaction}%)")
        grp = [r for r in sided if r["side"] == side]
        entered = [r for r in grp if not r["vetoed"]] if side == "short" else grp
        for h in HORIZONS:
            xs = [r[f"ret_{h}"] for r in entered if r.get(f"ret_{h}") is not None]
            o.append(f"- T+{h}: {_stats(xs)}")
        o.append("")

    o.append("## 2. Markov gate value (post-mode shorts)")
    shorts = [r for r in sided if r["side"] == "short" and r["gate_known"]]
    for label, grp in (("VETOED (sticky Bull) — as-if-shorted", [r for r in shorts if r["vetoed"]]),
                       ("passed gate — entered", [r for r in shorts if not r["vetoed"]])):
        o.append(f"### {label}")
        for h in HORIZONS:
            xs = [r[f"ret_{h}"] for r in grp if r.get(f"ret_{h}") is not None]
            o.append(f"- T+{h}: {_stats(xs)}")
        o.append("")

    o.append("## 3. Regime alignment (entered names, all sides)")
    for b in ("aligned", "neutral", "fighting"):
        for h in (14,):
            xs = [r[f"ret_{h}"] for r in sided
                  if not r["vetoed"] and r.get("aligned") == b and r.get(f"ret_{h}") is not None]
            o.append(f"- {b} @T+14: {_stats(xs)}")
    o.append("")

    o.append("## 4. Reaction-magnitude gradient (T+14, entered)")
    for side in ("long", "short"):
        for lo, hi in ((args.min_reaction, 5), (5, 10), (10, 1000)):
            xs = [r["ret_14"] for r in sided
                  if r["side"] == side and not r["vetoed"] and r.get("ret_14") is not None
                  and lo <= abs(r["reaction_pct"]) < hi]
            o.append(f"- {side} |rx| {lo}-{hi if hi < 1000 else '+'}%: {_stats(xs)}")
    o.append("")

    o.append("## 5. PRE-entry binary noise floor (every reported large-cap)")
    rx = [abs(r["reaction_pct"]) for r in results]
    if rx:
        big = sum(1 for x in rx if x >= 5)
        o.append(f"- |print reaction|: mean {mean(rx):.1f}%, median {median(rx):.1f}%, "
                 f">=5% in {big}/{len(rx)} ({big/len(rx)*100:.0f}%) of events")
        for h in HORIZONS:
            xs = [r[f"pre_long_ret_{h}"] for r in results if r.get(f"pre_long_ret_{h}") is not None]
            o.append(f"- enter LONG before every print (base rate), T+{h}: {_stats(xs)}")
    o.append("")

    annotated = [r for r in sided if r.get("peg") is not None]
    if annotated:
        o.append("## 6. Reaction x valuation interaction (T+14, entered)")
        for side in ("long", "short"):
            grp = [r for r in annotated if r["side"] == side and not r["vetoed"]
                   and r.get("ret_14") is not None]
            rich = [r["ret_14"] for r in grp if (r.get("peg") or 0) >= 2]
            cheap = [r["ret_14"] for r in grp if 0 < (r.get("peg") or -1) < 1]
            o.append(f"- {side} + rich (PEG>=2): {_stats(rich)}")
            o.append(f"- {side} + cheap (0<PEG<1): {_stats(cheap)}")
        o.append("")

    o.append("## 7. By year (T+14, entered, all sides)")
    years = sorted({r["week"][:4] for r in sided})
    for y in years:
        xs = [r["ret_14"] for r in sided
              if r["week"].startswith(y) and not r["vetoed"] and r.get("ret_14") is not None]
        o.append(f"- {y}: {_stats(xs)}")
    o.append("")
    o.append("_Signal returns (close-to-close, no slippage/borrow). Gate + regimes fit "
             "point-in-time on price history ending at entry. Fundamentals use a "
             f"{REPORT_LAG_DAYS}-day reporting lag; analyst grades are monthly snapshots._")
    return "\n".join(o)


if __name__ == "__main__":
    main()
