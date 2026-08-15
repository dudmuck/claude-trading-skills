#!/usr/bin/env python3
"""Build the aligned CSV + JSON spec that `residual-edge-analyzer` consumes.

Why this exists
---------------
The weekly pipeline decides posture every Sunday, but nothing in it ever asks
the obvious follow-up: is the tactical rebalancing producing anything that
holding SPY wouldn't have? `skills/residual-edge-analyzer` answers that, but it
deliberately fetches no data -- it takes one aligned return CSV and one JSON
spec. This script produces both from the live Alpaca account.

Cadence: QUARTERLY, not weekly. This measures something that only accumulates
signal over months; re-running it every Sunday re-reads noise on a sample that
has barely changed, and invites treating an unchanged verdict as new evidence.

    strategy_return      daily % change in account equity (Alpaca portfolio history)
    market_return        SPY, dividend-adjusted
    equal_weight_return  RSP, dividend-adjusted
    momentum_return      MTUM, dividend-adjusted

Three methodology points worth keeping straight:

1. Baselines come from FMP `historical-price-eod/dividend-adjusted`, so they are
   TOTAL-return series. Account equity already includes dividends received as
   cash, so both sides of the regression are total return. Raw closes would
   understate SPY by roughly its dividend yield and flatter the strategy by the
   same amount.

2. Baselines are NOT sourced from Alpaca. This account has no SIP entitlement,
   and the IEX fallback is missing daily bars for the thinner ETFs (RSP, MTUM) --
   on the first run that silently dropped 17 of 81 days, and those days are not
   missing at random. FMP is full-tape and keeps the sample intact.

3. The book runs a ~60% equity sleeve against a >=25% cash floor, so the fitted
   beta on SPY should land well below 1.0 and the intercept absorbs the cash
   drag. That is expected, not a bug -- the question is whether alpha survives
   AFTER that beta is accounted for. Do not "correct" for it by scaling.

Cashflows: daily equity changes are only returns when no deposits or
withdrawals occurred. Any day whose implied return exceeds --cashflow-threshold
is reported so it can be excluded rather than silently regressed on.

Usage:
    export APCA_API_KEY_ID=... APCA_API_SECRET_KEY=... FMP_API_KEY=...
    python3 build_residual_edge_input.py --out-dir /tmp/residual
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

# Alpaca stamps 1D portfolio-history rows at 20:00 America/New_York (the end of
# the extended session), which is 00:00 UTC on the FOLLOWING calendar day.
# Converting those timestamps in UTC therefore shifts every trading date forward
# by one and silently pairs each day's strategy return with the NEXT day's
# baseline return. Resolve the date in exchange time instead.
EXCHANGE_TZ = ZoneInfo("America/New_York")

ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
FMP_ADJUSTED_URL = "https://financialmodelingprep.com/stable/historical-price-eod/dividend-adjusted"

# column name in the emitted CSV -> ETF proxy
DEFAULT_BASELINES = {
    "market_return": "SPY",
    "equal_weight_return": "RSP",
    "momentum_return": "MTUM",
}


def alpaca_headers() -> dict:
    key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        sys.exit(
            "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY (or ALPACA_API_KEY / ALPACA_SECRET_KEY)."
        )
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "accept": "application/json",
    }


def fmp_key() -> str:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        sys.exit("Set FMP_API_KEY (baseline ETF closes are sourced from FMP).")
    return key


def fetch_portfolio_equity(period: str, base_url: str) -> dict[str, float]:
    """Return {ISO date: equity} for funded days only, oldest first."""
    r = requests.get(
        f"{base_url}/v2/account/portfolio/history",
        params={"period": period, "timeframe": "1D"},
        headers=alpaca_headers(),
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    out: dict[str, float] = {}
    for ts, eq in zip(j.get("timestamp") or [], j.get("equity") or []):
        if not eq:  # pre-funding days come back as 0
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(EXCHANGE_TZ).date().isoformat()
        out[d] = float(eq)
    return dict(sorted(out.items()))


def fetch_adjusted_closes(symbol: str, start: str, end: str, key: str) -> dict[str, float]:
    """Return {ISO date: dividend-adjusted close} for one symbol."""
    r = requests.get(
        FMP_ADJUSTED_URL,
        params={"symbol": symbol, "from": start, "to": end, "apikey": key},
        timeout=60,
    )
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        sys.exit(f"FMP returned no dividend-adjusted history for {symbol}.")
    out = {}
    for row in rows:
        close = row.get("adjClose")
        if row.get("date") and close:
            out[row["date"][:10]] = float(close)
    return out


def to_returns(series: dict[str, float]) -> dict[str, float]:
    """Simple period returns keyed by the LATER date of each pair."""
    dates = sorted(series)
    return {
        dates[i]: series[dates[i]] / series[dates[i - 1]] - 1.0
        for i in range(1, len(dates))
        if series[dates[i - 1]]
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--period", default="1A", help="Alpaca portfolio-history period (default 1A)")
    p.add_argument("--out-dir", required=True, help="Directory for the CSV + config")
    p.add_argument("--base-url", default=ALPACA_PAPER_URL)
    p.add_argument(
        "--cashflow-threshold",
        type=float,
        default=0.15,
        help="Flag any daily equity move beyond this magnitude as a possible deposit/withdrawal",
    )
    p.add_argument("--frequency", default="daily", choices=["daily", "weekly", "monthly"])
    p.add_argument("--rolling-window", type=int, default=21)
    args = p.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    equity = fetch_portfolio_equity(args.period, args.base_url)
    if len(equity) < 2:
        sys.exit("Not enough funded portfolio history to compute returns.")
    start, end = min(equity), max(equity)
    print(f"Portfolio equity: {len(equity)} funded days, {start} -> {end}", file=sys.stderr)

    strat = to_returns(equity)
    suspect = {d: r for d, r in strat.items() if abs(r) > args.cashflow_threshold}
    if suspect:
        print(
            f"WARNING: {len(suspect)} day(s) exceed the {args.cashflow_threshold:.0%} "
            "cashflow threshold and may be deposits/withdrawals rather than returns:",
            file=sys.stderr,
        )
        for d, r in suspect.items():
            print(f"  {d}: {r:+.2%}", file=sys.stderr)

    key = fmp_key()
    base_returns = {}
    for col, sym in DEFAULT_BASELINES.items():
        closes = fetch_adjusted_closes(sym, start, end, key)
        base_returns[col] = to_returns(closes)
        print(f"  {sym}: {len(closes)} adjusted closes", file=sys.stderr)

    # Intersect on dates where EVERY series has a return.
    common = set(strat)
    for col in base_returns:
        common &= set(base_returns[col])
    aligned = sorted(common)
    dropped = len(strat) - len(aligned)
    if dropped:
        print(f"Dropped {dropped} strategy day(s) with no matching baseline bar.", file=sys.stderr)
    if not aligned:
        sys.exit("No overlapping dates between portfolio history and baseline bars.")

    columns = ["date", "strategy_return", *DEFAULT_BASELINES.keys()]
    csv_path = os.path.join(args.out_dir, "residual_edge_input.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for d in aligned:
            w.writerow(
                [d, f"{strat[d]:.8f}", *[f"{base_returns[c][d]:.8f}" for c in DEFAULT_BASELINES]]
            )

    config = {
        "schema_version": "1.0",
        "date_column": "date",
        "strategy_column": "strategy_return",
        "return_unit": "decimal",
        "frequency": args.frequency,
        "primary_model": {"name": "market", "baseline_columns": ["market_return"]},
        "sensitivity_models": [
            {"name": "equal_weight", "baseline_columns": ["equal_weight_return"]},
            {
                "name": "market_plus_momentum",
                "baseline_columns": ["market_return", "momentum_return"],
            },
        ],
        "rolling_window": args.rolling_window,
        "minimum_observations": 60,
        "minimum_rolling_windows": 12,
        "hac_lags": "auto",
        "include_series": True,
        "data_declarations": {
            "baseline_selection": "predeclared",
            "strategy_return_basis": "net",
            "baseline_return_basis": "net",
            "analysis_scope": "out_of_sample",
            "universe_data": "point_in_time",
        },
    }
    cfg_path = os.path.join(args.out_dir, "residual_edge_config.json")
    with open(cfg_path, "w") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")

    print(f"\nRows: {len(aligned)} ({aligned[0]} -> {aligned[-1]})")
    print(f"CSV:    {csv_path}")
    print(f"Config: {cfg_path}")
    floor = max(config["minimum_observations"], 10)
    if len(aligned) < floor:
        print(f"\nNOTE: {len(aligned)} rows is below the {floor}-observation evidence floor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
