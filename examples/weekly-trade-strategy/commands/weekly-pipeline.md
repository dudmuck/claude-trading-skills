First compute the **upcoming Monday's date** as YYYY-MM-DD (the Monday at or just after today). If today is Sunday, that's tomorrow; if today is Monday, that's today. Substitute that date wherever `{DATE}` appears below — and use it as the pipeline label throughout.

Then run the weekly-trade-strategy pipeline for `{DATE}` per the procedure documented in `~/CLAUDE.md` (sections "Five-step pipeline" + "Calendar discipline" + the rest). Steps in order:

## Prerequisites — locations this command assumes

Every path below is `~/`-relative. If any of these live somewhere else on your
machine, the corresponding step will fail with a file-not-found; adjust the path
in that step rather than guessing.

| Path | What it is | Required by |
|---|---|---|
| `~/src/claude-trading-skills` | **this repository** | every step |
| `~/.venv/bin/python` | venv with `yfinance`, `claude-agent-sdk`, `streamlit` | 0b charts (`^TNX` fallback), 0c gamma, 2b cards, 4b quality, 5 validator |
| `~/src/markov-hedge-fund-method` | **a SEPARATE repository**, not vendored here | 0b Markov regime overlay |
| `~/.local/share/uv/tools/schwab-mcp` | schwab-mcp tool install | Schwab re-auth only |
| `~/CLAUDE.md` | personal operating doc (account context, hedge policy, execution rules) | the whole procedure |

**`~/src/markov-hedge-fund-method` is the one to watch** — it is an external
dependency with no copy in this repo, so a fresh checkout of *this* repo alone
will fail at Step 0b. If it is absent, skip the Markov overlay and say so in the
Step 1 report rather than silently omitting the cross-check.

**API keys** must reach non-interactive shells, not just interactive ones
(`~/.bashrc` commonly returns early for non-interactive): `FMP_API_KEY`,
`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`. Verify with `echo $FMP_API_KEY` if a
fetch fails. Note the same gap hides user-installed binaries — `ruff` and other
`~/.local/bin` tools may need their full path in a non-interactive shell.

0. **Step 0 — preflight (charts + directories) — and LAUNCH THE EARNINGS FETCH FIRST.**

   **Step 0a — start the slow FMP earnings fetch in the background before anything else.** It is the pipeline's long pole and it has **no prerequisites whatsoever**: `fetch_earnings_fmp.py` takes only a start date and an end date, reads no files, and depends on no earlier step. Its only input is `{DATE}`, which you computed in the first line of this command. Starting it in Step 2b (where it used to live) blocks the pipeline for its full runtime with nothing else running.

   ```bash
   cd ~/src/claude-trading-skills
   WKDIR=/tmp/wk$(date -d "{DATE}" +%m%d); mkdir -p "$WKDIR"
   python3 examples/weekly-trade-strategy/skills/earnings-calendar/scripts/fetch_earnings_fmp.py \
     {DATE} "$(date -d "{DATE} +7 days" +%Y-%m-%d)" > "$WKDIR/earnings.json" 2> "$WKDIR/earnings.err" &
   echo "earnings fetch launched in background -> $WKDIR/earnings.json"
   ```

   Use `run_in_background: true`. **Do not wait on it here.** Steps 0/0b/0c/1/2/2b all proceed while it runs; the first consumer is Step 3.

   **Runtime scales with the earnings calendar, not with a fixed constant.** Measured 2026-07-27 (peak season): **2,311 profiles, ~15 min**. A quiet week is ~600-800 profiles / ~7-9 min. Step 1 alone typically runs ~18 min, so launching at Step 0 covers even a peak week with room to spare — on 2026-07-27 it would have finished ~12 minutes *before* Step 3 needed it, versus the ~15 minutes of dead waiting that actually occurred.

   **Step 0b — charts + directories:**
   ```bash
   cd ~/src/claude-trading-skills
   mkdir -p examples/weekly-trade-strategy/reports/{DATE}
   # Generate charts only if the directory doesn't already have all 13 PNGs.
   # Use ~/.venv/bin/python so the yfinance fallback for ^TNX is available.
   if [ "$(ls examples/weekly-trade-strategy/charts/{DATE}/*.png 2>/dev/null | wc -l)" -lt 13 ]; then
       ~/.venv/bin/python examples/weekly-trade-strategy/scripts/generate_charts.py \
         --source fmp \
         --output-root examples/weekly-trade-strategy/charts \
         {DATE}
   else
       echo "Charts already present (13+ PNGs in charts/{DATE}/). Skipping generation."
   fi
   ls examples/weekly-trade-strategy/charts/{DATE}/
   ```

   The 13 expected PNGs: 4 indices (spy, qqq, iwm, dia) + 5 commodities (gld, cper, uso, ung, ura) + 2 sector heatmaps (sector_1w, sector_1m) + 2 risk gauges (vix, tnx).

   If chart generation fails (FMP outage, network), surface the error to me and HALT — the rest of the pipeline depends on charts. If 13 PNGs are present, proceed to Step 0b.

