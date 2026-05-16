#!/usr/bin/env python3
"""Rank this week's earnings names as long/short candidates worth deeper review.

Pipeline:
  1. Read an earnings JSON (default /tmp/wk0511/earnings.json), filter by mcap.
  2. Pull a lightweight FMP fundamentals subset per symbol (quote, profile,
     key-metrics-ttm, ratios-ttm, financial-growth, price-target-consensus,
     grades-consensus). Reuses fmp_get / _first from fmp_stock_snapshot.py.
  3. Score each name on a short-bias composite (over-valuation, crowding) and
     a long-bias composite (growth quality, reasonable valuation, upside).
  4. Output the top-N for the chosen bias as markdown or JSON.

The output is a triage list, not a recommendation — you still drill into
each name with fmp_stock_snapshot.py + chart_ticker.py + the bear/bull
writeup pipeline.

Usage:
    export FMP_API_KEY=...
    python rank_earnings_candidates.py                                # default earnings.json, both biases, top 10 each
    python rank_earnings_candidates.py --bias short --top 15
    python rank_earnings_candidates.py --earnings-json /tmp/wk0511/earnings.json --min-mcap 50e9 --bias long
    python rank_earnings_candidates.py --format json --output /tmp/wk0511/candidates.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Sibling module — same scripts/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fmp_stock_snapshot import _first, fmp_get  # noqa: E402


def fetch_fundamentals(symbol: str, api_key: str) -> dict:
    """Lightweight subset of the full snapshot — 7 endpoints, ~0.7s per name."""
    sym = symbol.upper()
    quote = _first(fmp_get("quote", {"symbol": sym}, api_key))
    profile = _first(fmp_get("profile", {"symbol": sym}, api_key))
    km = _first(fmp_get("key-metrics-ttm", {"symbol": sym}, api_key))
    ratios = _first(fmp_get("ratios-ttm", {"symbol": sym}, api_key))
    growth = _first(fmp_get("financial-growth", {"symbol": sym, "limit": 1}, api_key))
    target = _first(fmp_get("price-target-consensus", {"symbol": sym}, api_key))
    grades = _first(fmp_get("grades-consensus", {"symbol": sym}, api_key))

    spot = quote.get("price")
    yh = quote.get("yearHigh")
    yl = quote.get("yearLow")
    range_pct = None
    if spot and yh and yl and yh != yl:
        range_pct = (spot - yl) / (yh - yl) * 100

    target_avg = target.get("targetConsensus") if target else None
    implied_upside_pct = None
    if spot and target_avg:
        implied_upside_pct = (target_avg / spot - 1) * 100

    n_buy = (grades.get("strongBuy", 0) or 0) + (grades.get("buy", 0) or 0) if grades else 0
    n_sell = (grades.get("sell", 0) or 0) + (grades.get("strongSell", 0) or 0) if grades else 0
    n_hold = (grades.get("hold", 0) or 0) if grades else 0
    n_total = n_buy + n_hold + n_sell

    return {
        "symbol": sym,
        "name": profile.get("companyName"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "price": spot,
        "market_cap": quote.get("marketCap") or profile.get("marketCap"),
        "beta": profile.get("beta"),
        "year_range_pct": range_pct,
        "pe_ttm": quote.get("pe"),
        "ev_to_sales": km.get("evToSalesTTM"),
        "ev_to_ebitda": km.get("evToEBITDATTM"),
        "ev_to_fcf": km.get("evToFreeCashFlowTTM"),
        "peg": ratios.get("priceToEarningsGrowthRatioTTM"),
        "fcf_yield": km.get("freeCashFlowYieldTTM"),
        "earnings_yield": km.get("earningsYieldTTM"),
        "roe": km.get("returnOnEquityTTM"),
        "roic": km.get("returnOnInvestedCapitalTTM"),
        "operating_margin": ratios.get("operatingProfitMarginTTM"),
        "sbc_to_revenue": km.get("stockBasedCompensationToRevenueTTM"),
        "revenue_growth_1y": growth.get("revenueGrowth"),
        "eps_growth_1y": growth.get("epsgrowth"),
        "fcf_growth_1y": growth.get("freeCashFlowGrowth"),
        "target_avg": target_avg,
        "implied_upside_pct": implied_upside_pct,
        "n_buy": n_buy,
        "n_hold": n_hold,
        "n_sell": n_sell,
        "n_total": n_total,
        "rating_consensus": grades.get("consensus") if grades else None,
    }


def _ge(v, threshold):
    """Safe >= for None values."""
    return isinstance(v, (int, float)) and v >= threshold


def _le(v, threshold):
    return isinstance(v, (int, float)) and v <= threshold


def short_score(f: dict) -> tuple[int, list[str]]:
    """Higher = more attractive short candidate. Returns (score, flags)."""
    score = 0
    flags = []

    if _ge(f.get("ev_to_ebitda"), 50):
        score += 3; flags.append(f"EV/EBITDA {f['ev_to_ebitda']:.0f}x (extreme)")
    elif _ge(f.get("ev_to_ebitda"), 25):
        score += 2; flags.append(f"EV/EBITDA {f['ev_to_ebitda']:.0f}x (rich)")
    elif _ge(f.get("ev_to_ebitda"), 15):
        score += 1

    if _ge(f.get("peg"), 2):
        score += 2; flags.append(f"PEG {f['peg']:.1f} (rich vs growth)")
    elif _ge(f.get("peg"), 1):
        score += 1

    if _le(f.get("fcf_yield"), 0.02):
        score += 2; flags.append(f"FCF yield {f['fcf_yield']*100:.1f}% (sub-2%)")
    elif _le(f.get("fcf_yield"), 0.04):
        score += 1

    if _ge(f.get("year_range_pct"), 85):
        score += 2; flags.append(f"{f['year_range_pct']:.0f}% of 52w range (near high)")
    elif _ge(f.get("year_range_pct"), 70):
        score += 1

    if _ge(f.get("beta"), 1.5):
        score += 1; flags.append(f"Beta {f['beta']:.1f} (high)")

    if _le(f.get("implied_upside_pct"), 0):
        score += 2; flags.append(f"Analyst upside {f['implied_upside_pct']:.1f}% (priced through)")
    elif _le(f.get("implied_upside_pct"), 5):
        score += 1

    # Crowded long: many Buys, zero Sells, decent sample
    if f.get("n_total", 0) >= 10 and f.get("n_sell", 0) == 0 and f.get("n_buy", 0) > f.get("n_hold", 0):
        score += 1; flags.append(f"{f['n_buy']}B/{f['n_hold']}H/0S (crowded long, downgrade risk)")

    if _ge(f.get("sbc_to_revenue"), 0.05):
        score += 1; flags.append(f"SBC {f['sbc_to_revenue']*100:.1f}% rev (dilution)")

    # Negative ERP (FCF yield < 10Y proxy ~4.4%)
    if isinstance(f.get("fcf_yield"), (int, float)) and f["fcf_yield"] < 0.044:
        flags.append("Negative ERP vs 10Y")

    return score, flags


def long_score(f: dict) -> tuple[int, list[str]]:
    """Higher = more attractive long candidate. Returns (score, flags)."""
    score = 0
    flags = []

    if _ge(f.get("revenue_growth_1y"), 0.20):
        score += 2; flags.append(f"Rev growth {f['revenue_growth_1y']*100:.0f}% (strong)")
    elif _ge(f.get("revenue_growth_1y"), 0.10):
        score += 1

    if _ge(f.get("eps_growth_1y"), 0.30):
        score += 2; flags.append(f"EPS growth {f['eps_growth_1y']*100:.0f}% (strong)")
    elif _ge(f.get("eps_growth_1y"), 0.15):
        score += 1

    if _ge(f.get("fcf_growth_1y"), 0.20):
        score += 1; flags.append(f"FCF growth {f['fcf_growth_1y']*100:.0f}%")

    if _ge(f.get("fcf_yield"), 0.05):
        score += 2; flags.append(f"FCF yield {f['fcf_yield']*100:.1f}% (>10Y)")
    elif _ge(f.get("fcf_yield"), 0.03):
        score += 1

    # Reasonable valuation given growth
    if _le(f.get("ev_to_ebitda"), 15) and isinstance(f.get("ev_to_ebitda"), (int, float)):
        score += 1; flags.append(f"EV/EBITDA {f['ev_to_ebitda']:.0f}x (cheap)")
    elif _le(f.get("ev_to_ebitda"), 25):
        score += 0  # neutral

    if _ge(f.get("roic"), 0.15):
        score += 2; flags.append(f"ROIC {f['roic']*100:.0f}% (high quality)")
    elif _ge(f.get("roic"), 0.10):
        score += 1

    # Pullback territory — not at highs, not at lows
    if isinstance(f.get("year_range_pct"), (int, float)) and 40 <= f["year_range_pct"] <= 70:
        score += 1; flags.append(f"{f['year_range_pct']:.0f}% of 52w range (pullback)")

    if _ge(f.get("implied_upside_pct"), 15):
        score += 2; flags.append(f"Analyst upside {f['implied_upside_pct']:.1f}% (>15%)")
    elif _ge(f.get("implied_upside_pct"), 5):
        score += 1

    if _ge(f.get("operating_margin"), 0.20):
        score += 1; flags.append(f"Op margin {f['operating_margin']*100:.0f}%")

    return score, flags


def render_table(rows: list[dict], bias: str) -> str:
    """Markdown ranked table for one bias."""
    if not rows:
        return f"_No {bias} candidates ranked._\n"
    score_key = f"{bias}_score"
    out = []
    out.append(f"## Top {bias.title()} Candidates")
    out.append("")
    out.append(f"| # | Symbol | Name | Sector | Mcap | Score | Key flags |")
    out.append(f"|---:|---|---|---|---:|---:|---|")
    for i, r in enumerate(rows, 1):
        f = r["fundamentals"]
        mcap = f.get("market_cap")
        mcap_str = (
            f"${mcap/1e12:.1f}T" if mcap and mcap >= 1e12
            else f"${mcap/1e9:.0f}B" if mcap else "n/a"
        )
        name = (f.get("name") or "")[:30]
        flags = r[f"{bias}_flags"]
        flag_str = "; ".join(flags[:4]) if flags else "-"
        out.append(
            f"| {i} | **{f['symbol']}** | {name} | {f.get('sector') or '-'} "
            f"| {mcap_str} | {r[score_key]} | {flag_str} |"
        )
    return "\n".join(out) + "\n"


def render_markdown(short_rows: list[dict], long_rows: list[dict],
                    earnings_path: str, mcap_floor: float, total_screened: int,
                    skipped: int) -> str:
    out = []
    out.append(f"# Earnings-Week Candidate Ranking")
    out.append("")
    out.append(f"- Source: `{earnings_path}`")
    out.append(f"- Mcap floor: ${mcap_floor/1e9:.0f}B")
    out.append(f"- Names screened: {total_screened} ({skipped} skipped due to missing data)")
    out.append("")
    out.append("Scores are heuristic composites — high score = strong fit for the bias. "
               "Verify each candidate with `fmp_stock_snapshot.py` + `chart_ticker.py` before acting.")
    out.append("")
    if short_rows:
        out.append(render_table(short_rows, "short"))
        out.append("")
    if long_rows:
        out.append(render_table(long_rows, "long"))
        out.append("")
    out.append("## Scoring rubric")
    out.append("")
    out.append("**Short bias** (each adds 1-3 points): EV/EBITDA > 25/50, PEG > 1/2, "
               "FCF yield < 4%/2%, % of 52w range > 70%/85%, beta > 1.5, "
               "analyst implied upside < 5%/0%, crowded long (0 Sells, mostly Buys), "
               "stock-based-comp > 5% of revenue.")
    out.append("")
    out.append("**Long bias** (each adds 1-2 points): revenue growth > 10%/20%, "
               "EPS growth > 15%/30%, FCF growth > 20%, FCF yield > 3%/5%, "
               "ROIC > 10%/15%, EV/EBITDA < 15, % of 52w range 40-70% (pullback), "
               "analyst implied upside > 5%/15%, op margin > 20%.")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--earnings-json", default="/tmp/wk0511/earnings.json",
                   help="Path to earnings JSON from fetch_earnings_fmp.py.")
    p.add_argument("--min-mcap", type=float, default=10e9,
                   help="Minimum market cap to consider (default: 10e9 = $10B).")
    p.add_argument("--top", type=int, default=10,
                   help="Top N per bias to output (default: 10).")
    p.add_argument("--bias", choices=("short", "long", "both"), default="both")
    p.add_argument("--format", choices=("md", "json"), default="md")
    p.add_argument("--output", help="Output path (default: stdout).")
    p.add_argument("--max-names", type=int, default=60,
                   help="Hard cap on names to fetch (default: 60 to bound runtime).")
    args = p.parse_args()

    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        sys.exit("Set FMP_API_KEY environment variable.")

    earnings_path = Path(args.earnings_json)
    if not earnings_path.is_file():
        sys.exit(f"Earnings JSON not found: {earnings_path}")
    earnings = json.loads(earnings_path.read_text(encoding="utf-8"))

    # Filter: mcap floor + dedupe by symbol (some sources list same name twice
    # for ADR / dual class).
    seen = set()
    candidates = []
    for row in earnings:
        sym = row.get("symbol")
        mcap = row.get("marketCap") or 0
        if not sym or sym in seen or mcap < args.min_mcap:
            continue
        seen.add(sym)
        candidates.append(row)

    # Sort by mcap descending and cap.
    candidates.sort(key=lambda r: -(r.get("marketCap") or 0))
    candidates = candidates[: args.max_names]
    print(f"Screening {len(candidates)} names from {earnings_path.name} "
          f"(mcap >= ${args.min_mcap/1e9:.0f}B)...", file=sys.stderr)

    results = []
    skipped = 0
    for i, c in enumerate(candidates, 1):
        sym = c["symbol"]
        try:
            f = fetch_fundamentals(sym, api_key)
        except Exception as e:
            print(f"  [{i}/{len(candidates)}] {sym}: skipped ({e})", file=sys.stderr)
            skipped += 1
            continue
        # Need at least price + ev_to_ebitda + revenue_growth to score meaningfully
        if not (f.get("price") and f.get("ev_to_ebitda") is not None
                and f.get("revenue_growth_1y") is not None):
            print(f"  [{i}/{len(candidates)}] {sym}: skipped (sparse data)", file=sys.stderr)
            skipped += 1
            continue
        s_score, s_flags = short_score(f)
        l_score, l_flags = long_score(f)
        results.append({
            "fundamentals": f,
            "short_score": s_score,
            "short_flags": s_flags,
            "long_score": l_score,
            "long_flags": l_flags,
        })
        if i % 10 == 0 or i == len(candidates):
            print(f"  [{i}/{len(candidates)}] done", file=sys.stderr)

    # Sort and pick top N per bias.
    short_rows = (
        sorted(results, key=lambda r: -r["short_score"])[: args.top]
        if args.bias in ("short", "both") else []
    )
    long_rows = (
        sorted(results, key=lambda r: -r["long_score"])[: args.top]
        if args.bias in ("long", "both") else []
    )

    if args.format == "json":
        payload = {
            "earnings_source": str(earnings_path),
            "min_mcap": args.min_mcap,
            "screened": len(results),
            "skipped": skipped,
            "short_candidates": short_rows,
            "long_candidates": long_rows,
        }
        text = json.dumps(payload, indent=2, default=str)
    else:
        text = render_markdown(
            short_rows, long_rows, str(earnings_path),
            args.min_mcap, len(results), skipped,
        )

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


if __name__ == "__main__":
    main()
