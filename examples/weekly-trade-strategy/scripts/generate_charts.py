#!/usr/bin/env python3
"""Generate weekly chart images for the weekly-trade-strategy pipeline.

Pulls weekly OHLCV bars and renders candlestick PNGs for major indices, sector
ETFs, and commodity ETF proxies. Two data sources are supported:

  --source alpaca (default): Alpaca Markets weekly bars; yfinance fallback for
                             ^VIX and ^TNX (indices not on Alpaca equity feed).
  --source fmp             : FMP daily bars resampled to weekly; ^VIX and ^TNX
                             pulled from FMP directly (no yfinance needed).

Usage:
    # Alpaca (default)
    export APCA_API_KEY_ID=...
    export APCA_API_SECRET_KEY=...
    # optional: export ALPACA_FEED=iex   (default; use "sip" if you have the paid feed)
    python generate_charts.py                       # charts/<today>/
    python generate_charts.py 2026-04-27            # charts/2026-04-27/

    # FMP only (full-tape volume; no Alpaca creds needed)
    export FMP_API_KEY=...
    python generate_charts.py --source fmp 2026-04-27

Dependencies: requests, matplotlib, numpy. yfinance is optional (alpaca source only).
Run from the weekly-trade-strategy/ directory so "charts/" is created there.
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import requests
from matplotlib.patches import Rectangle

ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
FMP_DAILY_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"
FMP_RATE_LIMIT_DELAY = 0.3
LOOKBACK_WEEKS = 104

INDICES = {
    "SPY": "S&P 500 (SPY)",
    "QQQ": "Nasdaq 100 (QQQ)",
    "IWM": "Russell 2000 (IWM)",
    "DIA": "Dow Jones (DIA)",
}

COMMODITIES = {
    "GLD": "Gold (GLD)",
    "CPER": "Copper (CPER)",
    "USO": "Crude Oil (USO)",
    "UNG": "Natural Gas (UNG)",
    "URA": "Uranium (URA)",
}

SECTORS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLY": "Consumer Disc.",
    "XLV": "Healthcare",
    "XLP": "Consumer Stap.",
    "XLI": "Industrials",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLC": "Comm. Services",
}

YF_SYMBOLS = {"^VIX": "VIX", "^TNX": "10Y Treasury Yield"}


def alpaca_headers():
    key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        sys.exit(
            "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY "
            "(or ALPACA_API_KEY / ALPACA_SECRET_KEY)."
        )
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "accept": "application/json",
    }


def fetch_alpaca_bars(symbols, start, end, timeframe="1Week"):
    """Return {symbol: [bar dicts]}, paginating through next_page_token."""
    feed = os.environ.get("ALPACA_FEED", "iex")
    params = {
        "symbols": ",".join(symbols),
        "timeframe": timeframe,
        "start": start,
        "end": end,
        "adjustment": "all",
        "feed": feed,
        "sort": "asc",
        "limit": 10000,
    }
    headers = alpaca_headers()
    out = {}
    while True:
        r = requests.get(ALPACA_BARS_URL, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        j = r.json()
        for sym, bars in (j.get("bars") or {}).items():
            out.setdefault(sym, []).extend(bars)
        page = j.get("next_page_token")
        if not page:
            break
        params["page_token"] = page
    return out


def _daily_to_weekly(daily_bars):
    """Group FMP daily bars into ISO weeks (Mon-Fri buckets).

    Each input bar has keys date/open/high/low/close/volume. Output bars match
    Alpaca shape: t (ISO Z), o, h, l, c, v.
    """
    if not daily_bars:
        return []
    daily_sorted = sorted(daily_bars, key=lambda b: b["date"])
    weeks = {}
    for b in daily_sorted:
        d = datetime.strptime(b["date"], "%Y-%m-%d").date()
        year, week, _ = d.isocalendar()
        weeks.setdefault((year, week), []).append(b)
    out = []
    for (year, week), days in sorted(weeks.items()):
        monday = datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u").date()
        out.append({
            "t": f"{monday.isoformat()}T00:00:00Z",
            "o": days[0]["open"],
            "h": max(d["high"] for d in days),
            "l": min(d["low"] for d in days),
            "c": days[-1]["close"],
            "v": sum(d.get("volume") or 0 for d in days),
        })
    return out


def fetch_fmp_bars(symbols, start, end):
    """Return {symbol: [weekly bar dicts]} via FMP daily aggregation."""
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        sys.exit("Set FMP_API_KEY environment variable.")
    out = {}
    last_call = 0.0
    for sym in symbols:
        elapsed = time.time() - last_call
        if elapsed < FMP_RATE_LIMIT_DELAY:
            time.sleep(FMP_RATE_LIMIT_DELAY - elapsed)
        params = {"symbol": sym, "from": start, "to": end, "apikey": api_key}
        r = requests.get(FMP_DAILY_URL, params=params, timeout=30)
        last_call = time.time()
        if r.status_code != 200:
            print(f"  FMP fetch failed for {sym}: HTTP {r.status_code}", file=sys.stderr)
            continue
        data = r.json()
        if isinstance(data, dict) and "historical" in data:
            daily = data["historical"]
        elif isinstance(data, list):
            daily = data
        else:
            print(f"  unexpected FMP shape for {sym}", file=sys.stderr)
            continue
        weekly = _daily_to_weekly(daily)
        if weekly:
            out[sym] = weekly
    return out


def bars_arrays(bars):
    """Convert list of bar dicts to (times, opens, highs, lows, closes, volumes)."""
    if not bars:
        return None
    times = np.array([datetime.fromisoformat(b["t"].replace("Z", "+00:00")) for b in bars])
    return (
        times,
        np.array([b["o"] for b in bars]),
        np.array([b["h"] for b in bars]),
        np.array([b["l"] for b in bars]),
        np.array([b["c"] for b in bars]),
        np.array([b["v"] for b in bars]),
    )


def render_candle(data, title, out_path):
    times, opens, highs, lows, closes, volumes = data
    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    dates = mdates.date2num(times)
    body_w = 5.0  # weekly bar width in days

    up = closes >= opens
    ax_price.vlines(dates, lows, highs, color="black", linewidth=0.8)
    for i in range(len(dates)):
        color = "#26a69a" if up[i] else "#ef5350"
        bottom = min(opens[i], closes[i])
        height = abs(closes[i] - opens[i]) or (highs[i] - lows[i]) * 0.01
        ax_price.add_patch(Rectangle(
            (dates[i] - body_w / 2, bottom), body_w, height,
            facecolor=color, edgecolor=color,
        ))

    for window, color in [(20, "#1976d2"), (50, "#f57c00")]:
        if len(closes) >= window:
            ma = np.convolve(closes, np.ones(window) / window, mode="valid")
            ax_price.plot(dates[window - 1:], ma, color=color, linewidth=1.2,
                          label=f"MA{window}")

    ax_price.set_title(title)
    ax_price.legend(loc="upper left", fontsize=9)
    ax_price.grid(True, alpha=0.3)
    ax_price.set_ylabel("Price")

    vol_colors = ["#26a69a" if u else "#ef5350" for u in up]
    ax_vol.bar(dates, volumes, width=body_w, color=vol_colors, alpha=0.7)
    ax_vol.set_ylabel("Volume")
    ax_vol.grid(True, alpha=0.3)
    ax_vol.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax_vol.xaxis.get_majorticklabels(), rotation=30)

    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def render_sector_perf(bars_by_sym, period_weeks, title, out_path):
    rows = []
    for sym, label in SECTORS.items():
        bars = bars_by_sym.get(sym) or []
        if len(bars) < period_weeks + 1:
            continue
        ret = (bars[-1]["c"] / bars[-period_weeks - 1]["c"] - 1) * 100
        rows.append((label, ret))
    if not rows:
        print(f"  skip {title}: insufficient data", file=sys.stderr)
        return
    rows.sort(key=lambda r: r[1], reverse=True)
    labels, values = zip(*rows)
    colors = ["#26a69a" if v >= 0 else "#ef5350" for v in values]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.invert_yaxis()
    ax.set_xlabel("Return (%)")
    ax.set_title(title)
    for i, v in enumerate(values):
        ax.text(
            v + (0.15 if v >= 0 else -0.15), i, f"{v:+.1f}%",
            va="center", ha="left" if v >= 0 else "right", fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def try_yfinance(symbol):
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.Ticker(symbol).history(period="2y", interval="1wk")
        if df.empty:
            return None
        return (
            np.array(df.index.to_pydatetime()),
            df["Open"].to_numpy(),
            df["High"].to_numpy(),
            df["Low"].to_numpy(),
            df["Close"].to_numpy(),
            df["Volume"].to_numpy(),
        )
    except Exception as e:
        print(f"  yfinance fetch failed for {symbol}: {e}", file=sys.stderr)
        return None


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("date", nargs="?", default=None,
                   help="Target date (YYYY-MM-DD); default: today.")
    p.add_argument("--output-root", default="charts",
                   help="Root directory (default: charts).")
    p.add_argument("--source", choices=("alpaca", "fmp"), default="alpaca",
                   help="Bar data source (default: alpaca).")
    args = p.parse_args()

    target = args.date or date.today().isoformat()
    out_dir = Path(args.output_root) / target
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing charts to {out_dir}/", file=sys.stderr)

    end_iso = target
    start_iso = (date.fromisoformat(target) - timedelta(weeks=LOOKBACK_WEEKS)).isoformat()

    all_syms = list(INDICES) + list(COMMODITIES) + list(SECTORS)
    print(f"Fetching {len(all_syms)} symbols from {args.source.upper()} "
          f"({start_iso} -> {end_iso})...", file=sys.stderr)
    if args.source == "fmp":
        bars_by_sym = fetch_fmp_bars(all_syms, start_iso, end_iso)
    else:
        bars_by_sym = fetch_alpaca_bars(all_syms, start_iso, end_iso)

    for sym, label in {**INDICES, **COMMODITIES}.items():
        data = bars_arrays(bars_by_sym.get(sym))
        if data is None:
            print(f"  skip {sym}: no data", file=sys.stderr)
            continue
        render_candle(data, label, out_dir / f"{sym.lower()}.png")
        print(f"  OK {sym.lower()}.png", file=sys.stderr)

    render_sector_perf(bars_by_sym, 1, "Sector Performance - 1 Week",
                       out_dir / "sector_1w.png")
    print("  OK sector_1w.png", file=sys.stderr)
    render_sector_perf(bars_by_sym, 4, "Sector Performance - 1 Month",
                       out_dir / "sector_1m.png")
    print("  OK sector_1m.png", file=sys.stderr)

    if args.source == "fmp":
        vix_tnx_bars = fetch_fmp_bars(list(YF_SYMBOLS), start_iso, end_iso)
    else:
        vix_tnx_bars = {}
    for sym, label in YF_SYMBOLS.items():
        data = bars_arrays(vix_tnx_bars.get(sym))
        if data is None:
            data = try_yfinance(sym)
            src = "yfinance"
        else:
            src = "fmp"
        if data is None:
            print(f"  skip {sym}: no data (FMP paywall? yfinance unavailable?)",
                  file=sys.stderr)
            continue
        fname = sym.lstrip("^").lower() + ".png"
        render_candle(data, label, out_dir / fname)
        print(f"  OK {fname} ({src})", file=sys.stderr)

    files = sorted(out_dir.iterdir())
    print(f"\nDone. {len(files)} files in {out_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