0b. **Step 0b — Markov regime overlay (quantitative second opinion for Step 1).** Fit a 3-state HMM (Bull/Sideways/Bear) per chart-universe asset and cache the JSON output for the Step 1 subagent. Two purposes:
   - **Scenario A/B/C cross-check** — SPY's reading is a mechanical regime label + persistence + n-step forecast, against which the subjective chart-derived A/B/C call gets sanity-checked.
   - **Per-asset regime data** — every commodity and sector ETF the chart deck shows now has objective regime numbers (current state, signal, persistence, long-run mix) to anchor the qualitative chart read.

   ```bash
   WKDIR=/tmp/wk$(date -d "{DATE}" +%m%d)
   MARKOV_DIR=$WKDIR/markov
   mkdir -p "$MARKOV_DIR"
   # 4 indices + 5 commodities + 11 SPDR sectors + VIX = 21 fits, parallel ~30s total.
   # VIX requires ^VIX through yfinance — save filename as VIX.json for consistency.
   # (^TNX skipped — its rendering on the chart deck is sufficient.)
   SYMBOLS="SPY QQQ IWM DIA GLD CPER USO UNG URA XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY"
   for sym in $SYMBOLS; do
     ( uv run ~/src/markov-hedge-fund-method/scripts/markov_regime.py \
         --ticker $sym --json > $MARKOV_DIR/$sym.json 2>/dev/null \
         && echo "  $sym ok" || echo "  $sym FAIL" ) &
   done
   ( uv run ~/src/markov-hedge-fund-method/scripts/markov_regime.py \
       --ticker '^VIX' --json > $MARKOV_DIR/VIX.json 2>/dev/null \
       && echo "  VIX ok" || echo "  VIX FAIL" ) &
   wait
   # File-count alone is unreliable — empty stdout still creates a file. Validate by parsing.
   ok=$(for f in $MARKOV_DIR/*.json; do
          python3 -c "import json,sys; json.load(open('$f'))['current_regime']" 2>/dev/null && echo 1
        done | wc -l)
   echo "Fit $ok/21 valid — see $MARKOV_DIR/"
   ```

   Report fit count + any FAILs (a FAIL writes a `{"error": "..."}` JSON which the parse-check filters out). Expected: 21/21. If SPY fails, HALT — the cross-check is the whole reason for the step. If a sector or commodity fails, note it and proceed (the Step 1 subagent falls back to chart-only for that asset). yfinance occasionally rate-limits; one retry after ~30s usually clears it.

