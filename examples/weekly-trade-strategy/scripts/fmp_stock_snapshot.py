#!/usr/bin/env python3
"""Pull a one-page valuation + positioning snapshot for a single ticker from FMP.

Output is structured data designed to be fed into `us-stock-analysis` (or any
LLM analysis pass) so the analysis runs on hard numbers instead of WebSearch
guesses. Both JSON and markdown formats are supported.

Endpoints used (all verified working on FMP Starter tier as of 2026-05-13):
  /stable/quote                      - current price, mcap, P/E, day change
  /stable/profile                    - sector, industry, beta, dividend, exchange
  /stable/key-metrics-ttm            - EV/EBITDA, EV/Sales, ROE, FCF yield, etc.
  /stable/ratios-ttm                 - PEG, P/B, P/S, margins, debt/equity
  /stable/financial-growth?limit=1   - revenue + EPS growth (1y/3y/5y CAGR)
  /stable/income-statement?period=quarter  - last 4 quarters revenue + EPS
  /stable/analyst-estimates?period=annual  - forward year estimates
  /stable/price-target-consensus     - analyst target high/low/avg vs spot
  /stable/grades-consensus           - analyst rating distribution (B/H/S)
  /stable/grades-historical          - recent rating changes (last 10)
  /stable/shares-float               - float shares, outstanding shares

Usage:
    export FMP_API_KEY=...
    python fmp_stock_snapshot.py AMD                       # JSON to stdout
    python fmp_stock_snapshot.py AMD --format md           # markdown to stdout
    python fmp_stock_snapshot.py AMD --output amd.json
    python fmp_stock_snapshot.py AMD --format md --output amd.md
"""

import argparse
import json
import os
import sys
import time
from urllib.parse import urlencode

import requests

BASE = "https://financialmodelingprep.com/stable"
RATE_LIMIT_DELAY = 0.1  # 750/min Starter tier


def fmp_get(path: str, params: dict, api_key: str):
    """GET /stable/<path> with rate-limit pacing. Returns parsed JSON or None on
    non-200 / shape errors. Caller decides whether the field is required."""
    params = {**params, "apikey": api_key}
    url = f"{BASE}/{path}?{urlencode(params)}"
    r = requests.get(url, timeout=30)
    time.sleep(RATE_LIMIT_DELAY)
    if r.status_code != 200:
        print(f"  WARN {path}: HTTP {r.status_code}", file=sys.stderr)
        return None
    try:
        return r.json()
    except ValueError:
        print(f"  WARN {path}: non-JSON response", file=sys.stderr)
        return None


def _first(data):
    """FMP often returns single-element lists; unwrap safely."""
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


