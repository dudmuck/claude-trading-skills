#!/usr/bin/env python3
"""Friday web-sentiment overlay for the PEAD forward-test cohort.

ADVISORY layer that sits BESIDE the cohort, never inside it. It reads the
newest post-mode (PEAD) cohort's would-enter longs and runs a web-research
agent (claude_agent_sdk -> WebSearch/WebFetch, subscription auth) to answer the
one thing the quant drift-quality gate structurally cannot see:

    Is the post-print evidence a DURABLE drift setup or a one-day pop that FADES?

The single highest-value web signal is ANALYST-REVISION MOMENTUM after the print
(sell-side price targets chasing the surprise UP = drift confirmation; targets
flat/cut = fade risk) — the literature-backed PEAD confirmer, plus guidance
direction and the narrative behind the reaction. Output is written to
``sentiment_overlay_{date}.md`` next to the cohort.

IMPORTANT boundaries (by design):
  * NEVER mutates cohort_*.json or marks.jsonl. The forward-test dataset stays
    clean so it keeps measuring the systematic signal; this overlay only informs
    a discretionary real-capital decision.
  * Graceful degradation: if the agent SDK / subscription auth is unavailable
    (e.g. a bare cron environment), it writes a runnable PROMPT-PACK fallback
    instead of crashing — the Friday cron must never fail on the advisory step.
  * Idempotent: skips if the overlay already exists (use --force to regenerate).

Usage:
    python3 cohort_sentiment_overlay.py                 # newest *_post cohort
    python3 cohort_sentiment_overlay.py --date 2026-07-05
    python3 cohort_sentiment_overlay.py --cohort ~/shortlong_cohorts/cohort_2026-07-05_post.json
    python3 cohort_sentiment_overlay.py --mode prompt-pack   # skip the agent, emit the pack
    python3 cohort_sentiment_overlay.py --force --model sonnet
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DIR = Path.home() / "shortlong_cohorts"
DEFAULT_MODEL = "sonnet"          # cost-reasonable for a weekly cron; --model to override
AGENT_TIMEOUT_S = 1500            # wall-clock cap; a 3-name sonnet run is ~10min, leave headroom
MAX_TURNS = 40                    # enough for ~5 names x a few searches each


# --------------------------------------------------------------------------- io
def find_cohort(args) -> Path:
    if args.cohort:
        p = Path(args.cohort).expanduser()
        if not p.is_file():
            sys.exit(f"--cohort not found: {p}")
        return p
    cdir = Path(args.dir).expanduser()
    if args.date:
        p = cdir / f"cohort_{args.date}_post.json"
        if not p.is_file():
            sys.exit(f"no post cohort for {args.date}: {p}")
        return p
    posts = sorted(cdir.glob("cohort_*_post.json"))
    if not posts:
        sys.exit(f"no cohort_*_post.json in {cdir}")
    return posts[-1]


def would_enter_longs(cohort: dict) -> list[dict]:
    """The would-enter long records, enriched from the candidates table."""
    longs = set(cohort.get("would_enter", {}).get("longs", []))
    out = []
    for r in cohort.get("candidates", []):
        if r.get("symbol") in longs and r.get("entry_side") == "long":
            out.append(r)
    # preserve the cohort's conviction ordering (candidates are pre-sorted)
    return out


def _fmt_pct(v) -> str:
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else "n/a"


def candidate_line(r: dict) -> str:
    q = f"{r.get('quality')}/4" if isinstance(r.get("quality"), int) else "n/a"
    flags = "; ".join((r.get("quality_bits") or [])[:2] + (r.get("entry_flags") or [])[:2]) or "-"
    return (
        f"- **{r['symbol']}** ({r.get('sector') or 'sector n/a'}): "
        f"reaction {_fmt_pct(r.get('reaction_pct'))}, drift-quality {q}, "
        f"EPS surprise {_fmt_pct(r.get('eps_surprise_pct'))}, "
        f"revenue surprise {_fmt_pct(r.get('revenue_surprise_pct'))}, "
        f"entry ref ${r.get('entry_ref_price')}, "
        f"ranker bias L{r.get('long_score')}/S{r.get('short_score')}. "
        f"Quant flags: {flags}."
    )


# ----------------------------------------------------------------------- prompt
def build_prompt(cands: list[dict], cohort: dict) -> str:
    win = cohort.get("window", {})
    lines = "\n".join(candidate_line(r) for r in cands)
    short_leaners = [r["symbol"] for r in cands
                     if isinstance(r.get("short_score"), int)
                     and isinstance(r.get("long_score"), int)
                     and r["short_score"] > r["long_score"]]
    short_note = ""
    if short_leaners:
        short_note = (
            f"\nNOTE: the fundamental ranker actually leans SHORT on "
            f"{', '.join(short_leaners)} (short bias > long bias) despite the positive "
            f"reaction — flag anything that explains the pop being fragile/mechanical.\n"
        )
    return f"""You are a sell-side-desk analyst adding a web-sentiment overlay to a set of \