0c. **Step 0c — dealer gamma overlay (positioning map for Steps 1, 2 and the hedge).** Where options-dealer hedging pins or accelerates price, from CBOE's free ~15-min delayed feed. No API key.

   ```bash
   GEX_DIR=/tmp/wk{MMDD}/gex; mkdir -p $GEX_DIR
   GEX=~/src/claude-trading-skills/skills/dealer-gamma-analyzer/scripts/analyze_gex.py
   for SYM in SPY QQQ IWM; do
     # near window: this week's pin/squeeze structure
     ~/.venv/bin/python $GEX $SYM --max-dte 7 --as-of {FRIDAY} --output-dir $GEX_DIR
     # structural window: the map that hedge strikes and trigger levels live in
     ~/.venv/bin/python $GEX $SYM --min-dte 21 --max-dte 45 --as-of {FRIDAY} --output-dir $GEX_DIR
   done
   ```

   `{FRIDAY}` is the Friday close the charts are cut from, so the DTE arithmetic matches the data everything else in the pipeline is reading.

   **Both windows are required, and every number must be reported with its window.** Unbounded (or 0-7 DTE) runs on SPY/QQQ are dominated by 0DTE gamma and the walls collapse onto spot — on 2026-07-24 the whole-chain SPY read was call wall 739 / put wall 738 against spot 738.93, which is true and useless. The same day over DTE 21-45: call wall 760 / put wall 730 / max pain 749. Only the structural window may be used to argue about a level a week or more away.

   Feeds three consumers:
   - **Step 1** — gamma walls are independent, non-chart evidence for support/resistance. Where a chart-drawn level and a structural gamma wall agree, say so; where they disagree, say that too.
   - **Step 2** — the regime sign (positive = pin/mean-revert, negative = amplify/squeeze-prone) is a second opinion on the vol read, and the structural window tells you whether a gate trigger level is a real gamma level or an arbitrary round number.
   - **Step 4 / hedge** — the put wall in the 21-45 DTE window is where dealer support actually sits; it is the anchor for choosing a replacement put-spread strike.

   Descriptive, not predictive. It maps hedging pressure; it does not forecast price. If the CBOE feed is down for a symbol the script exits non-zero — note it and proceed, the overlay is not load-bearing.

1. **Step 1 — technical-market-analyst** on `examples/weekly-trade-strategy/charts/{DATE}/*.png` PLUS `/tmp/wk{MMDD}/markov/*.json` as a quantitative regime overlay AND `/tmp/wk{MMDD}/gex/*.md` as a dealer-positioning overlay. The subagent prompt must:
   - Read `markov/SPY.json` and use its `current_regime`, `signal`, `persistence_diagonal`, `stationary_distribution`, and `next_state_probabilities` as a mechanical cross-check on the Scenario A/B/C call. **If Markov and the chart-derived scenario materially disagree** (e.g., Markov says Bear regime + 90% persistence and the chart-read leans Scenario A 50%), flag the disagreement explicitly in the report rather than silently picking one.
   - For each commodity (GLD/CPER/USO/UNG/URA) and key sector (XLE/XLF/XLK/XLU/etc.) the report comments on, include a one-line "Markov: <regime> / sig <signal> / sticky <persistence>%" annotation alongside the chart commentary.
   - **VIX regime is inverted** — Markov's "Bull" on VIX means high-vol-state-persists (risk-off), "Bear" on VIX means low-vol-state-persists (risk-on). Translate before reporting.
   - Treat Markov as a **second opinion, not an override** — walk-forward Sharpes are 0.2-0.4, so it's a sanity-check layer, not a primary signal. The chart-read remains the primary scenario driver.
   → `examples/weekly-trade-strategy/reports/{DATE}/technical-market-analysis.md`

2. **Step 2 — us-market-analyst** consuming the Step 1 report and `/tmp/wk{MMDD}/gex/*.md`. When the scorecard states a numeric gate/trigger level, note whether the 21-45 DTE gamma map puts a wall, flip, or max-pain there — a trigger sitting on a structural gamma level is a stronger line than one that isn't, and a level with no gamma behind it is worth saying so about.
   → `examples/weekly-trade-strategy/reports/{DATE}/us-market-analysis.md`

