#!/usr/bin/env bash
# Cron wrapper for the forward-test cohort harness (cohort_generate.py / cohort_track.py).
#
# Why this exists: the cohort dataset only has value if the weekly cadence never
# skips (a missed week is a hole in the forward test; a missed mark is a hole in
# the T+5/14/30/90 series). Humans miss calendar reminders — cron doesn't.
#
# Install (idempotent; survives reboots and Claude sessions, unlike CronCreate):
#   crontab -l 2>/dev/null | grep -v cohort_cron.sh > /tmp/ct
#   echo '3 13 * * 0 $HOME/src/claude-trading-skills/examples/weekly-trade-strategy/scripts/cohort_cron.sh generate' >> /tmp/ct
#   echo '7 13 * * 5 $HOME/src/claude-trading-skills/examples/weekly-trade-strategy/scripts/cohort_cron.sh track' >> /tmp/ct
#   crontab /tmp/ct
#
#   Sun 13:03 local  generate  -> next week's PRE cohort + the ended week's POST cohort
#   Fri 13:07 local  track     -> mark all cohorts to market (post-close), append marks.jsonl
#
# Cron runs with a bare environment: source the login profile for FMP_API_KEY etc.
# and put ~/.local/bin (uv, for the Markov fits) on PATH.

set -u
[ -f "$HOME/.profile" ] && . "$HOME/.profile"
export PATH="$HOME/.local/bin:$PATH"

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/shortlong_cohorts/cron.log"
mkdir -p "$HOME/shortlong_cohorts"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

case "${1:-}" in
  generate)
    # PRE cohort for the upcoming week (run on Sunday -> next Monday's window),
    # POST/PEAD cohort for the week that just ended (trailing-window reporters).
    NEXT_MON=$(date -d "next Monday" +%F)
    TODAY=$(date +%F)
    log "generate: pre --date $NEXT_MON + post --date $TODAY"
    python3 "$SCRIPTS/cohort_generate.py" --date "$NEXT_MON" --mode pre  >> "$LOG" 2>&1 \
      && log "pre cohort OK" || log "pre cohort FAILED (exit $?)"
    # Backtest-tuned post mode (2026-06-11, n=3489 sided events over 152 weeks):
    # long-only (gap-down shorts mean-revert; negative expectancy every full year),
    # |reaction| >= 5% (the 3-5% bucket adds ~nothing over the market base rate;
    # the >=5% pocket showed positive excess every year, ~+1.4pp @T+14 for >=10%).
    # Shorts are still logged + as-if-tracked via the disabled-side veto.
    #
    # 2026-07-02 widening: mcap floor 20B -> 5B (PEAD is empirically stronger in
    # mid-caps — thinner coverage, slower price discovery; the $20B funnel was
    # starving: ~9 names/week -> ~1 entry). Affordable because the generator now
    # reaction-checks BEFORE ranking (sub-threshold names cost 1 FMP call, not 8)
    # and gates would-enter on drift-quality (default --min-quality 2: EPS/rev
    # surprise + volume + close-location must confirm the pop).
    python3 "$SCRIPTS/cohort_generate.py" --date "$TODAY" --mode post \
      --min-reaction 5 --no-shorts --min-mcap 5e9 >> "$LOG" 2>&1 \
      && log "post cohort OK" || log "post cohort FAILED (exit $?)"
    ;;
  track)
    log "track: marking all cohorts"
    python3 "$SCRIPTS/cohort_track.py" >> "$LOG" 2>&1 \
      && log "track OK" || log "track FAILED (exit $?)"
    ;;
  *)
    echo "usage: $0 {generate|track}" >&2
    exit 2
    ;;
esac