post-earnings-drift (PEAD) LONG candidates. Today is {datetime.now().date().isoformat()}. \
Work in English. Your output is written verbatim into an advisory markdown file — return \
clean structured markdown, not pleasantries, and do NOT ask questions.

These names each reported earnings in the window {win.get('from')} -> {win.get('to')}, \
popped on the print, and passed a QUANTITATIVE drift-quality gate (EPS/revenue surprise + \
volume + close-location). They are logged in a forward-test cohort at the entry-reference \
prices below — NO real position is held; this is advisory. Your job is the one thing the \
quant screen cannot see: does the post-print WEB evidence say this is a DURABLE drift setup \
or a one-day pop that will FADE? Known failure mode to catch: a stock pops on a beat, then \
gives it all back over 2-3 weeks (recent program examples: CASY and MU both popped on beats, \
then fell 10-14%).

CANDIDATES (verify each company + report date yourself via search; reaction % is the \
print-day move):
{lines}
{short_note}
FOR EACH NAME research and report (WebSearch/WebFetch; prioritize dates ON/AFTER the print):
a. Report date + what actually DROVE the reaction (guidance raise? backlog/contract? one-off? \
short squeeze?). One tight paragraph.
b. ANALYST-REVISION MOMENTUM SINCE THE PRINT (the key PEAD confirmer) — count + direction of \
rating changes and price-target revisions in the days after the report. Are targets chasing \
the move UP (bullish confirmation) or flat/CUT (fade risk)? Name firms + specific PT moves \
where findable. Do NOT fabricate numbers; if you can't confirm, say so.
c. GUIDANCE quality — did management RAISE forward guidance, reaffirm, or was the beat \
backward-looking with soft/cut guidance? (Beat + raised guide drifts; beat + soft guide fades.)
d. Post-print catalysts/news in the ~1-2 weeks after that would sustain or threaten drift.
e. Red flags — insider selling, dilution/offering after the pop, valuation stretch, one-time \
revenue, litigation, or a narrative that the pop was mechanical (index/short-cover) not \
fundamental.

Weight recency and source quality; a PT change dated after the print outweighs a stale \
pre-print note.