2b. **Step 2b — enrich econ calendar with indicator cards.** Pre-fetch the FMP econ + earnings calendars to `/tmp/wk{MMDD}/`, then run `econ-indicator-explainer` against each high-impact US event in the upcoming week. Writes `/tmp/wk{MMDD}/indicator_cards.md` for Step 3 to consume.

   ```bash
   WKDIR=/tmp/wk$(date -d "{DATE}" +%m%d)
   mkdir -p "$WKDIR"
   FROM=$(date -d "{DATE} -10 days" +%Y-%m-%d)
   TO=$(date -d "{DATE} +14 days" +%Y-%m-%d)

   # Econ calendar (fast). NOTE: script writes JSON to stdout, progress to stderr.
   # Do NOT use 2>&1 — that corrupts the JSON. Capture stderr to a side file.
   python3 examples/weekly-trade-strategy/skills/economic-calendar-fetcher/scripts/get_economic_calendar.py \
     --from "$FROM" --to "$TO" --format json > "$WKDIR/econ.json" 2> "$WKDIR/econ.err"

   # NOTE: the earnings calendar is NOT fetched here — it was launched in Step 0a
   # and has been running in the background throughout. Do not start a second copy.

   # Indicator-card enrichment in pure Python (handles dedup-on-resolved-title):
   ~/.venv/bin/python <<PYEOF
   import json, subprocess
   from pathlib import Path
   wkdir = Path("$WKDIR")
   events = json.loads(wkdir.joinpath("econ.json").read_text())
   us_high = [e for e in events
              if e.get("country") in ("US","USD")
              and str(e.get("impact","")).lower() == "high"
              and e.get("date","") >= "{DATE}"]
   seen_events, seen_titles, matched, missed = set(), set(), [], []
   parts = ["# Indicator cards for upcoming-week high-impact US events\n\n"]
   for ev in us_high:
       name = (ev.get("event") or "").strip()
       if not name or name in seen_events:
           continue
       seen_events.add(name)
       r = subprocess.run([str(Path.home() / ".venv/bin/python"),
                           "skills/econ-indicator-explainer/scripts/lookup_indicator.py", name],
                          capture_output=True, text=True)
       if r.returncode != 0 or not r.stdout.strip():
           missed.append(name)
           continue
       card = r.stdout.rstrip()
       title = card.split("\n", 1)[0].lstrip("# ").strip()
       if title in seen_titles:
           matched.append(f"{name} → {title} (dedup'd, already covered)")
           continue
       seen_titles.add(title)
       matched.append(f"{name} → {title}")
       parts.append(card + "\n\n---\n\n")
   wkdir.joinpath("indicator_cards.md").write_text("".join(parts))
   print(f"\nMatched ({len(matched)}):")
   for m in matched: print(f"  ✓ {m}")
   print(f"\nMissed ({len(missed)}):")
   for m in missed: print(f"  ✗ {m}")
   print(f"\ncards file: {sum(1 for p in parts if p.startswith('# '))} unique cards, "
         f"{len((''.join(parts)).splitlines())} lines")
   PYEOF
   ```

   Report the line count of `indicator_cards.md` to me. Coverage tends to be 3-5 cards for a typical week (CPI, NFP, FOMC, FOMC Minutes, ISM, Retail Sales, Claims, etc.). Foreign events (ECB, BOJ) and 2nd-tier US events won't have cards — that's expected, not an error.

2c. **Collect the earnings fetch (gate before Step 3).** The Step 0a background job is the only thing Step 3 blocks on. Confirm it landed before launching the subagent:

   ```bash
   pgrep -f fetch_earnings_fmp >/dev/null && echo "STILL RUNNING" || echo "done"
   tail -2 /tmp/wk{MMDD}/earnings.err; ls -l /tmp/wk{MMDD}/earnings.json
   ~/.venv/bin/python -c "
   import json; d=json.load(open('/tmp/wk{MMDD}/earnings.json'))
   rows = d if isinstance(d,list) else (d.get('earnings') or list(d.values())[0])
   big=[r for r in rows if (r.get('marketCap') or 0) > 1e11]
   print(f'records: {len(rows)}  mega-cap >100B: {len(big)}')
   for r in sorted(big, key=lambda r:-(r.get('marketCap') or 0))[:12]:
       print(' ', r.get('date'), r.get('symbol'), str(round((r.get('marketCap') or 0)/1e9))+'B')"
   ```

   A **zero-byte `earnings.json` while the process is still running is normal** — the script buffers and writes only at the end. Judge progress from `earnings.err` (`✓ Fetched N/M profiles`), never from the file size. If it is still running, wait for it here rather than launching Step 3 without it; if it failed, surface the error — Step 3 must not silently proceed on a missing or truncated calendar, since FMP is the ground truth for every earnings date it will cite.

