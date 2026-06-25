#!/usr/bin/env bash
# Cron wrapper for the shortlong-basket checkpoint review (shortlong_review.py).
#
# Why: the T+14 and T+30 reviews were both MISSED when they depended only on a
# Google Calendar reminder (a human has to run the local script). A hole in a
# forward-test checkpoint series is unrecoverable past the date, so the firing
# lives in cron. The review is analysis-only — it never modifies positions.
#
# Usage:  shortlong_cron.sh <T-label>     e.g.  shortlong_cron.sh T+90
#
# Install the remaining checkpoint(s) (one-shot dates; crontab has no native
# "run once" so we self-disable after firing by checking the file):
#   crontab -l | { cat; echo '5 7 24 8 * $HOME/.../scripts/shortlong_cron.sh T+90'; } | crontab -
#   (Mon 2026-08-24 07:05 local — T+90 of the 5/26 basket)
#
# Cron runs bare: source the profile for the SHORTLONG Alpaca keys + PATH for uv.

set -u
[ -f "$HOME/.profile" ] && . "$HOME/.profile"
export PATH="$HOME/.local/bin:$PATH"

LABEL="${1:?usage: shortlong_cron.sh <T-label>}"
LOG="$HOME/shortlong_cohorts/cron.log"
REC="$HOME/shortlong_paper_2026-05-26.md"
log() { echo "[$(date '+%F %T')] shortlong $*" >> "$LOG"; }

# Idempotency: skip if this label's section already exists in the record.
if grep -q "^## ${LABEL} Review" "$REC" 2>/dev/null; then
  log "$LABEL already present in record — skipping"
  exit 0
fi

if [ -z "${APCA_API_KEY_ID_SHORTLONG:-}" ]; then
  log "$LABEL FAILED — APCA_API_KEY_ID_SHORTLONG not in environment"
  exit 1
fi

python3 "$HOME/shortlong_review.py" --label "$LABEL" >> "$LOG" 2>&1 \
  && log "$LABEL OK (appended to $REC)" || log "$LABEL FAILED (exit $?)"
