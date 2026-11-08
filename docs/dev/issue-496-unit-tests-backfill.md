# Issue #496 step 1 — `unit_tests` verification backfill (assessed 2026-10-26)

Assessed commit convention: `assessed_commit` pins `52c93232...`, the last revision common
to origin/main and this PR branch (an ancestor of the PR head, reachable after squash-merge;
a commit cannot contain its own final SHA). The recorded evidence command and the cited
skill-local test files are byte-identical on the PR head revision.
CI is green on origin/main at `52c93232` for all test-matrix
rows covered by this assessment (GitHub Actions run 40103302803; the only failing CI job on that
run is `Supply chain`, a pre-existing dependency-audit failure that also fails on #587, unrelated
to skill tests).

Evidence was collected by `scripts/backfill_unit_tests_evidence.py`
(report `reports/unit_tests_evidence.json` at assessment time; regenerate to reproduce).
Method: only skill-local tests under `skills/<id>/scripts/tests` that assert the skill's own
produced output keys / schema file can source the `output-schema conformance` and
`error/fail-closed` signals; repo-level suites (scripts/tests/*) count for coverage mapping
only and are never cited as schema evidence.
`passed` is claimed for exactly the skills whose mapped test set demonstrates, per skill
(individually recorded rationale in the baseline override): the skill's own produced-output
key/schema assertions, a real error-path/fail-closed test, and happy-path/boundary coverage
whose per-skill evidence is individually recorded in each override rationale. Watch-outs:
- the collector's raw output never stamps reviewer confirmation: the
`schema_conformance_confirmed_by_reviewer` flag is False by default and the per-skill deep
review that confirms each schema claim is recorded in the override rationale instead.
- Recorded commands preserve the actual install/run status (`install && run`), without
an unconditional `exit 0`. The collector stops before running a row if installation fails.
A `passed` proposal requires successful installation and execution for the skill row and,
when repo-level tests are mapped, the repo-scripts row. Missing exit evidence yields a gap.

Outcome: **12 skills marked `passed`** (index + same-commit baseline override with
per-skill rationale), **47 skills remain `not_verified` with a documented gap**, and 3 skills
with no executable helper scripts are already `not_applicable`.

This table documents the per-skill state required by issue #496 acceptance criterion #1.
| Skill | Proposed value | Gap reasons / notes |
|---|---|---|
| backtest-expert | passed | - |
| breadth-chart-analyst | gap | Local install/run could not execute: `uv pip install` of opencv/pillow refused into the ambient Homebrew interpreter. CI `Test (breadth-chart-analyst)` green at 52c93232. Kept `not_verified` (environment drift, not ambient flake). |
| breakout-trade-planner | passed | - |
| canslim-screener | gap | no assertion-shaped output-schema conformance test among mapped tests |
| contrarian-setup-gate | gap | no assertion-shaped output-schema conformance test among mapped tests |
| cot-contrarian-detector | gap | no assertion-shaped output-schema conformance test among mapped tests |
| data-quality-checker | gap | no assertion-shaped output-schema conformance test among mapped tests |
| dividend-growth-pullback-screener | gap | no assertion-shaped output-schema conformance test among mapped tests |
| downtrend-duration-analyzer | gap | no assertion-shaped output-schema conformance test among mapped tests |
| drawdown-circuit-breaker | gap | no assertion-shaped output-schema conformance test among mapped tests |
| dual-axis-skill-reviewer | gap | no assertion-shaped output-schema conformance test among mapped tests |
| earnings-calendar | gap | no assertion-shaped output-schema conformance test among mapped tests |
| earnings-trade-analyzer | passed | - |
| economic-calendar-fetcher | gap | no assertion-shaped output-schema conformance test among mapped tests |
| edge-candidate-agent | passed | - |
| edge-concept-synthesizer | gap | no assertion-shaped error-path/fail-closed test among mapped tests; no assertion-shaped output-schema conformance test among mapped tests |
| edge-hint-extractor | gap | no assertion-shaped output-schema conformance test among mapped tests |
| edge-pipeline-orchestrator | gap | no assertion-shaped output-schema conformance test among mapped tests |
| edge-signal-aggregator | gap | no assertion-shaped output-schema conformance test among mapped tests |
| edge-strategy-designer | gap | no assertion-shaped output-schema conformance test among mapped tests |
| edge-strategy-reviewer | gap | no assertion-shaped error-path/fail-closed test among mapped tests; no assertion-shaped output-schema conformance test among mapped tests |
| exposure-coach | gap | no assertion-shaped output-schema conformance test among mapped tests |
| finviz-screener | gap | no assertion-shaped output-schema conformance test among mapped tests |
| ftd-detector | gap | no assertion-shaped output-schema conformance test among mapped tests |
| futures-position-sizer | passed | - |
| ibd-distribution-day-monitor | gap | no assertion-shaped output-schema conformance test among mapped tests |
| institutional-flow-tracker | gap | Track/place-holder script track_institution_portfolio.py is unmatched (no test module references it; it is an unimplemented placeholder). Kept `not_verified`. |
| kanchi-dividend-review-monitor | gap | no assertion-shaped output-schema conformance test among mapped tests |
| kanchi-dividend-sop | gap | 1 unmatched script (thresholds.py) is transitively exercised via tested importers; that alone is judged insufficient for `passed`, and no skill-local output-schema assertion exists in mapped tests. Kept `not_verified`. |
| kanchi-dividend-us-tax-accounting | gap | no assertion-shaped error-path/fail-closed test among mapped tests; no assertion-shaped output-schema conformance test among mapped tests |
| macro-regime-detector | passed | - |
| market-breadth-analyzer | passed | - |
| market-environment-analysis | gap | no assertion-shaped output-schema conformance test among mapped tests |
| market-news-analyst | not_applicable (out of scope) | no executable helper scripts (out of scope for #496 step 1) |
| market-top-detector | gap | no assertion-shaped output-schema conformance test among mapped tests |
| news-reaction-failure-analyzer | passed | - |
| options-strategy-advisor | gap | Local install/run could not execute (same uv/pillow ambient-interpreter cause). CI row green at 52c93232. Kept `not_verified` (environment drift). |
| pair-trade-screener | gap | Local install/run could not execute (same uv/pandas ambient cause). CI row green at 52c93232. Kept `not_verified` (environment drift). |
| parabolic-short-trade-planner | gap | 3 executable script(s) without a mapped test module |
| pead-screener | passed | - |
| portfolio-manager | gap | Local row exit 1 in the assessment environment (message-text drift vs the locked CI env). The CI `Test (portfolio-manager)` row is green at assessed commit 52c93232 (GitHub Actions run 40103302803). Kept `not_verified` because the local recorded run could not establish exit-0 evidence. |
| position-sizer | passed | - |
| pre-trade-discipline-gate | gap | no assertion-shaped output-schema conformance test among mapped tests |
| scenario-analyzer | not_applicable (out of scope) | no executable helper scripts (out of scope for #496 step 1) |
| sector-analyst | gap | no assertion-shaped output-schema conformance test among mapped tests |
| signal-postmortem | gap | no assertion-shaped output-schema conformance test among mapped tests |
| skill-designer | gap | no assertion-shaped output-schema conformance test among mapped tests |
| skill-idea-miner | gap | no assertion-shaped output-schema conformance test among mapped tests |
| skill-integration-tester | gap | no assertion-shaped error-path/fail-closed test among mapped tests |
| stanley-druckenmiller-investment | gap | no assertion-shaped output-schema conformance test among mapped tests |
| strategy-pivot-designer | gap | no assertion-shaped output-schema conformance test among mapped tests |
| technical-analyst | passed | - |
| theme-detector | gap | Local row exit 1 (yfinance provider-fallback tests against ambient package versions). CI row green at 52c93232. Kept `not_verified`. (Corrected: the earlier explanation blaming an ambient interpreter flake was wrong; cause was environment drift.) |
| trade-hypothesis-ideator | gap | run_hypothesis_ideator.py is unmatched; its only coverage is transitive via scripts/workflow_replay.py, judged insufficient for `passed`. Kept `not_verified`. |
| trader-memory-core | passed | - |
| trading-skills-navigator | gap | no assertion-shaped output-schema conformance test among mapped tests |
| uptrend-analyzer | gap | no assertion-shaped output-schema conformance test among mapped tests |
| us-market-bubble-detector | gap | no assertion-shaped output-schema conformance test among mapped tests |
| us-stock-analysis | not_applicable (out of scope) | no executable helper scripts (out of scope for #496 step 1) |
| value-dividend-screener | gap | no assertion-shaped output-schema conformance test among mapped tests |
| vcp-screener | gap | no assertion-shaped output-schema conformance test among mapped tests |
| weekly-performance-digest | gap | no assertion-shaped output-schema conformance test among mapped tests |