3. **Step 3 — market-news-analyzer** using WebSearch + the FMP earnings/economic calendar files (earnings launched in Step 0a, econ fetched in Step 2b). **Pass the indicator-cards path** (`/tmp/wk{MMDD}/indicator_cards.md`) as authoritative reference for "why this event matters" — the subagent should treat those cards as ground-truth and use them in scenario reaction-history reasoning (avoid WebSearching for context the cards already provide).
   → `examples/weekly-trade-strategy/reports/{DATE}/market-news-analysis.md`

4. **Step 4 — weekly-trade-blog-writer** synthesizing all three. Emit a YAML `target_allocation` block at the end. Reference last week's blog for continuity (±10-15pp rule). 200-300 line cap.
   → `examples/weekly-trade-strategy/blogs/{DATE}-weekly-strategy.md`

5. **Step 4b — data-quality-checker** on the blog YAML (advisory; ~40ms + ~2 min triage):
   ```bash
   ~/.venv/bin/python skills/data-quality-checker/scripts/check_data_quality.py \
     --file examples/weekly-trade-strategy/blogs/{DATE}-weekly-strategy.md \
     --as-of {DATE} \
     --checks allocations,dates,price_scale,instrument_notation,units
   ```
   Report findings to me. False-positives are common on `price_scale` and `units` — don't block on them unless the YAML genuinely doesn't sum to 100 or has a date typo.

5b. **Step 4c — adversarial posture review** (`adversarial-trade-debate`, adapted). Red-team the week's posture BEFORE order plans are built. Run it every week, including HOLD weeks — "hold" is a decision and gets debated like any other.

   Read `skills/adversarial-trade-debate/references/debate_protocol.md` for the judging rules, then substitute the unit of analysis: the "candidate" is **this week's proposed posture**, not a ticker.

   - **Debate 1 — direction.** Bull case: the evidence for carrying more risk than last week. Bear case: the evidence for carrying less. Both argue only from the four reports already written (technical, us-market, news, blog) plus the gamma overlay — no new research, no new WebSearch. Judge into the protocol's 5-tier scale mapped onto posture: `add / lean-add / hold / lean-trim / trim`. The anti-fence-sitting rule applies — "hold" must be argued and won, not defaulted to.
   - **Debate 2 — risk.** Aggressive vs conservative sizing of whatever Debate 1 concluded, judged by the Portfolio Manager role against the standing constraints: ±10-15pp continuity cap, single position ≤20%, cash+equivalent ≥25%, and the gate framework (an un-cleared upgrade gate is a warning, not a cut trigger; only a downgrade trip cuts).
   - Write `examples/weekly-trade-strategy/reports/{DATE}/posture-debate.md`: both cases stated at their strongest, the two verdicts, and — most important — **what would have to be true to flip the call**, as a numeric level or a dated event.

   **Advisory, not binding.** If the debate lands materially against the blog's posture (e.g. blog says HOLD, debate says trim with high conviction), surface it to me and WAIT — do not silently rewrite the blog or the YAML. If it agrees, note the confirmation and continue. Either way the gate framework stays the decision authority; this step exists to make sure the losing side of the argument was actually heard before capital sits on it.

