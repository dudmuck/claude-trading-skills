#!/usr/bin/env bash
# Daily parabolic-short scan (Phase 1 of skills/parabolic-short-trade-planner).
#
# Why: the one short archetype with evidence behind it is the GENUINELY parabolic
# name (cohort #0: CRDO — the only winning short; "merely expensive" shorts all
# lost). This standing scan watches for that rare setup daily; most days it finds
# nothing, which is expected and fine.
#
# FMP-Starter note: the S&P-500-constituent endpoint is paywalled (402/403), so the
# universe comes from /stable/company-screener (works on Starter): US common stocks
# >= $10B, ~950 names, 1 call. Phase 1 then pulls 60d bars per name (~1000 calls,
# rate-limited — fine vs the 300/min plan limit with the client's built-in pacing).
#
# Install (idempotent):
#   crontab -l | { cat; echo '12 13 * * 1-5 <this script>'; } | crontab -
#   (weekdays 13:12 local = just after the 13:00 PT close)
#
# When the watchlist has A/B candidates: run Phase 2 pre-market next morning
# (generate_pre_market_plan.py --candidates-json <json> --broker alpaca) and
# Phase 3 intraday (monitor_intraday_trigger.py) — PAPER ONLY (shortlong account)
# until the forward record justifies more. No order fires from this cron.

set -u
[ -f "$HOME/.profile" ] && . "$HOME/.profile"
export PATH="$HOME/.local/bin:$PATH"

REPO="$HOME/src/claude-trading-skills"
SCREEN="$REPO/skills/parabolic-short-trade-planner/scripts/screen_parabolic.py"
OUT="$HOME/parabolic_watch"
LOG="$OUT/cron.log"
mkdir -p "$OUT"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# 1. Refresh the universe (1 FMP call; survives a failure by reusing yesterday's CSV).
python3 - <<'PY' >> "$LOG" 2>&1 || log "universe refresh FAILED (reusing existing CSV)"
import os, json, urllib.request, urllib.parse
key = os.environ["FMP_API_KEY"]
url = "https://financialmodelingprep.com/stable/company-screener?" + urllib.parse.urlencode({
    "marketCapMoreThan": 10_000_000_000, "isActivelyTrading": "true", "limit": 5000, "apikey": key})
with urllib.request.urlopen(url, timeout=40) as r:
    rows = json.load(r)
US = {"NASDAQ", "NYSE", "AMEX"}
syms = sorted({r["symbol"] for r in rows
               if not r.get("isEtf") and not r.get("isFund")
               and (r.get("exchangeShortName") or "").upper() in US and r.get("symbol")})
open(os.path.expanduser("~/parabolic_watch/universe.csv"), "w").write("\n".join(syms) + "\n")
print(f"universe refreshed: {len(syms)} names")
PY

# 2. Run the Phase 1 screen.
log "screen start"
python3 "$SCREEN" \
  --mode safe_largecap \
  --universe finviz-csv --universe-csv "$OUT/universe.csv" \
  --max-api-calls 3000 \
  --output-dir "$OUT" >> "$LOG" 2>&1 \
  && log "screen OK" || { log "screen FAILED (exit $?)"; exit 1; }

# 3. Loud marker when actionable (A/B-grade) candidates appear — most days: none.
TODAY=$(date +%F)
JSON=$(ls -t "$OUT"/parabolic_short_*"$TODAY"*.json 2>/dev/null | head -1)
if [ -n "${JSON:-}" ]; then
  HITS=$(python3 -c "
import json,sys
d=json.load(open('$JSON'))
cands=[c for c in d.get('candidates',[]) if c.get('rank') in ('A','B')]
print(','.join(c['ticker'] for c in cands))
" 2>/dev/null)
  if [ -n "$HITS" ]; then
    log "*** A/B CANDIDATES: $HITS — run Phase 2 pre-market (see $JSON) ***"
    echo "$TODAY $HITS" >> "$OUT/CANDIDATES_ALERT"
  else
    log "no A/B candidates today (expected most days)"
  fi
fi