def fetch_snapshot(symbol: str, api_key: str) -> dict:
    """Pull all endpoints and assemble into a structured snapshot."""
    sym = symbol.upper()
    print(f"Fetching FMP snapshot for {sym}...", file=sys.stderr)

    quote = _first(fmp_get("quote", {"symbol": sym}, api_key))
    profile = _first(fmp_get("profile", {"symbol": sym}, api_key))
    km_ttm = _first(fmp_get("key-metrics-ttm", {"symbol": sym}, api_key))
    ratios_ttm = _first(fmp_get("ratios-ttm", {"symbol": sym}, api_key))
    growth = _first(fmp_get("financial-growth", {"symbol": sym, "limit": 1}, api_key))
    income_q = fmp_get(
        "income-statement",
        {"symbol": sym, "limit": 4, "period": "quarter"},
        api_key,
    ) or []
    estimates = fmp_get(
        "analyst-estimates", {"symbol": sym, "period": "annual"}, api_key
    ) or []
    target = _first(fmp_get("price-target-consensus", {"symbol": sym}, api_key))
    grades_cons = _first(fmp_get("grades-consensus", {"symbol": sym}, api_key))
    grades_hist = fmp_get(
        "grades-historical", {"symbol": sym, "limit": 10}, api_key
    ) or []
    float_data = _first(fmp_get("shares-float", {"symbol": sym}, api_key))

    spot = quote.get("price")
    target_avg = target.get("targetConsensus") if target else None
    implied_upside = None
    if spot and target_avg:
        implied_upside = (target_avg / spot - 1) * 100

    # Pick the next-year estimate (closest future fiscal-year-end date)
    from datetime import date as _date
    today_iso = _date.today().isoformat()
    fwd_est = None
    if estimates:
        future = sorted(
            [e for e in estimates if (e.get("date") or "") > today_iso],
            key=lambda e: e.get("date", ""),
        )
        fwd_est = future[0] if future else None

    snapshot = {
        "symbol": sym,
        "as_of": quote.get("timestamp") or quote.get("earningsAnnouncement"),
        "header": {
            "name": profile.get("companyName"),
            "exchange": profile.get("exchange"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "price": spot,
            "change_pct_day": quote.get("changePercentage"),
            "market_cap": quote.get("marketCap") or profile.get("marketCap"),
            "beta": profile.get("beta"),
            "pe_ttm": quote.get("pe"),
            "eps_ttm": quote.get("eps"),
            "year_high": quote.get("yearHigh"),
            "year_low": quote.get("yearLow"),
            "year_range_pct": (
                (spot - quote.get("yearLow")) / (quote.get("yearHigh") - quote.get("yearLow")) * 100
                if spot and quote.get("yearHigh") and quote.get("yearLow")
                and quote.get("yearHigh") != quote.get("yearLow") else None
            ),
            "shares_outstanding": float_data.get("outstandingShares"),
            "float_shares": float_data.get("floatShares"),
            "free_float_pct": float_data.get("freeFloat"),
            "next_earnings": quote.get("earningsAnnouncement"),
        },
        "valuation": {
            "pe_ttm": quote.get("pe"),
            "forward_pe": (
                spot / fwd_est.get("epsAvg") if spot and fwd_est and fwd_est.get("epsAvg") else None
            ),
            "peg": ratios_ttm.get("priceToEarningsGrowthRatioTTM"),
            "ev_to_sales": km_ttm.get("evToSalesTTM"),
            "ev_to_ebitda": km_ttm.get("evToEBITDATTM"),
            "ev_to_operating_cf": km_ttm.get("evToOperatingCashFlowTTM"),
            "ev_to_fcf": km_ttm.get("evToFreeCashFlowTTM"),
            "price_to_book": ratios_ttm.get("priceToBookRatioTTM"),
            "price_to_sales": ratios_ttm.get("priceToSalesRatioTTM"),
            "earnings_yield": km_ttm.get("earningsYieldTTM"),
            "fcf_yield": km_ttm.get("freeCashFlowYieldTTM"),
            "enterprise_value": km_ttm.get("enterpriseValueTTM"),
        },
        "profitability": {
            "gross_margin": ratios_ttm.get("grossProfitMarginTTM"),
            "operating_margin": ratios_ttm.get("operatingProfitMarginTTM"),
            "net_margin": ratios_ttm.get("netProfitMarginTTM"),
            "roe": km_ttm.get("returnOnEquityTTM"),
            "roic": km_ttm.get("returnOnInvestedCapitalTTM"),
            "roa": km_ttm.get("returnOnAssetsTTM"),
        },
        "balance_sheet": {
            "current_ratio": km_ttm.get("currentRatioTTM"),
            "debt_to_equity": ratios_ttm.get("debtToEquityRatioTTM"),
            "net_debt_to_ebitda": km_ttm.get("netDebtToEBITDATTM"),
            "interest_coverage": ratios_ttm.get("interestCoverageRatioTTM"),
        },
        "capital_allocation": {
            "rnd_to_revenue": km_ttm.get("researchAndDevelopementToRevenueTTM"),
            "capex_to_revenue": km_ttm.get("capexToRevenueTTM"),
            "capex_to_ocf": km_ttm.get("capexToOperatingCashFlowTTM"),
            "stock_based_comp_to_revenue": km_ttm.get("stockBasedCompensationToRevenueTTM"),
        },
        "growth": {
            "revenue_growth_1y": growth.get("revenueGrowth"),
            "revenue_cagr_3y_pershare": growth.get("threeYRevenueGrowthPerShare"),
            "revenue_cagr_5y_pershare": growth.get("fiveYRevenueGrowthPerShare"),
            "eps_growth_1y": growth.get("epsgrowth"),
            "eps_diluted_growth_1y": growth.get("epsdilutedGrowth"),
            "net_income_cagr_3y_pershare": growth.get("threeYNetIncomeGrowthPerShare"),
            "net_income_cagr_5y_pershare": growth.get("fiveYNetIncomeGrowthPerShare"),
            "operating_income_growth_1y": growth.get("operatingIncomeGrowth"),
            "fcf_growth_1y": growth.get("freeCashFlowGrowth"),
            "rd_expense_growth_1y": growth.get("rdexpenseGrowth"),
        },
        "recent_quarters": [
            {
                "date": q.get("date"),
                "period": q.get("period"),
                "revenue": q.get("revenue"),
                "eps_diluted": q.get("epsDiluted") or q.get("epsdiluted"),
                "operating_income": q.get("operatingIncome"),
                "net_income": q.get("netIncome"),
                "gross_margin": (
                    q.get("grossProfit") / q.get("revenue") if q.get("revenue") else None
                ),
            }
            for q in income_q
        ],
        "forward_estimate": (
            {
                "fiscal_year_end": fwd_est.get("date"),
                "revenue_avg": fwd_est.get("revenueAvg"),
                "revenue_low": fwd_est.get("revenueLow"),
                "revenue_high": fwd_est.get("revenueHigh"),
                "eps_avg": fwd_est.get("epsAvg"),
                "eps_low": fwd_est.get("epsLow"),
                "eps_high": fwd_est.get("epsHigh"),
                "num_analysts_eps": fwd_est.get("numAnalystsEstimatedEps"),
            }
            if fwd_est
            else None
        ),
        "analyst_targets": {
            "target_high": target.get("targetHigh") if target else None,
            "target_low": target.get("targetLow") if target else None,
            "target_avg": target_avg,
            "target_median": target.get("targetMedian") if target else None,
            "implied_upside_pct": implied_upside,
        },
        "rating_consensus": {
            "strong_buy": grades_cons.get("strongBuy") if grades_cons else None,
            "buy": grades_cons.get("buy") if grades_cons else None,
            "hold": grades_cons.get("hold") if grades_cons else None,
            "sell": grades_cons.get("sell") if grades_cons else None,
            "strong_sell": grades_cons.get("strongSell") if grades_cons else None,
            "consensus": grades_cons.get("consensus") if grades_cons else None,
        },
        "recent_rating_changes": [
            {
                "date": g.get("date"),
                "firm": g.get("gradingCompany"),
                "previous_grade": g.get("previousGrade"),
                "new_grade": g.get("newGrade"),
                "action": g.get("action"),
            }
            for g in grades_hist[:10]
        ],
    }
    return snapshot


def _fmt_pct(v, digits=1):
    return f"{v * 100:.{digits}f}%" if isinstance(v, (int, float)) else "n/a"


def _fmt_pct_raw(v, digits=1):
    return f"{v:.{digits}f}%" if isinstance(v, (int, float)) else "n/a"


def _fmt_num(v, digits=2):
    return f"{v:.{digits}f}" if isinstance(v, (int, float)) else "n/a"


def _fmt_money(v):
    if not isinstance(v, (int, float)):
        return "n/a"
    if abs(v) >= 1e12:
        return f"${v / 1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.2f}M"
    return f"${v:,.0f}"


def render_markdown(s: dict) -> str:
    h = s["header"]
    v = s["valuation"]
    p = s["profitability"]
    b = s["balance_sheet"]
    c = s["capital_allocation"]
    g = s["growth"]
    t = s["analyst_targets"]
    r = s["rating_consensus"]

    out = []
    out.append(f"# {s['symbol']} — {h.get('name', 'n/a')}")
    out.append("")
    out.append(f"**{h.get('exchange', '?')} | {h.get('sector', '?')} / {h.get('industry', '?')}**")
    out.append("")
    out.append(f"- Price: **${_fmt_num(h.get('price'))}** ({_fmt_num(h.get('change_pct_day'))}% today)")
    out.append(f"- Market cap: {_fmt_money(h.get('market_cap'))}  |  Beta: {_fmt_num(h.get('beta'))}")
    out.append(f"- 52w range: ${_fmt_num(h.get('year_low'))} — ${_fmt_num(h.get('year_high'))} "
               f"({_fmt_pct_raw(h.get('year_range_pct'))} of range)")
    out.append(f"- Float: {_fmt_money(h.get('float_shares'))}  |  Free float: {_fmt_pct_raw(h.get('free_float_pct'))}")
    out.append(f"- Next earnings: {h.get('next_earnings') or 'n/a'}")
    out.append("")

    out.append("## Valuation")
    out.append("")
    out.append(f"| Metric | Value |")
    out.append(f"|---|---:|")
    out.append(f"| P/E (TTM) | {_fmt_num(v.get('pe_ttm'))} |")
    out.append(f"| Forward P/E | {_fmt_num(v.get('forward_pe'))} |")
    out.append(f"| PEG | {_fmt_num(v.get('peg'))} |")
    out.append(f"| EV / Sales | {_fmt_num(v.get('ev_to_sales'))} |")
    out.append(f"| EV / EBITDA | {_fmt_num(v.get('ev_to_ebitda'))} |")
    out.append(f"| EV / Operating CF | {_fmt_num(v.get('ev_to_operating_cf'))} |")
    out.append(f"| EV / FCF | {_fmt_num(v.get('ev_to_fcf'))} |")
    out.append(f"| P / Book | {_fmt_num(v.get('price_to_book'))} |")
    out.append(f"| P / Sales | {_fmt_num(v.get('price_to_sales'))} |")
    out.append(f"| Earnings yield | {_fmt_pct(v.get('earnings_yield'))} |")
    out.append(f"| FCF yield | {_fmt_pct(v.get('fcf_yield'))} |")
    out.append(f"| Enterprise value | {_fmt_money(v.get('enterprise_value'))} |")
    out.append("")

    out.append("## Profitability & Returns")
    out.append("")
    out.append(f"| Metric | Value |")
    out.append(f"|---|---:|")
    out.append(f"| Gross margin | {_fmt_pct(p.get('gross_margin'))} |")
    out.append(f"| Operating margin | {_fmt_pct(p.get('operating_margin'))} |")
    out.append(f"| Net margin | {_fmt_pct(p.get('net_margin'))} |")
    out.append(f"| ROE | {_fmt_pct(p.get('roe'))} |")
    out.append(f"| ROIC | {_fmt_pct(p.get('roic'))} |")
    out.append(f"| ROA | {_fmt_pct(p.get('roa'))} |")
    out.append("")

    out.append("## Balance Sheet & Coverage")
    out.append("")
    out.append(f"| Metric | Value |")
    out.append(f"|---|---:|")
    out.append(f"| Current ratio | {_fmt_num(b.get('current_ratio'))} |")
    out.append(f"| Debt / equity | {_fmt_num(b.get('debt_to_equity'))} |")
    out.append(f"| Net debt / EBITDA | {_fmt_num(b.get('net_debt_to_ebitda'))} |")
    out.append(f"| Interest coverage | {_fmt_num(b.get('interest_coverage'))} |")
    out.append("")

    out.append("## Capital Allocation")
    out.append("")
    out.append(f"| Metric | Value |")
    out.append(f"|---|---:|")
    out.append(f"| R&D / revenue | {_fmt_pct(c.get('rnd_to_revenue'))} |")
    out.append(f"| Capex / revenue | {_fmt_pct(c.get('capex_to_revenue'))} |")
    out.append(f"| Capex / operating CF | {_fmt_pct(c.get('capex_to_ocf'))} |")
    out.append(f"| Stock-based comp / revenue | {_fmt_pct(c.get('stock_based_comp_to_revenue'))} |")
    out.append("")

    out.append("## Growth")
    out.append("")
    out.append(f"| Metric | Value |")
    out.append(f"|---|---:|")
    out.append(f"| Revenue growth (1y) | {_fmt_pct(g.get('revenue_growth_1y'))} |")
    out.append(f"| Revenue CAGR (3y, /share) | {_fmt_pct(g.get('revenue_cagr_3y_pershare'))} |")
    out.append(f"| Revenue CAGR (5y, /share) | {_fmt_pct(g.get('revenue_cagr_5y_pershare'))} |")
    out.append(f"| EPS growth (1y) | {_fmt_pct(g.get('eps_growth_1y'))} |")
    out.append(f"| EPS diluted growth (1y) | {_fmt_pct(g.get('eps_diluted_growth_1y'))} |")
    out.append(f"| Net income CAGR (3y, /share) | {_fmt_pct(g.get('net_income_cagr_3y_pershare'))} |")
    out.append(f"| Net income CAGR (5y, /share) | {_fmt_pct(g.get('net_income_cagr_5y_pershare'))} |")
    out.append(f"| Operating income growth (1y) | {_fmt_pct(g.get('operating_income_growth_1y'))} |")
    out.append(f"| FCF growth (1y) | {_fmt_pct(g.get('fcf_growth_1y'))} |")
    out.append(f"| R&D expense growth (1y) | {_fmt_pct(g.get('rd_expense_growth_1y'))} |")
    out.append("")

    if s.get("recent_quarters"):
        out.append("## Recent quarters")
        out.append("")
        out.append("| Period | Revenue | Op. income | Net income | EPS (dil) | GM |")
        out.append("|---|---:|---:|---:|---:|---:|")
        for q in s["recent_quarters"]:
            out.append(
                f"| {q.get('date')} ({q.get('period')}) "
                f"| {_fmt_money(q.get('revenue'))} "
                f"| {_fmt_money(q.get('operating_income'))} "
                f"| {_fmt_money(q.get('net_income'))} "
                f"| {_fmt_num(q.get('eps_diluted'))} "
                f"| {_fmt_pct(q.get('gross_margin'))} |"
            )
        out.append("")

    if s.get("forward_estimate"):
        fe = s["forward_estimate"]
        out.append("## Forward estimate (next FY)")
        out.append("")
        out.append(f"- Fiscal year end: {fe.get('fiscal_year_end')}")
        out.append(f"- Revenue: avg {_fmt_money(fe.get('revenue_avg'))} "
                   f"(low {_fmt_money(fe.get('revenue_low'))}, high {_fmt_money(fe.get('revenue_high'))})")
        out.append(f"- EPS: avg {_fmt_num(fe.get('eps_avg'))} "
                   f"(low {_fmt_num(fe.get('eps_low'))}, high {_fmt_num(fe.get('eps_high'))})")
        out.append(f"- Analysts (EPS): {fe.get('num_analysts_eps')}")
        out.append("")

    out.append("## Analyst targets & ratings")
    out.append("")
    out.append(f"- Targets: low ${_fmt_num(t.get('target_low'))} / "
               f"avg **${_fmt_num(t.get('target_avg'))}** / "
               f"high ${_fmt_num(t.get('target_high'))} / "
               f"median ${_fmt_num(t.get('target_median'))}")
    out.append(f"- Implied upside vs spot: **{_fmt_pct_raw(t.get('implied_upside_pct'))}**")
    out.append(f"- Consensus: **{r.get('consensus') or 'n/a'}** "
               f"(strong buy {r.get('strong_buy', 0) or 0}, buy {r.get('buy', 0) or 0}, "
               f"hold {r.get('hold', 0) or 0}, sell {r.get('sell', 0) or 0}, "
               f"strong sell {r.get('strong_sell', 0) or 0})")
    out.append("")

    if s.get("recent_rating_changes"):
        out.append("## Recent rating changes")
        out.append("")
        out.append("| Date | Firm | Previous | New | Action |")
        out.append("|---|---|---|---|---|")
        for rc in s["recent_rating_changes"]:
            out.append(
                f"| {rc.get('date')} | {rc.get('firm')} "
                f"| {rc.get('previous_grade') or '-'} "
                f"| {rc.get('new_grade') or '-'} "
                f"| {rc.get('action') or '-'} |"
            )

    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("symbol", help="Ticker (e.g., AMD, NVDA, AAPL).")
    p.add_argument("--format", choices=("json", "md"), default="json",
                   help="Output format (default: json).")
    p.add_argument("--output", help="Output file path (default: stdout).")
    args = p.parse_args()

    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        sys.exit("Set FMP_API_KEY environment variable.")

    snapshot = fetch_snapshot(args.symbol, api_key)

    if args.format == "json":
        text = json.dumps(snapshot, indent=2, default=str)
    else:
        text = render_markdown(snapshot)

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


if __name__ == "__main__":
    main()
