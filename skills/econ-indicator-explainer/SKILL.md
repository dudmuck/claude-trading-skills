---
name: econ-indicator-explainer
description: "Static knowledge base for ~30 economic indicators. Given an indicator name (or FMP event name like 'Consumer Price Index (CPI) YoY'), returns a structured 'why it matters' card with: what it is, how it's measured, why it matters for markets, typical 60-min reaction history (SPY/TLT/DXY/VIX), and what to watch for in today's print. Used by morning-trading-briefing skill to enrich raw economic-calendar-fetcher output. No API calls — fast, deterministic, version-controlled."
---

# Econ Indicator Explainer

Look up the "why it matters" context for an economic indicator. Designed to pair with `economic-calendar-fetcher`, which provides the *schedule + consensus + actual*, while this skill provides the *interpretive context*.

## Why a separate skill

The FMP API tells you "CPI releases at 8:30 ET, consensus 3.1%". It does not tell you what CPI *is*, why it matters, or how markets historically react. That content doesn't change — so we write it once, store it in `references/indicators.md`, version it in git, and never let the LLM regenerate it (where hallucinations creep in).

## Interface

### Lookup one indicator
```bash
python3 skills/econ-indicator-explainer/scripts/lookup_indicator.py "CPI YoY"
python3 skills/econ-indicator-explainer/scripts/lookup_indicator.py "Consumer Price Index (CPI) YoY"   # FMP alias
python3 skills/econ-indicator-explainer/scripts/lookup_indicator.py --json "Core PCE"   # machine-readable
```

### List all known indicators
```bash
python3 skills/econ-indicator-explainer/scripts/lookup_indicator.py --list
```

## Card schema

Each indicator card in `references/indicators.md` has:

| Field | Purpose |
|---|---|
| `canonical` | Display name |
| `short_name` | Short label for tables |
| `category` | inflation / labor / growth / sentiment / housing / monetary / energy |
| `country` | US, EU, JP, CN, Global |
| `release_time_et` | When it drops (Eastern time) |
| `frequency` | monthly, weekly, quarterly, ad-hoc |
| `release_source` | BLS, BEA, Census, ISM, Fed, etc. |
| `fmp_aliases` | Names the FMP API uses for this event (lookup keys) |
| `importance` | tier-1 / tier-2 / global |
| **Body sections** | What / How measured / Why matters / Reaction history / Watch for |

## Coverage (30 indicators)

**Inflation (5):** CPI, Core CPI, PPI, Core PPI, PCE, Core PCE
**Labor (4):** NFP, Unemployment Rate, Average Hourly Earnings, JOLTS, Jobless Claims
**Growth (4):** GDP, Retail Sales, Industrial Production, Durable Goods
**Sentiment / Surveys (5):** ISM Mfg PMI, ISM Services PMI, U-Mich Sentiment, Conference Board Consumer Confidence, Philly Fed
**Housing (3):** Housing Starts, Building Permits, Existing Home Sales
**Monetary (3):** FOMC Rate Decision, FOMC Minutes, FOMC SEP / Dot Plot
**Global (5):** ECB Rate Decision, BOJ Rate Decision, China CPI, China Manufacturing PMI, OPEC+ Meeting
**Energy (1):** EIA Crude Oil Inventories

## How morning-trading-briefing uses this

1. `economic-calendar-fetcher` fetches today's releases from FMP → list of event names
2. For each event, call `lookup_indicator.py --json "<event name>"`
3. Render the card into the briefing's macro section
4. If no match found, log to `state/unmapped_indicators.log` for the user to add later

## Updating the knowledge base

When the user wants to add an indicator (or refine reaction history):
1. Edit `references/indicators.md` directly
2. Append a new card following the existing schema
3. Commit to git — the change is version-controlled, no code edits needed

When a Fed regime shift changes how markets react (e.g. inflation matters more than employment, or vice versa), update the `## Reaction history` and `## Watch for` sections. Keep `## What it is` and `## How it's measured` frozen — those don't change.

## Future enhancements (not blocking)

- `state/reaction_history/{indicator}.csv` — record actual SPY/TLT/DXY moves after each release; over time, this overrides the textbook `## Reaction history` with your *own* empirical data.
- `--regime` flag — different reaction-history blurb based on current macro regime (cutting cycle vs. hiking cycle vs. holding).