RETURN this exact structure:
1. A per-name block with: a DRIFT-vs-FADE verdict (DURABLE DRIFT / MIXED / LIKELY FADE) + a \
1-5 confidence; the analyst-revision tally (e.g. "4 PT raises, 0 cuts since <date>"); a \
guidance verdict; the single most important supporting fact; and the single biggest risk.
2. A FINAL RANKING table of the candidates by web-confirmed drift strength.
3. An explicit AGREEMENT-vs-QUANT-SCREEN call: does the web agree with the quant (which liked \
all these as longs) or disagree on any name (especially any the ranker leaned short)?
4. A short LOAD-BEARING SOURCES list (the most important URLs).
5. A one-line DATA CAVEATS note for anything you could not fully confirm."""


# ------------------------------------------------------------------------ agent
async def _run_agent(prompt: str, model: str, cwd: Path) -> str:
    """Drive the research agent; return the final assistant markdown. Raises on failure."""
    from claude_agent_sdk import (
        query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage,
    )
    opts = ClaudeAgentOptions(
        allowed_tools=["WebSearch", "WebFetch"],
        permission_mode="bypassPermissions",   # read-only tools only; no file writes by the agent
        model=model,
        max_turns=MAX_TURNS,
        cwd=str(cwd),
        setting_sources=[],                     # don't inherit project CLAUDE.md/skills in cron
    )
    last_text = ""
    result: object = None
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, AssistantMessage):
            text = "".join(b.text for b in msg.content if isinstance(b, TextBlock))
            if text.strip():
                last_text = text            # keep the final assistant turn = the report
        elif isinstance(msg, ResultMessage):
            result = msg
    if not last_text.strip():
        err = getattr(result, "result", None) or "agent returned no text"
        raise RuntimeError(f"empty agent output ({err})")
    return last_text.strip()


def run_agent(prompt: str, model: str, cwd: Path) -> str:
    return asyncio.run(asyncio.wait_for(_run_agent(prompt, model, cwd), timeout=AGENT_TIMEOUT_S))


# ------------------------------------------------------------------------ write
def header(cohort_path: Path, cands: list[dict], model: str, mode: str) -> str:
    syms = ", ".join(r["symbol"] for r in cands) or "(none)"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        f"# Sentiment overlay — {cohort_path.stem}\n\n"
        f"_Generated {ts} · source `{cohort_path.name}` · candidates: {syms} · "
        f"mode: {mode}{' · model ' + model if mode == 'live' else ''}_\n\n"
        f"> **Advisory only.** This overlay does NOT alter the cohort JSON or `marks.jsonl` — "
        f"the forward-test dataset stays clean. It adds the web signal the quant drift-quality "
        f"gate cannot see (analyst-revision momentum, guidance direction, the reaction's "
        f"narrative) to inform a discretionary real-capital decision, not the experiment.\n\n"
        f"---\n\n"
    )


def prompt_pack(prompt: str, cands: list[dict], cohort_path: Path) -> str:
    """Fallback body: the exact research prompt + data, runnable in an interactive session."""
    return (
        "## Prompt-pack fallback\n\n"
        "The research agent could not run headless (SDK/auth unavailable in this environment). "
        "Paste the prompt below into an interactive Claude session — it is self-contained and "
        "carries this cohort's would-enter longs.\n\n"
        "```text\n" + prompt + "\n```\n"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cohort", help="Path to a specific cohort_*.json (default: newest *_post).")
    p.add_argument("--date", help="Cohort date YYYY-MM-DD (resolves cohort_{date}_post.json).")
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="Cohorts dir (default ~/shortlong_cohorts).")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Agent model (default {DEFAULT_MODEL}).")
    p.add_argument("--mode", choices=("auto", "live", "prompt-pack"), default="auto",
                   help="auto = try live agent, fall back to prompt-pack (default); "
                        "live = require the agent (nonzero exit on failure); "
                        "prompt-pack = skip the agent, emit the pack only.")
    p.add_argument("--force", action="store_true", help="Regenerate even if the overlay exists.")
    args = p.parse_args()

    cohort_path = find_cohort(args)
    cohort = json.loads(cohort_path.read_text())
    date = cohort.get("cohort_date") or cohort_path.stem.replace("cohort_", "").replace("_post", "")
    out_path = cohort_path.with_name(f"sentiment_overlay_{date}.md")

    if out_path.is_file() and not args.force:
        print(f"[skip] overlay exists: {out_path} (use --force to regenerate)")
        return

    cands = would_enter_longs(cohort)
    if not cands:
        out_path.write_text(
            header(cohort_path, cands, args.model, "none")
            + "_No would-enter longs in this cohort — nothing to research._\n"
        )
        print(f"[ok] no would-enter longs; wrote stub {out_path}")
        return

    prompt = build_prompt(cands, cohort)
    syms = ", ".join(r["symbol"] for r in cands)
    print(f"[info] {cohort_path.name}: researching {len(cands)} would-enter long(s): {syms}")

    if args.mode == "prompt-pack":
        out_path.write_text(header(cohort_path, cands, args.model, "prompt-pack")
                            + prompt_pack(prompt, cands, cohort_path))
        print(f"[ok] wrote prompt-pack (agent skipped): {out_path}")
        return

    try:
        body = run_agent(prompt, args.model, cohort_path.parent)
        out_path.write_text(header(cohort_path, cands, args.model, "live") + body + "\n")
        print(f"[ok] wrote live overlay: {out_path}")
    except Exception as e:  # noqa: BLE001 — advisory step must degrade, never crash the cron
        msg = f"{type(e).__name__}: {e}"
        print(f"[warn] agent run failed ({msg}); falling back to prompt-pack", file=sys.stderr)
        if args.mode == "live":
            sys.exit(f"live mode required the agent but it failed: {msg}")
        out_path.write_text(
            header(cohort_path, cands, args.model, "prompt-pack (agent failed)")
            + f"> Agent run failed: `{msg}`\n\n"
            + prompt_pack(prompt, cands, cohort_path)
        )
        print(f"[ok] wrote prompt-pack fallback: {out_path}")


if __name__ == "__main__":
    main()