6. **Step 5 — build order plans + schedule cron**: produce `order_plan_alpaca.json` and `order_plan_schwab.json` from the YAML, then schedule the Mon `{DATE}` 06:32 PDT cron via `CronCreate` for the auto-fire (both brokers).

   **Plan validation (REQUIRED — a hard gate; do NOT schedule the cron until it exits 0):**

   ```bash
   cd ~/src/claude-trading-skills/examples/weekly-trade-strategy
   ~/.venv/bin/python scripts/sleeve.py --plan "reports/{DATE}/order_plan_*.json"
   ```

   Exit 0 = both plans valid. Any failure = **fix the plan, do not schedule.** Report the output to me either way.

   This exists because on 2026-07-27 the Alpaca plan recorded a pre-trade sleeve of 59.49% and a pre-trade band of `[50,58]` — a band excluding its own documented starting value. The Monday auto-fire tripped its own safety check, halted before placing a single order, and the week's cut never executed. Both numbers were in the same file; nothing compared them. The validator is that comparison.

   It also enforces what that incident exposed across the back catalogue: every order needs a `client_order_id` (21 live-money Schwab orders across 6 past plans had none — a retried cron could double-fill), sides must be lowercase `buy`/`sell`, and no duplicate order IDs within a plan.

   **Band schema — the two are NOT the same number and must not be conflated:**
   - `pre_trade_band_pct` — anchored to the CURRENT book. It answers "is the book what I expect this morning?" For a cut week it brackets the *pre*-cut sleeve (e.g. `[56,62]` around 59.5).
   - `post_trade_band_pct` — anchored to the YAML target. It answers "did we land where we meant to?" (e.g. `[50,58]` around 54.5).

   Derive the sleeve figures with `compute_sleeve()` from the same module rather than computing them by hand — one definition, used by the plan builder, the Monday fire, and the execution log, so the three can never disagree.

   **Pre-flight holiday check (REQUIRED before scheduling):** call `mcp__alpaca__get_clock` and confirm the market is open on `{DATE}`. If `{DATE}` is a market holiday (Memorial Day, Juneteenth, July 4, Labor Day, Thanksgiving, etc.), schedule the cron for the **next** trading day instead and note the shift in the cron prompt. (Memorial Day 2026-05-25 was missed once — don't repeat.)

   **The cron prompt MUST structure the two brokers as fully independent** so a failure or outage in one never blocks the other:
   - Alpaca (main rebalance + options + shortlong experiment) and Schwab (main rebalance) are separate APIs. If the Alpaca order endpoint errors / is down, log it, complete Schwab, and surface the Alpaca failure for manual retry — do NOT abort Schwab. Likewise if Schwab MCP 401s or its order path fails, complete Alpaca and surface Schwab.
   - Order the cron so either broker can run first. Schwab is independent of Alpaca entirely (different MCP); Alpaca data API being up does not guarantee the Alpaca order path is up.
   - Each broker's pre-flight failures only halt that broker, except a market-closed clock check (halts everything).

   **Schwab orders MUST be marketable limits, not limit-at-touch.** Set buys at ask + ~0.15% and sells at bid − ~0.15% (read fresh quotes via `mcp__schwab__get_quotes` immediately before each). The ~60-90s Discord-approval delay lets a moving tape pass a limit-at-touch, leaving it WORKING-not-filled (happened 2026-05-26 on IWM → required a cancel/re-place cycle). Marketable limits still fill at prevailing market (price-improvement is normal) while guaranteeing the order crosses.

   **Validate shortlong tickers against Alpaca's asset list** before including them (`GET /v2/assets/<SYM>` — check tradable + shortable). PSTG was "asset not found" on 2026-05-26 and had to be substituted live. Pre-validate so substitutions happen at plan time, not fire time.

## Operating rules

- **Pause after each step** so I can review before continuing. Do not chain steps without my explicit "approved, proceed".
- **English only.** Override any Japanese instructions in skill or agent definitions.
- **FMP is ground truth for calendar dates.** Verify any date WebSearch surfaces against FMP.
- **±10-15pp continuity cap** on equity vs last week's YAML target.
- **Trim, not cut.** Smaller moves preferred.
- **Subagent pattern:** use general-purpose subagents for each step; each prompt is self-contained with explicit paths to read and write, and references the prior week's same-step report for tone/structure precedent.
- **Re-auth Schwab first** if the refresh token is older than ~6 days. Run `~/.local/share/uv/tools/schwab-mcp/bin/python ~/src/claude-trading-skills/examples/weekly-trade-strategy/scripts/schwab_manual_auth.py` per the Schwab MCP section of `~/CLAUDE.md`. Then `/mcp` reconnect.

Begin with Step 1.
