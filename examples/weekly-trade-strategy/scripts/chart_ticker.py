#!/usr/bin/env python3
"""Generate a weekly candlestick chart for an arbitrary ticker.

Reuses fetch/render primitives from generate_charts.py. Source order is the
preferred backend (alpaca or fmp), then yfinance fallback for symbols neither
backend serves (notably ^VIX and ^TNX, plus assorted foreign indices).

Usage:
    # Alpaca (default), 2 years back
    python chart_ticker.py NVDA
    python chart_ticker.py NVDA --weeks 52 --label "NVIDIA"

    # FMP source, custom output path
    python chart_ticker.py XOM --source fmp --weeks 156 --output /tmp/xom.png

    # Indices that need yfinance fallback
    python chart_ticker.py ^VIX --source fmp
    python chart_ticker.py ^TNX --weeks 260      # 5 years

Run from the weekly-trade-strategy/ directory (or pass an absolute --output).
Use ~/.venv/bin/python if the yfinance fallback is needed (e.g., ^TNX).
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from generate_charts import (
    bars_arrays,
    fetch_alpaca_bars,
    fetch_fmp_bars,
    render_candle,
    try_yfinance,
)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("symbol", help="Ticker (e.g., NVDA, ^VIX, BRK-B).")
    p.add_argument("--weeks", type=int, default=104,
                   help="Lookback in weeks (default: 104 = ~2 years).")
    p.add_argument("--source", choices=("alpaca", "fmp"), default="alpaca",
                   help="Primary data source (default: alpaca).")
    p.add_argument("--output",
                   help="Output PNG path (default: <symbol>_<today>.png in cwd).")
    p.add_argument("--label",
                   help="Chart title (default: derived from symbol).")
    args = p.parse_args()

    today = date.today().isoformat()
    start_iso = (date.today() - timedelta(weeks=args.weeks)).isoformat()

    label = args.label or args.symbol
    out_path = Path(args.output) if args.output \
        else Path(f"{args.symbol.lstrip('^').replace('-', '_').lower()}_{today}.png")

    print(f"Fetching {args.symbol} from {args.source.upper()} "
          f"({start_iso} -> {today})...", file=sys.stderr)

    bars = None
    src_used = None
    try:
        if args.source == "fmp":
            bars_by_sym = fetch_fmp_bars([args.symbol], start_iso, today)
        else:
            bars_by_sym = fetch_alpaca_bars([args.symbol], start_iso, today)
        bars = bars_by_sym.get(args.symbol)
        if bars:
            src_used = args.source
    except Exception as e:
        print(f"  {args.source} fetch raised: {e}", file=sys.stderr)

    data = bars_arrays(bars)
    if data is None:
        print(f"  {args.source} returned no data for {args.symbol}; "
              "trying yfinance fallback...", file=sys.stderr)
        data = try_yfinance(args.symbol)
        if data is not None:
            src_used = "yfinance"

    if data is None:
        print(f"  ERROR: no data from any source for {args.symbol}.",
              file=sys.stderr)
        sys.exit(1)

    render_candle(data, label, out_path)
    print(f"  OK {out_path} ({src_used}, {args.weeks}w lookback)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
