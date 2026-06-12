#!/usr/bin/env python3
"""Collect weekly core portfolio data for local review workflows."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

ALPACA_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE_URL = "https://api.alpaca.markets"
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Collect Alpaca holdings plus FMP enrichment for weekly core reviews."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "reports",
        help="Directory for generated JSON artifacts. Defaults to reports/ in this repo.",
    )
    parser.add_argument(
        "--as-of",
        default=dt.datetime.now().astimezone().date().isoformat(),
        help="Date string for output filenames. Defaults to today's local date.",
    )
    parser.add_argument(
        "--alpaca-paper",
        choices=["true", "false"],
        default=os.environ.get("ALPACA_PAPER", "true").lower(),
        help="Use Alpaca paper endpoint when true. Defaults to ALPACA_PAPER or true.",
    )
    parser.add_argument(
        "--fmp-sleep-seconds",
        type=float,
        default=0.08,
        help="Pause between per-symbol FMP request groups.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def alpaca_headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": require_env("ALPACA_API_KEY"),
        "APCA-API-SECRET-KEY": require_env("ALPACA_SECRET_KEY"),
    }


def get_json(url: str, **kwargs: Any) -> Any:
    response = requests.get(url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def alpaca_base_url(use_paper: bool) -> str:
    return ALPACA_PAPER_BASE_URL if use_paper else ALPACA_LIVE_BASE_URL


def fmp_get(api_key: str | None, path: str, **params: Any) -> Any:
    if not api_key:
        return None
    params["apikey"] = api_key
    try:
        response = requests.get(f"{FMP_BASE_URL}/{path}", params=params, timeout=30)
        if response.status_code != 200:
            return {"_status": response.status_code, "_text": response.text[:200]}
        return response.json()
    except requests.RequestException as exc:
        return {"_error": str(exc)}


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def fetch_profiles_and_quotes(symbols: list[str], fmp_api_key: str | None) -> tuple[dict, dict]:
    profiles: dict[str, dict] = {}
    quotes: dict[str, dict] = {}
    if not symbols or not fmp_api_key:
        return profiles, quotes

    for chunk in chunks(symbols, 50):
        symbol_csv = ",".join(chunk)
        profile_data = fmp_get(fmp_api_key, f"profile/{symbol_csv}")
        if isinstance(profile_data, list):
            profiles.update(
                {item.get("symbol"): item for item in profile_data if item.get("symbol")}
            )

        quote_data = fmp_get(fmp_api_key, f"quote/{symbol_csv}")
        if isinstance(quote_data, list):
            quotes.update({item.get("symbol"): item for item in quote_data if item.get("symbol")})

    return profiles, quotes


def build_holding_rows(
    account: dict,
    positions: list[dict],
    profiles: dict[str, dict],
    quotes: dict[str, dict],
    fmp_api_key: str | None,
    fmp_sleep_seconds: float,
) -> tuple[list[dict], list[dict]]:
    monitor_holdings = []
    full_rows = []
    equity = to_float(account.get("equity"))
    long_market_value = to_float(account.get("long_market_value"))

    for position in positions:
        symbol = position["symbol"]
        profile = profiles.get(symbol, {}) or {}
        quote = quotes.get(symbol, {}) or {}

        dividends = []
        cashflow = []
        income = []
        balance_sheet = []
        if fmp_api_key:
            dividend_data = fmp_get(fmp_api_key, f"historical-price-full/stock_dividend/{symbol}")
            if isinstance(dividend_data, dict):
                dividends = dividend_data.get("historical") or []

            cashflow = fmp_get(fmp_api_key, f"cash-flow-statement/{symbol}", limit=4)
            income = fmp_get(fmp_api_key, f"income-statement/{symbol}", limit=4)
            balance_sheet = fmp_get(fmp_api_key, f"balance-sheet-statement/{symbol}", limit=4)
            time.sleep(fmp_sleep_seconds)

        positive_dividends = [
            to_float(item.get("adjDividend") or item.get("dividend"))
            for item in dividends
            if to_float(item.get("adjDividend") or item.get("dividend")) > 0
        ]
        latest_dividend = positive_dividends[0] if positive_dividends else None
        prior_dividend = positive_dividends[1] if len(positive_dividends) > 1 else None

        coverage_ratios = []
        if isinstance(cashflow, list):
            for statement in cashflow[:4]:
                free_cash_flow = to_float(statement.get("operatingCashFlow")) + to_float(
                    statement.get("capitalExpenditure")
                )
                dividends_paid = abs(to_float(statement.get("dividendsPaid")))
                if dividends_paid:
                    coverage_ratios.append(
                        dividends_paid / free_cash_flow if free_cash_flow else 999
                    )

        net_debt_history = []
        if isinstance(balance_sheet, list):
            for statement in balance_sheet[:4]:
                net_debt_history.append(
                    to_float(statement.get("totalDebt"))
                    - to_float(statement.get("cashAndCashEquivalents"))
                )

        interest_coverage_history = []
        revenues = []
        if isinstance(income, list):
            for statement in income[:4]:
                interest_expense = abs(to_float(statement.get("interestExpense")))
                ebit = to_float(statement.get("ebitda") or statement.get("operatingIncome"))
                interest_coverage_history.append(
                    ebit / interest_expense if interest_expense else None
                )
                if statement.get("revenue"):
                    revenues.append(to_float(statement.get("revenue")))

        revenue_cagr_3y = None
        if len(revenues) >= 4 and revenues[-1] > 0:
            revenue_cagr_3y = (revenues[0] / revenues[-1]) ** (1 / 3) - 1

        instrument_type = "etf" if profile.get("isEtf") else "stock"
        sector = profile.get("sector") or quote.get("sector") or "Unknown"
        market_value = to_float(position.get("market_value"))

        row = {
            "symbol": symbol,
            "qty": to_float(position.get("qty")),
            "market_value": market_value,
            "cost_basis": to_float(position.get("cost_basis")),
            "unrealized_pl": to_float(position.get("unrealized_pl")),
            "unrealized_plpc": to_float(position.get("unrealized_plpc")),
            "current_price": to_float(position.get("current_price")),
            "weight_gross_long": market_value / long_market_value if long_market_value else None,
            "weight_equity": market_value / equity if equity else None,
            "sector": sector,
            "industry": profile.get("industry"),
            "company": profile.get("companyName") or symbol,
            "instrument_type": instrument_type,
            "is_etf": bool(profile.get("isEtf")),
            "beta": profile.get("beta") or quote.get("beta"),
            "dividend_yield_profile": profile.get("lastDiv"),
            "latest_regular_dividend": latest_dividend,
            "prior_regular_dividend": prior_dividend,
            "dividend_events_count": len(positive_dividends),
            "coverage_ratio_history": coverage_ratios[:4],
            "net_debt_history": net_debt_history[:4],
            "interest_coverage_history": interest_coverage_history[:4],
            "revenue_cagr_3y": revenue_cagr_3y,
        }
        full_rows.append(row)

        if latest_dividend is not None or instrument_type == "etf":
            dividend_growth_stalled = (
                latest_dividend is not None
                and prior_dividend is not None
                and abs(latest_dividend - prior_dividend) < 1e-9
            )
            monitor_holdings.append(
                {
                    "ticker": symbol,
                    "instrument_type": instrument_type,
                    "dividend": {
                        "latest_regular": latest_dividend,
                        "prior_regular": prior_dividend,
                        "is_missing": latest_dividend is None or prior_dividend is None,
                        "flags": {
                            "cut_flag": bool(
                                latest_dividend is not None
                                and prior_dividend is not None
                                and latest_dividend < prior_dividend * 0.99
                            ),
                            "freeze_flag": dividend_growth_stalled,
                            "special_dividend_flag": False,
                            "variable_policy_flag": False,
                        },
                    },
                    "cashflow": {
                        "fcf": None,
                        "ffo": None,
                        "nii": None,
                        "dividends_paid": None,
                        "coverage_ratio_history": coverage_ratios[:4],
                    },
                    "balance_sheet": {
                        "net_debt_history": net_debt_history[:4],
                        "interest_coverage_history": interest_coverage_history[:4],
                    },
                    "capital_returns": {"buybacks": None, "dividends_paid": None, "fcf": None},
                    "filings": {"recent_text": "", "latest_8k_text": "", "headlines": []},
                    "operations": {
                        "revenue_cagr_5y": revenue_cagr_3y * 100
                        if revenue_cagr_3y is not None
                        else None,
                        "margin_trend": None,
                        "guidance_trend": None,
                        "dividend_growth_stalled": dividend_growth_stalled,
                    },
                }
            )

    return full_rows, monitor_holdings


def build_summary(account: dict, holdings: list[dict], as_of: str) -> dict:
    sector_weights: dict[str, float] = defaultdict(float)
    for row in holdings:
        sector_weights[row["sector"]] += row["market_value"]

    equity = to_float(account.get("equity"))
    long_market_value = to_float(account.get("long_market_value"))
    return {
        "as_of": as_of,
        "account": {
            key: account.get(key)
            for key in [
                "status",
                "currency",
                "equity",
                "cash",
                "buying_power",
                "long_market_value",
                "short_market_value",
                "portfolio_value",
                "balance_asof",
                "multiplier",
                "pattern_day_trader",
            ]
        },
        "positions_count": len(holdings),
        "symbols": [row["symbol"] for row in holdings],
        "gross_long_exposure_pct_equity": long_market_value / equity * 100 if equity else None,
        "cash_pct_equity": to_float(account.get("cash")) / equity * 100 if equity else None,
        "sector_weights_gross_long": {
            sector: value / long_market_value * 100 if long_market_value else None
            for sector, value in sorted(sector_weights.items(), key=lambda item: -item[1])
        },
        "top_positions": sorted(holdings, key=lambda row: row["market_value"], reverse=True)[:10],
        "holdings": holdings,
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    use_paper = args.alpaca_paper == "true"
    base_url = alpaca_base_url(use_paper)
    headers = alpaca_headers()
    account = get_json(f"{base_url}/v2/account", headers=headers)
    positions = get_json(f"{base_url}/v2/positions", headers=headers)
    if not isinstance(account, dict):
        raise SystemExit("Unexpected Alpaca account response")
    if not isinstance(positions, list):
        raise SystemExit("Unexpected Alpaca positions response")

    symbols = [position["symbol"] for position in positions]
    fmp_api_key = os.environ.get("FMP_API_KEY")
    profiles, quotes = fetch_profiles_and_quotes(symbols, fmp_api_key)
    holdings, monitor_holdings = build_holding_rows(
        account, positions, profiles, quotes, fmp_api_key, args.fmp_sleep_seconds
    )
    summary = build_summary(account, holdings, args.as_of)

    holdings_path = args.output_dir / f"core_portfolio_holdings_{args.as_of}.json"
    monitor_path = args.output_dir / f"kanchi_monitor_input_{args.as_of}.json"
    write_json(holdings_path, summary)
    write_json(
        monitor_path,
        {"schema_version": 1, "as_of": args.as_of, "holdings": monitor_holdings},
    )

    print(
        json.dumps(
            {
                "holdings_path": str(holdings_path),
                "monitor_path": str(monitor_path),
                "positions": len(holdings),
                "symbols": symbols,
                "equity": account.get("equity"),
                "long_mv": account.get("long_market_value"),
                "cash": account.get("cash"),
                "sector_weights": summary["sector_weights_gross_long"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
