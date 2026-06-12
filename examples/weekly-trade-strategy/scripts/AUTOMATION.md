# Automation: `cohort_cron.sh` and `parabolic_cron.sh`

Two crontab-driven wrappers keep the strategy-research datasets accumulating without
human attention. They were created after a scheduled review was missed from a calendar
reminder — a hole in a forward-test series is unrecoverable, so the cadence lives in
`cron`, and calendar events are demoted to verification glances.

Both wrappers are plain `bash` + `python3` (no Claude/LLM involvement at runtime), source
`~/.profile` for API keys (`FMP_API_KEY`), and put `~/.local/bin` on `PATH` (for `uv`,
which runs the Markov regime fits). They never place broker orders.

## Cron schedule (user crontab, local time = US Pacific here)

```cron
# Forward-test cohort harness
3 13 * * 0   .../scripts/cohort_cron.sh generate     # Sunday 13:03
7 13 * * 5   .../scripts/cohort_cron.sh track        # Friday 13:07 (post-close)

# Parabolic-short daily scan
12 13 * * 1-5 .../scripts/parabolic_cron.sh          # weekdays 13:12 (post-close)
```

Install/verify/remove with `crontab -l` / `crontab -e`. Each script header contains an
idempotent install snippet.

---

## 1. `cohort_cron.sh` — earnings long/short forward test

Maintains the weekly **cohort dataset** that decides whether the earnings-week
long/short strategy ever earns real capital. Two sub-commands:

### `generate` (Sundays)

Runs `cohort_generate.py` twice:

| Run | Mode | What it does |
|---|---|---|
| `--date <next Monday> --mode pre` | **pre** | Screens names *reporting in the upcoming week*; side from the fundamental ranker (`rank_earnings_candidates.py` composite); enters *before* the print. Kept running as the control arm — the 2023-2026 backtest says this is a coin-flip on the earnings binary. |
| `--date <today> --mode post --min-reaction 5 --no-shorts` | **post / PEAD** | Screens names that *already reported* in the trailing week; side = print-reaction direction; enters *after* the print. Flags encode the backtest verdict: only gap-**up** longs with reaction ≥ 5% are entered (gap-down large-cap shorts had negative expectancy every year — they mean-revert). Short candidates are still logged and as-if-tracked via the disabled-side veto, so the evidence keeps accumulating. |

Output: `~/shortlong_cohorts/cohort_<date>[_post].{json,md}` — every candidate with
entry-reference price, ranker scores, print reaction, Markov regime/persistence, and
the would-enter / vetoed decision. No orders are placed; this is a signal test.

### `track` (Fridays, post-close)

Runs `cohort_track.py`: marks **all** logged cohorts to market (FMP quote vs entry-ref),
prints per-cohort tables plus cross-cohort aggregates **per entry mode** (the pre-vs-post
A/B), the Markov-gate scorecard (did vetoed shorts dodge losses?), and appends a dated
per-name snapshot to `~/shortlong_cohorts/marks.jsonl` — the longitudinal series from
which T+5/14/30/90 horizon returns are read.

Log: `~/shortlong_cohorts/cron.log`.

### Related Python scripts (this directory)

| Script | Role |
|---|---|
| `cohort_generate.py` | Weekly cohort generator (both modes). FMP-efficient: `earnings-calendar ∩ company-screener` mcap pre-filter (~150-280 calls/week instead of ~800). Markov gate: native fit via `markov_regime.py` (external repo, `MARKOV_REGIME_SCRIPT` env-overridable). |
| `cohort_track.py` | Mark-to-market + aggregate analysis + `marks.jsonl` appender. |
| `rank_earnings_candidates.py` | The fundamental long/short composite scorer the pre mode (and post-mode annotations) use. |
| `cohort_backtest.py` | One-shot historical replay (2023-2026, FMP **Premium** endpoints, disk-cached). Produced the verdict the post-mode flags encode: long-only, ≥5% reaction, ~+1pp/name excess @T+14 for the ≥10% bucket. Not on a schedule — re-run only to test new hypotheses (free against the cache). |
| `shortlong_review.py` | Checkpoint reviewer for the original 2026-05-26 live paper basket (separate from the cohort signal test; needs Alpaca env keys). Run manually at T+30/T+90. |

### The decision rule this feeds

Real cash only when ≥10 forward post-mode cohorts confirm the backtested expectancy
(~+1pp/name excess at T+14, equal-weight basket). If the forward series persistently
misses it, the edge decayed and the strategy stops. Pre-committed before the data
arrived; see `~/earnings_ranker_journal.md` (local, not in repo).

---

## 2. `parabolic_cron.sh` — daily parabolic-short scan

A standing scan for the **one short archetype with evidence behind it**: the genuinely
parabolic name (the forward test's only winning short was the most extreme-valuation,
near-vertical chart; every "merely expensive" short lost). Runs Phase 1 of
`skills/parabolic-short-trade-planner` every weekday after the close.

Steps per run:

1. **Universe refresh** — one `company-screener` call: US common stocks ≥ $10B
   (~950 names) → `~/parabolic_watch/universe.csv`. This sidesteps the
   S&P-500-constituent endpoint (paywalled on FMP Starter) via Phase 1's
   `--universe finviz-csv` flag, and is a broader universe anyway.
2. **Phase 1 screen** — `screen_parabolic.py --mode safe_largecap --max-api-calls 3000`
   (5-factor: MA extension / acceleration / volume climax / range expansion /
   liquidity → A-D grades). Output: `~/parabolic_watch/parabolic_short_<date>.{json,md}`.
3. **Alert** — if any A/B-grade candidates exist, a loud line goes to the log and the
   date+tickers are appended to `~/parabolic_watch/CANDIDATES_ALERT`. Most days the
   watchlist is empty — that is the expected steady state, not a failure.

Log: `~/parabolic_watch/cron.log`.

### Related Python scripts (in `skills/parabolic-short-trade-planner/scripts/`)

| Script | Phase | When it runs |
|---|---|---|
| `screen_parabolic.py` | 1 — watchlist | Daily, from this cron |
| `generate_pre_market_plan.py` | 2 — trigger plans (ORL break / first red 5-min / VWAP fail), sizing, SSR state | **Manual**, pre-market the morning after an A/B alert |
| `monitor_intraday_trigger.py` | 3 — intraday FSM against 5-min bars | **Manual**, intraday on plan days (`watch -n 60` or 5-min cron) |

No order ever fires from the cron. Phase 2/3 are paper-only (Alpaca paper account)
until a forward record justifies more — the same evidence bar as the cohort harness.

---

## Operational notes

- **Environment:** cron runs with a bare environment. Both wrappers handle this by
  sourcing `~/.profile` (must export `FMP_API_KEY`) and extending `PATH`. If a run
  logs an auth error, check that the key is exported in `~/.profile`, not only
  `~/.bashrc` (which non-interactive shells skip).
- **Verifying a run fired:** `tail ~/shortlong_cohorts/cron.log` / `tail
  ~/parabolic_watch/cron.log` — every invocation writes a timestamped start/OK/FAILED
  line. `systemctl is-active cron` confirms the daemon.
- **FMP budget:** weekly cohorts ~150-300 calls; daily parabolic ~1000-2500 calls;
  both trivial against a 300 calls/min plan limit and 20 GB/mo bandwidth.
- **Failure isolation:** a failed step logs `FAILED (exit N)` and never blocks the
  other steps or later runs; caches make re-runs cheap and idempotent (same-date
  outputs are overwritten, not duplicated).
