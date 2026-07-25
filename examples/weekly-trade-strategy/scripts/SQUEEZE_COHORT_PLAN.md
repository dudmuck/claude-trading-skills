# Plan — wire `short-squeeze-radar` into the shortlong PEAD cohort

**Status: proposed, not implemented.** Nothing in `cohort_generate.py` changes until this is approved.

## Why bother

The cohort harness already gates the short side, but only on regime: a short candidate is
vetoed when the Markov state on SPY is a sticky Bull (`shorts_vetoed_by_gate`). That gate
answers "is it a bad week to be short anything?" It does not answer the question that
actually kills individual short entries — **"is this specific name already crowded with
shorts, so that any good news detonates it?"**

That is the failure mode a post-earnings drift short is most exposed to. The name has
already gapped down, the drift thesis says it keeps bleeding, and the position is fine
right up until a crowded short base covers into a bounce and the loss is several times the
edge being harvested.

`short-squeeze-radar` reads FINRA Reg SHO daily short-volume files — free, no auth, no key,
published every trading day — and computes `short_volume_ratio = (ShortVolume +
ShortExemptVolume) / TotalVolume` plus a rising-inflection detector (shorts piling in). That
is a direct, per-name measurement of the thing the cohort currently guesses at.

## What changes

**One new veto reason, symmetric with the existing two.** The cohort's funnel today is:

```
reaction threshold -> Markov regime gate -> drift-quality gate -> entry_side
```

Proposed:

```
reaction threshold -> Markov regime gate -> drift-quality gate -> crowding gate -> entry_side
```

The crowding gate only ever fires on the SHORT side. A crowded-short name is a *better*
long-side candidate if anything, so the long path is untouched.

### Field additions to each candidate record

| Field | Meaning |
|---|---|
| `short_volume_ratio` | latest session's FINRA ratio, 0-1 |
| `svr_trend_5d` | change in the 5-session mean ratio (positive = piling in) |
| `crowding_score` | 0-3, from the radar's own banding |
| `crowding_bits` | the human-readable reasons, same shape as `quality_bits` |

`gate_reason` gains a `crowded-short {score}/3` variant so a vetoed name explains itself in
the markdown report exactly like the drift-quality vetoes do today.

### Gate threshold

Start at **veto a short when `crowding_score >= 2`**, matching the existing
`--min-quality 2` default, and expose it as `--max-crowding` so it can be tuned or disabled
(`--max-crowding 4` = off) without a code change. Record vetoed names in a new
`would_enter.shorts_vetoed_by_crowding` list — the cohort already keeps
`shorts_vetoed_by_gate` and `quality_vetoed` separately, and keeping the third reason
distinct is what makes the backtest below possible.

## How to validate it before trusting it

**Do not turn the gate on live first.** The cohort's whole design is that it is a signal
test with reference-price marking and no execution noise, which makes it cheap to answer
this empirically:

1. **Backfill.** FINRA publishes daily files by date, so the crowding score is reconstructible
   for every cohort already generated (2026-05-26 onward). Compute it for every historical
   short candidate and write it alongside, without gating.
2. **Measure.** For the shorts that were actually entered, split realized return by
   `crowding_score`. The gate is justified only if high-crowding shorts show materially worse
   realized returns — or materially fatter left tails, which is the real argument since the
   squeeze risk is a tail, not a mean.
3. **Check what it would have cost.** Count the shorts the gate would have vetoed that
   *worked*. A gate that removes 40% of the short book to avoid a tail that never showed up in
   this sample is a worse gate than no gate.
4. **Only then** enable it, and keep `shorts_vetoed_by_crowding` in the JSON so the same
   question can be re-asked every quarter.

Roughly a session's work for steps 1-2, and it reuses `backtest_cache/` the same way the
existing cohort backtest does.

## Cost and failure modes

- **API cost: zero.** FINRA files are static, no key, no rate limit worth worrying about. One
  fetch per trading day, cacheable, and the existing `backtest_cache/` pattern applies directly.
- **Coverage:** Reg SHO files cover consolidated NMS tape. Thinly traded names have noisy
  ratios; require a minimum total volume before trusting a score, and treat "no data" as
  score 0 (do not veto on absence — failing closed here would silently shrink the short book).
- **Semantics trap:** short *volume* ratio is not short *interest*. A high ratio means a lot
  of today's prints were short-marked, which includes market-maker hedging, not just directional
  bets. The bi-monthly short-interest file is the crowding-stock measure; the daily ratio is the
  crowding-flow measure. The radar reads both — keep them distinct in any writeup, and prefer
  the flow measure for a days-to-weeks drift horizon.

## Deliberately out of scope

- No change to the long side.
- No change to the Markov gate or the drift-quality gate.
- No change to entry/exit mechanics — this is a *filter*, and the harness still has no stop
  concept by design.
