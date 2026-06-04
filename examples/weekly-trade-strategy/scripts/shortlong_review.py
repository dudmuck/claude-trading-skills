#!/usr/bin/env python3
"""Shortlong paper experiment — periodic readout (T+5 / T+14 / T+30 / T+90).

Pulls current positions from the shortlong Alpaca paper account (PA3TN7BDDHLZ),
computes per-name and basket-level P/L vs entry, fits a Markov regime model on
each name (via the markov-hedge-fund-method script), and appends a dated readout
section to the experiment record. Analysis only — never places or modifies orders.

The ranker score + key flags for each name are embedded below (from the
2026-05-26 entry) so the output puts realized return next to the flags that
predicted it — making the "which flags worked" correlation easy to eyeball.
The Markov columns (regime / signal / aligned / sticky) add a regime-alignment
veto layer: positions fighting a sticky opposing regime get flagged.

Usage:
    export APCA_API_KEY_ID_SHORTLONG=... APCA_API_SECRET_KEY_SHORTLONG=...
    python3 ~/shortlong_review.py --label T+5
    python3 ~/shortlong_review.py --label T+14
    python3 ~/shortlong_review.py --label T+30 --record ~/shortlong_paper_2026-05-26.md
    python3 ~/shortlong_review.py --label T+5 --no-append    # print only, don't write
    python3 ~/shortlong_review.py --label T+5 --skip-markov  # skip Markov (faster)
    python3 ~/shortlong_review.py --label T+30 --with-coach  # add trade-performance-coach review
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://paper-api.alpaca.markets"
# External tool paths — env-overridable, Path.home()-based (no hardcoded username,
# required for the public repo). markov-hedge-fund-method is a separate repo.
MARKOV_SCRIPT = Path(os.environ.get(
    "MARKOV_REGIME_SCRIPT",
    Path.home() / "src/markov-hedge-fund-method/scripts/markov_regime.py"))
COACH_SCRIPT = Path(os.environ.get(
    "TRADE_COACH_SCRIPT",
    Path.home() / "src/claude-trading-skills/skills/"
    "trade-performance-coach/scripts/review_trade_performance.py"))

# Entry reference: ticker -> (intended_side, ranker_score, key_flag).
# NTAP was substituted live for PSTG (not tradable on Alpaca).
ENTRY_META = {
    # longs
    "HEI":  ("long", 9, "EPS+34% FCF+40% 43%-of-range pullback"),
    "TCOM": ("long", 9, "EPS+89% EV/EBITDA 5x +62% upside"),
    "MDB":  ("long", 9, "Rev+23% EPS+49% FCF+315%"),
    "PDD":  ("long", 8, "FCF-yield 11.7% EV/EBITDA 6x ROIC 18%"),
    "ADSK": ("long", 8, "FCF+60% ROIC 19% +40% upside"),
    # shorts
    "CRDO": ("short", 12, "EV/EBITDA 112x FCF 0.7% 100%-of-range beta 3.2"),
    "MRVL": ("short", 10, "EV/EBITDA 38x near-high beta 2.3"),
    "NTAP": ("short", 8,  "PEG 2.5 (substitute for PSTG)"),
    "BMO":  ("short", 9,  "EV/EBITDA 36x -42.8% analyst upside"),
    "HPE":  ("short", 8,  "EV/EBITDA 35x PEG 3.3 -14.8% upside"),
}


def _api(path):
    key = os.environ.get("APCA_API_KEY_ID_SHORTLONG")
    secret = os.environ.get("APCA_API_SECRET_KEY_SHORTLONG")
    if not key or not secret:
        sys.exit("Set APCA_API_KEY_ID_SHORTLONG and APCA_API_SECRET_KEY_SHORTLONG in env.")
    req = urllib.request.Request(
        BASE + path,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fit_markov(symbol: str) -> dict | None:
    """Run the markov-hedge-fund-method script on a ticker; return summary dict.

    Returns None on any failure (yfinance fetch, script error, JSON parse).
    Sequential calls take ~5-15s each; the caller parallelizes.
    """
    if not MARKOV_SCRIPT.is_file():
        return None
    try:
        r = subprocess.run(
            ["uv", "run", str(MARKOV_SCRIPT), "--ticker", symbol, "--json"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            return None
        # The script prints JSON to stdout (uv may print install logs to stderr).
        # Locate the first '{' to be safe.
        buf = r.stdout
        i = buf.find("{")
        if i < 0:
            return None
        d = json.loads(buf[i:])
        cur = d.get("current_regime", "?")
        pers_diag = d.get("persistence_diagonal", {})
        # Persistence of CURRENT regime (the "how sticky is where we are"):
        cur_pers = pers_diag.get(cur.lower())
        return {
            "regime": cur,
            "signal": d.get("signal"),
            "current_persistence": cur_pers,
            "stationary_bull": d.get("stationary_distribution", {}).get("bull"),
            "stationary_bear": d.get("stationary_distribution", {}).get("bear"),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def regime_alignment(side: str, regime: str) -> str:
    """Return ✓ / ○ / ✗ based on whether the position bias matches the regime.

    long + Bull -> ✓, short + Bear -> ✓, anything + Sideways -> ○ (neutral),
    long + Bear or short + Bull -> ✗ (fighting regime).
    """
    if regime == "Sideways":
        return "○"
    if side == "long" and regime == "Bull":
        return "✓"
    if side == "short" and regime == "Bear":
        return "✓"
    return "✗"


# Synthetic risk anchors: the ranker doesn't define stops or targets, so we use
# 8% as the implied stop distance (matches the "%-of-52w-range" tolerance the
# ranker uses) and 15% as the target. Realized R is computed against the 8%.
SYNTHETIC_STOP_PCT = 0.08
SYNTHETIC_TARGET_PCT = 0.15


def _coach_single_trade_record(row: dict, traded_against_regime: bool, label: str) -> dict:
    """Build a single_trade record matching the trade-performance-coach schema.

    We treat each checkpoint as a hypothetical mark-to-market close so the coach
    can score each open position as-if-exited-today. The coach's findings then
    surface what the open position would look like to a process-review lens.
    """
    side = row["side"]
    entry, cur = row["entry"], row["cur"]
    if side == "long":
        stop = entry * (1 - SYNTHETIC_STOP_PCT)
        target = entry * (1 + SYNTHETIC_TARGET_PCT)
        outcome = "gain" if cur > entry else "loss"
    else:
        stop = entry * (1 + SYNTHETIC_STOP_PCT)
        target = entry * (1 - SYNTHETIC_TARGET_PCT)
        outcome = "gain" if cur < entry else "loss"
    realized_r = abs(row["uplpc"]) / (SYNTHETIC_STOP_PCT * 100)  # vs 8% stop
    return {
        "schema_version": 1,
        "review_type": "single_trade",
        "trade_id": f"shortlong_{label.replace('+', 'plus')}_{row['sym']}_{side}",
        "ticker": row["sym"],
        "outcome": outcome,
        "planned": {
            "thesis": row["flag"] or "ranker candidate",
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "risk_r": 1.0,
            "thesis_recorded_before_entry": True,
            "setup_confirmed": True,
            "market_regime": "allowed",
        },
        "actual": {
            "entry": round(entry, 2),
            "exit": round(cur, 2),
            "risk_r": round(realized_r, 2),
            "portfolio_heat_r": 10.0,  # 10 equal-weight positions = ~10R peak
            "stop_moved": False,
            "entry_before_confirmation": False,
            "traded_against_regime": traded_against_regime,
        },
        "risk_plan": {
            "max_risk_per_trade_r": 1.0,
            "max_portfolio_heat_r": 10.0,
        },
        "postmortem": {
            "root_cause": "thesis_played_out" if outcome == "gain" else "thesis_not_yet_proven",
            "notes": [
                f"Mark-to-market readout at {label}; position still open in PA3TN7BDDHLZ.",
            ],
        },
        "journal": {
            "reflection": f"Ranker score {row['score']}; flags: {row['flag']}",
            "emotions": [],
        },
    }


def _coach_aggregate_record(rows: list[dict], fighting_sticky: list[str], label: str) -> dict:
    """Build a monthly_aggregate record for basket-level coach review."""
    losing = [r["sym"] for r in rows
              if (r["side"] == "long" and r["cur"] < r["entry"])
              or (r["side"] == "short" and r["cur"] > r["entry"])]
    return {
        "schema_version": 1,
        "review_type": "monthly_aggregate",
        "trade_id": f"shortlong_basket_{label.replace('+', 'plus')}",
        "outcome": "mixed",
        "planned": {
            "thesis_recorded_before_entry": True,
            "setup_confirmed": True,
            "market_regime": "allowed",
        },
        "actual": {
            "risk_r": 1.0,
            "portfolio_heat_r": float(len(rows)),
            "stop_moved": False,
            "entry_before_confirmation": False,
            "traded_against_regime": len(fighting_sticky) > 0,
        },
        "risk_plan": {
            "max_risk_per_trade_r": 1.0,
            "max_portfolio_heat_r": 10.0,
        },
        "monthly": {
            "trades": sorted(r["sym"] for r in rows),
            "consecutive_losses": 0,  # intra-period bookkeeping — N/A here
            "rule_violations": len(fighting_sticky),
        },
        "postmortem": {
            "root_cause": "regime_fight" if fighting_sticky else "execution",
            "notes": [
                f"{len(losing)}/{len(rows)} names underwater at {label}: "
                f"{', '.join(losing) or 'none'}.",
                f"Names fighting sticky opposing regime: "
                f"{', '.join(fighting_sticky) or 'none'}.",
            ],
        },
        "journal": {
            "reflection": f"{label} basket readout; ranker spread tracked in main table.",
            "emotions": [],
        },
    }


def run_coach(record: dict, tmpdir: Path) -> dict | None:
    """Write record to tmp JSON and call review_trade_performance.py; parse JSON."""
    if not COACH_SCRIPT.is_file():
        return None
    rec_path = tmpdir / f"{record['trade_id']}.json"
    rec_path.write_text(json.dumps(record))
    try:
        r = subprocess.run(
            [sys.executable, str(COACH_SCRIPT), "--input", str(rec_path), "--stdout"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return None
        # Script may emit a warning line before JSON when given multi-input
        # (we always pass single input here, but be defensive).
        buf = r.stdout
        i = buf.find("{")
        if i < 0:
            return None
        return json.loads(buf[i:])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True, help="Checkpoint label, e.g. T+5 / T+14 / T+30 / T+90")
    p.add_argument("--record", default=str(Path.home() / "shortlong_paper_2026-05-26.md"),
                   help="Experiment record markdown to append to")
    p.add_argument("--no-append", action="store_true", help="Print only; do not write to the record")
    p.add_argument("--skip-markov", action="store_true",
                   help="Skip the Markov regime fit per name (faster — saves ~60-90s)")
    p.add_argument("--with-coach", action="store_true",
                   help="Run trade-performance-coach on each name + basket "
                        "(auto-on at T+30 and T+90; off otherwise)")
    args = p.parse_args()

    # Auto-enable coach for the deeper checkpoints unless the user explicitly opted out
    # via --with-coach=False (argparse doesn't support that, but --skip-markov sets the
    # convention; for coach we just default-on at T+30/T+90).
    if args.label.upper() in ("T+30", "T+90"):
        args.with_coach = True

    acct = _api("/v2/account")
    positions = _api("/v2/positions")
    today = date.today().isoformat()

    # Fit Markov for each held symbol in parallel (~5-15s each sequentially,
    # ~15-30s wall-clock with 4 workers). Skip cleanly if --skip-markov or if
    # any individual fit fails.
    markov_by_sym: dict[str, dict | None] = {}
    if not args.skip_markov:
        symbols = [p["symbol"] for p in positions]
        print(f"Fitting Markov on {len(symbols)} symbols (parallel) ...", file=sys.stderr)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            results = dict(zip(symbols, ex.map(fit_markov, symbols)))
        markov_by_sym = results
        ok = sum(1 for v in results.values() if v is not None)
        print(f"  Markov ok for {ok}/{len(symbols)} symbols", file=sys.stderr)

    # Build rows from live positions (avg_entry_price + unrealized_pl are Alpaca-tracked).
    rows = []
    long_pl = short_pl = long_cost = short_cost = 0.0
    held = set()
    for pos in positions:
        sym = pos["symbol"]
        held.add(sym)
        side = pos["side"]  # 'long' or 'short'
        qty = abs(float(pos["qty"]))
        entry = float(pos["avg_entry_price"])
        cur = float(pos["current_price"])
        upl = float(pos["unrealized_pl"])
        uplpc = float(pos["unrealized_plpc"]) * 100
        cost = entry * qty
        meta = ENTRY_META.get(sym, ("?", 0, ""))
        m = markov_by_sym.get(sym) if not args.skip_markov else None
        rows.append({
            "sym": sym, "side": side, "score": meta[1], "flag": meta[2],
            "qty": qty, "entry": entry, "cur": cur, "upl": upl, "uplpc": uplpc,
            "regime": m["regime"] if m else None,
            "signal": m["signal"] if m else None,
            "cur_pers": m["current_persistence"] if m else None,
            "aligned": regime_alignment(side, m["regime"]) if m else None,
        })
        if side == "long":
            long_pl += upl; long_cost += cost
        else:
            short_pl += upl; short_cost += cost

    # Flag any expected name that's no longer held (e.g., closed/halted).
    missing = [s for s in ENTRY_META if s not in held]

    long_ret = (long_pl / long_cost * 100) if long_cost else 0.0
    short_ret = (short_pl / short_cost * 100) if short_cost else 0.0
    net_pl = long_pl + short_pl
    spread = long_ret + short_ret  # both positive = ranker alpha on both legs

    # Mark each row as "fighting a sticky opposing regime" — used by both the
    # Markov-alignment summary and the coach's traded_against_regime input.
    for r in rows:
        r["against_sticky"] = bool(
            r.get("aligned") == "✗" and r.get("cur_pers") and r["cur_pers"] >= 0.80
        )
    sticky_opposed = [r["sym"] for r in rows if r["against_sticky"]]

    # ---- Render ----
    lines = []
    lines.append(f"## {args.label} Review ({today})")
    lines.append("")
    lines.append(f"- Account equity: **${float(acct['equity']):,.2f}** "
                 f"(baseline $100,000 → {float(acct['equity'])-100000:+,.2f})")
    lines.append(f"- Long basket P/L: **${long_pl:+,.2f}** ({long_ret:+.2f}% on ${long_cost:,.0f} cost)")
    lines.append(f"- Short basket P/L: **${short_pl:+,.2f}** ({short_ret:+.2f}% on ${short_cost:,.0f} cost)")
    lines.append(f"- **Net strategy P/L: ${net_pl:+,.2f}**  |  ranker spread (long%+short%): **{spread:+.2f}pp**")
    if missing:
        lines.append(f"- ⚠ No longer held (check for close/halt/corp-action): {', '.join(missing)}")
    lines.append("")
    if args.skip_markov:
        lines.append("| Symbol | Side | Score | Entry | Current | P/L $ | P/L % | Key flag |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|")
        for r in sorted(rows, key=lambda x: (x["side"], -x["score"])):
            lines.append(
                f"| {r['sym']} | {r['side']} | {r['score']} | {r['entry']:.2f} | {r['cur']:.2f} "
                f"| {r['upl']:+,.0f} | {r['uplpc']:+.1f}% | {r['flag']} |"
            )
    else:
        lines.append("| Symbol | Side | Score | Entry | Current | P/L $ | P/L % | Regime | Sig | Sticky | Aligned | Key flag |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|---:|---:|:-:|---|")
        for r in sorted(rows, key=lambda x: (x["side"], -x["score"])):
            reg = r['regime'] or "—"
            sig = f"{r['signal']:+.2f}" if r['signal'] is not None else "—"
            pers = f"{r['cur_pers']*100:.0f}%" if r['cur_pers'] is not None else "—"
            aligned = r['aligned'] or "—"
            lines.append(
                f"| {r['sym']} | {r['side']} | {r['score']} | {r['entry']:.2f} | {r['cur']:.2f} "
                f"| {r['upl']:+,.0f} | {r['uplpc']:+.1f}% | {reg} | {sig} | {pers} | {aligned} | {r['flag']} |"
            )

        # Regime-alignment summary
        aligned_count = sum(1 for r in rows if r['aligned'] == "✓")
        neutral_count = sum(1 for r in rows if r['aligned'] == "○")
        opposed_count = sum(1 for r in rows if r['aligned'] == "✗")
        lines.append("")
        lines.append(f"- Regime alignment: **{aligned_count}/{len(rows)} aligned** "
                     f"(✓), {neutral_count} neutral (○ Sideways), {opposed_count} fighting regime (✗)")
        if sticky_opposed:
            lines.append(f"- ⚠ Fighting **sticky** opposing regime (persistence ≥ 80%): "
                         f"{', '.join(sticky_opposed)}")

    # ---- Coach review (optional; default-on at T+30/T+90) ----
    if args.with_coach and COACH_SCRIPT.is_file():
        print(f"Running trade-performance-coach on {len(rows)} names + basket ...",
              file=sys.stderr)
        with tempfile.TemporaryDirectory(prefix="shortlong-coach-") as td:
            tmpdir = Path(td)
            # Per-name single_trade reviews
            per_name = []
            for r in rows:
                rec = _coach_single_trade_record(r, r["against_sticky"], args.label)
                rep = run_coach(rec, tmpdir)
                per_name.append((r, rep))
            # Basket monthly_aggregate review
            agg_rec = _coach_aggregate_record(rows, sticky_opposed, args.label)
            agg_rep = run_coach(agg_rec, tmpdir)

        ok = sum(1 for _, rep in per_name if rep is not None)
        print(f"  Coach ok for {ok}/{len(per_name)} names + "
              f"{'basket' if agg_rep else 'no basket'}", file=sys.stderr)

        lines.append("")
        lines.append(f"### Coach review (single-trade per name + monthly-aggregate basket)")
        lines.append("")
        lines.append("| Symbol | Outcome | Verdict | Proc | Risk | Exec | Behavior tags |")
        lines.append("|---|---|---|---:|---:|---:|---|")
        for r, rep in sorted(per_name, key=lambda x: (x[0]["side"], -x[0]["score"])):
            if rep is None:
                lines.append(f"| {r['sym']} | — | (coach failed) | — | — | — | — |")
                continue
            sc = rep["scores"]
            tags = ", ".join(t["tag"] for t in rep["behavioral_pattern_tags"]
                             if t["tag"] != "no_pattern_detected") or "—"
            lines.append(
                f"| {r['sym']} | {rep['summary']['outcome']} | {rep['overall_verdict']} "
                f"| {sc['process_score']} | {sc['risk_score']} | {sc['execution_score']} | {tags} |"
            )

        if agg_rep:
            lines.append("")
            lines.append("**Basket aggregate (monthly_aggregate):**")
            sc = agg_rep["scores"]
            lines.append(f"- Verdict: **{agg_rep['overall_verdict']}** "
                         f"(process {sc['process_score']} / risk {sc['risk_score']} / "
                         f"execution {sc['execution_score']})")
            if agg_rep["behavioral_pattern_tags"]:
                tags = [t for t in agg_rep["behavioral_pattern_tags"]
                        if t["tag"] != "no_pattern_detected"]
                if tags:
                    lines.append("- Behavior pattern tags:")
                    for t in tags:
                        lines.append(f"  - `{t['tag']}` ({t['confidence']}): {t['evidence']}")
            if agg_rep["next_session_operating_rules"]:
                lines.append("- Operating rules for next checkpoint:")
                for rule in agg_rep["next_session_operating_rules"]:
                    lines.append(f"  - **{rule['rule']}** — _{rule['reason']}_")
            if agg_rep["coach_questions"]:
                lines.append("- Coach questions to journal:")
                for q in agg_rep["coach_questions"]:
                    lines.append(f"  - {q}")

    lines.append("")
    lines.append("_Interpretation notes (fill in manually / with Claude): which flags "
                 "(valuation EV/EBITDA, growth, analyst-upside, crowding) tracked realized "
                 "return? Did regime alignment correlate with realized P/L? Earnings-driven "
                 "outliers?_")
    lines.append("")
    out = "\n".join(lines)

    print(out)

    if not args.no_append:
        rec = Path(args.record)
        if not rec.is_file():
            print(f"\nWARNING: record {rec} not found; printed only.", file=sys.stderr)
            return
        with rec.open("a", encoding="utf-8") as f:
            f.write("\n" + out)
        print(f"\nAppended {args.label} section to {rec}", file=sys.stderr)


if __name__ == "__main__":
    main()
