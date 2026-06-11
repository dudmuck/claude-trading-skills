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
    python3 "$SCRIPTS/cohort_generate.py" --date "$TODAY"    --mode post >> "$LOG" 2>&1 \
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
