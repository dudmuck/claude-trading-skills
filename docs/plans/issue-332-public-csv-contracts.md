# Issue #332 slice: public CSV provider contracts (trader-monty)

## Selection and isolation

Issue #332 is the only open P0. Its 2026-10-10 progress audit lists "non-FMP
providers have no contracts yet" as remaining work. No open PR or branch
covers it. The open PRs are #587 (#495 Batch C), #585 (external) and the
dependabot PRs #577 and #578.

Rejected alternatives:

- #495 Batch D would edit the same generator registry and gate lists as the
  open #587, so the two would conflict.
- #496, #297 and #298 each already have merged slices.

New worktree `cts-wt-332-csv`, branch
`codex/issue332-public-csv-contracts-20261024`, based on main `52c9323`.
#332 stays open.

Why these providers first: the four trader-monty public CSVs feed
`market-breadth-analyzer` and `uptrend-analyzer`. Those are two of the three
required skills in the canonical `market-regime-daily` workflow. They need no
API key, so their live canary actually runs. That closes the "canary never
probed" gap for this provider without a repository secret.

Scope decision: this is one PR covering the framework, the four contracts,
the canary, the workflow, and consumer hardening for the two
market-regime-daily skills. The consumer part is kept because "consumer
tests fail when a field is renamed" is a #332 acceptance criterion, and it
is small (two fetcher modules). If code review finds the diff unreviewable,
step 5 is split out.

## Current state (verified on main 52c9323; live CSVs read 2026-10-24)

| Endpoint (proposed key) | URL | Size today | Owners (all readers) |
|---|---|---|---|
| `market-breadth-data` | `tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv` | 380 KB, 2,512 rows | market-breadth-analyzer (`csv_client.py:22`), market-top-detector (`breadth_csv_client.py:20`), breadth-chart-analyst (`fetch_breadth_csv.py:25`) |
| `market-breadth-summary` | `…/market_breadth_summary.csv` (`Metric,Value`) | small | market-breadth-analyzer (`csv_client.py:24`). Reads `Average Peaks (200MA)` and `Average Troughs (8MA < 0.4)` (`market_breadth_analyzer.py:314, 328`; `historical_context_calculator.py:55-56`). `Value` mixes int, float and date strings. |
| `uptrend-ratio-timeseries` | `raw.githubusercontent.com/tradermonty/uptrend-dashboard/main/data/uptrend_ratio_timeseries.csv` | **2.81 MB**, 31,948 rows, ~14 KB/trading day growth | uptrend-analyzer (`data_fetcher.py:20`), sector-analyst (`analyze_sector_rotation.py:38`), breadth-chart-analyst (`fetch_breadth_csv.py:28`), theme-detector (`uptrend_client.py:30`) |
| `uptrend-sector-summary` | `…/data/sector_summary.csv` | small | uptrend-analyzer (`data_fetcher.py:24`), sector-analyst, theme-detector, breadth-chart-analyst |

Live data facts:

- In the timeseries, `ma_10` is empty in 1,431 rows and `slope` in 1,590.
- Every `ratio` value is populated.
- No CSV contains `nan`.
- Booleans are written as `True` / `False`.

Silent-drift behavior today:

- **uptrend-analyzer.** `_parse_timeseries_row` and `_parse_sector_summary_row`
  (`data_fetcher.py:185-214`) read cells with `row.get` and `_safe_float`. A
  renamed column therefore becomes `None` everywhere. Rows are still
  returned, and `main` proceeds (`uptrend_analyzer.py:78-95`).
- **market-breadth-analyzer.** `fetch_detail_csv` (`csv_client.py:43-80`)
  emits one WARN per line, skipping every row. It then prints `OK (0 rows)`,
  and `main` exits 1 with a generic message (`market_breadth_analyzer.py:94-97`).
  The schema cause is buried.
- **Summary metrics.** When a summary metric is missing, the code falls back
  silently.

Framework facts:

- **Validator.** `scripts/provider_contracts.py` is provider-agnostic: it has
  a `provider` field and a globally unique `endpoint`. `validate_rows` emits
  one anomaly **per row** (`:287-316`).
- **Canary.** The canary in `scripts/check_provider_contracts.py` is
  FMP-only:
  - the URL is built at `:110`;
  - the key is required at `:183-186`;
  - the summary titles are hard-coded at `:218-221`, `:269` and `:275`;
  - the default report path is `fmp_canary_<date>.json` (`:155-156`).
- **Existing tests that pin the FMP set and fetch signature:**
  - `test_provider_contracts.py:56-66` holds the exact contract set.
  - The `len(CONTRACTS)` budget assertions are at `:673, :700, :742, :939`.
  - The direct `run_canary` callers use `(path, query)` at `:977, :986, :1173`.
  - The stubbed `_build_requests_fetch` is at `:650, :688, :707, :735, :926`.
  - `test_provider_contracts_summary.py:118` asserts the FMP title.
- **Workflow tests.** `scripts/tests/test_fmp_canary_workflow.py` lints the
  FMP canary workflow. `scripts/tests/test_ci_supply_chain_wiring.py:16-20`
  enforces the locked environment per workflow.
- **Replay.** Workflow replay never calls these fetchers. The skill `main`
  tests mock `fetch_detail_csv` / `fetch_timeseries` at module level.

## Implementation plan

1. **Contract schema extension (additive; FMP contracts unchanged).**
   - `format`: `"json"` (default) or `"csv"`. `validate_contract_file` rejects
     any other value.
   - `url`: required for csv, forbidden for json. Rules:
     - the scheme must be `https`;
     - the host must be in the allowlist `{tradermonty.github.io, raw.githubusercontent.com}`;
     - there is no query string, and `query` must be empty;
     - `path` equals the URL path for display.
   - `max_bytes`: optional for csv, a positive int, default 2 MiB. The
     timeseries sets 16 MiB, which leaves room for years of growth.
   - `required_values`: `{column: [values…]}`. Each value must appear in at
     least one row. If not, the result is the new fatal
     `missing_required_value:<column>=<value>`.
   - `parse_csv_rows(text) -> (rows, parse_anomalies)` (stdlib `csv`). On
     an `extra_cells` row the restkey cells are dropped, so a row keeps only
     the header keys and no `None` key ever reaches `validate_rows` or the
     report:
     - strips a UTF-8 BOM and reads the header;
     - an empty cell becomes `None`;
     - `true` / `false` in any case becomes `bool`, the same as the breadth
       consumer;
     - an integer literal becomes `int`;
     - a decimal or exponent literal becomes `float`;
     - anything else stays `str`, including dates, `nan` and `inf`.

     `nan` / `inf` therefore give `wrong_type:…:str` for numeric columns.
     This is intentional and documented: the breadth consumer rejects them,
     and live data has none.

     Short rows are handled: DictReader's restval `None` maps to `None`. An
     extra cell, which DictReader puts in its restkey list, is reported as
     the fatal `extra_cells`.

     A header-only CSV gives `[]`, which yields `empty_response` when
     `min_rows >= 1`.

     CSV fixtures are stored as already-coerced JSON rows. Fixture and live
     text go through the same coercion.
   - **Type declarations follow what consumers accept.**
     - Every float-parsed column declares `["float","int"]`, because
       `float("1")` is valid.
     - `["int"]` applies only where the consumer uses `int()` directly:
       `Breadth_200MA_Trend`.
     - `count` and `total` are `["int","float"]`, because `_safe_int` is
       `int(float(v))`.
     - Bool columns are `["bool"]`, which is deliberately stricter than any one
       consumer. market-breadth-analyzer accepts `1`/`0`/`yes`/`no`, while
       market-top-detector reads every other value as False, so any other
       spelling is fatal drift (decided in code review round 2).
     - Summary `Value` is `["int","float","str"]`.
   - **Anomaly dedupe.** `RowValidation` gains `summarized()`, which returns
     the unique `(code, severity)` pairs with a `count`, in first-seen
     order. `validate_rows` keeps its per-row output, so existing FMP
     callers and tests are unchanged. The canary uses only the summarized
     form.
2. **Four contracts** under `config/provider-contracts/trader-monty/*.v1.json`.
   - Each has `provider: "trader-monty"`, matching the provenance provider
     string at `market_breadth_analyzer.py:102` and `uptrend_analyzer.py:99`.
   - Each has the full owner lists from the table above.
   - Each has a sanitized real-row fixture of 5-10 rows. The timeseries
     fixture includes rows with empty `ma_10` / `slope`.
   - `non_empty.min_rows` is set.
   - `required_fields` covers exactly the columns the owners read:
     - breadth data: the ten `DETAIL_COLUMNS`;
     - timeseries: `worksheet`, `date`, `count`, `total`, `ratio` (with
       `reject_all_null`), `ma_10` (nullable) and `slope` (nullable). `trend`
       is nullable in case it is empty.
     - sector summary: `Sector`, `Ratio`, `10MA`, `Trend`, `Slope` and
       `Status`;
     - breadth summary: `Metric` and `Value`, plus `required_values` for the
       two metrics.
   - Unread columns, such as the `Breadth_50_*` family, go in
     `optional_fields`.
   - breadth-chart-analyst tolerates alternate column names at
     `fetch_breadth_csv.py:176-184`: `SP500_Price`, `Breadth_200MA`,
     `Breadth_8MA`, and `Trend` for `Breadth_200MA_Trend`. They are recorded
     as `legacy_aliases` of the canonical names. The docs describe them as
     *consumer-tolerated alternates*, not provider history. A provider rename
     to one of them is fatal (`canonical_absent_legacy_present`), which is
     correct, because market-breadth-analyzer and market-top-detector would
     break.
3. **Provider-aware canary (FMP path unchanged by default).**
   - `canary --provider {fmp,trader-monty,all}`, default `fmp`. Contracts
     are filtered by provider before the budget is computed. `--max-calls`
     defaults to the selected count.
   - `FMP_API_KEY` is required only when FMP contracts are selected.
   - `_build_requests_fetch(api_key) -> fetch(path, query)` stays exactly
     as it is. `cmd_canary` still calls it, so the existing monkeypatches at
     `:650, :688, :707, :735, :926` keep working.
   - `run_canary(contracts, fetch)` dispatches on the type of `fetch`:
     - **A dict.** `fetch` is a `dict[str, Callable[[Contract], FetchResult]]`
       keyed by provider.
     - **A bare callable.** It is wrapped as the legacy FMP fetch, called as
       `fetch(c.endpoint_path, dict(c.query))`, and `TypeError` is raised if
       any selected contract is not FMP/json. The direct callers at
       `:977, :986, :1173` keep working, and `:977`'s parametrization is
       restricted to FMP contracts.
   - `FetchResult(status, rows, extra_anomalies)` is a small dataclass. The
     legacy FMP adapter turns its `(status, data)` tuple into
     `FetchResult(status, data, [])`, so FMP outcomes do not change. The
     current test at `:974-982` still pins exactly `[http_status:-1]`,
     which now carries `count: 1`.
   - `run_canary` merges `extra_anomalies`. For **CSV** contracts it skips
     `validate_rows` whenever `rows is None`, which happens on a transport
     error, an oversized body, a decode failure or a non-200/3xx response,
     so no spurious `empty_response` appears. The non-200 and 3xx tests
     assert exactly `[http_status:<code>]`. The FMP path keeps calling
     `validate_rows` exactly as it does today. The `http_status:*` entry
     carries `count: 1`.
   - New `_build_public_csv_fetch()`:
     - one GET to `contract.url` with no credentials, `allow_redirects=False`,
       a 30 s timeout and `stream=True`;
     - it reads raw bytes up to `max_bytes + 1`, and the cap counts
       decompressed bytes. It decodes the capped buffer as `utf-8-sig`, never
       `response.text`. An undecodable buffer gives the fatal `decode_error`, and a `csv.Error` gives the fatal `parse_error`;
     - an oversized body gives `FetchResult(status, None, [body_too_large:<max_bytes>])`;
     - a 3xx or other non-200 response gives `FetchResult(status, None, [])`,
       which leaves `http_status:<code>`;
     - a transport error gives `FetchResult(-1, None, [transport_error])`.
       For CSV only, this replaces the FMP-style `http_status:-1`. Its message
       is redacted and printed to stderr only;
     - otherwise it returns `FetchResult(200, rows, parse_anomalies)`.
   - `parse_csv_rows(text)` returns `(rows, parse_anomalies)`. An extra cell
     adds one `extra_cells` anomaly per affected row; these are summarized
     later. The step-1 coercion description is otherwise unchanged.
   - **Report changes:**
     - There is an additive top-level `"provider"` key.
     - Per-contract `anomalies` and `deprecations` are the summarized
       `{code, severity, count}` entries. `count` is additive, and FMP
       reports also gain it.
     - The default report path is `reports/<provider>_canary_<date>.json`.
       For FMP this is still `fmp_canary_<date>.json`.
   - **`summarize`** derives its titles from `report.get("provider", "fmp")`.
     Absent or `fmp` keeps the exact current strings, so
     `test_provider_contracts_summary.py:118` still holds. trader-monty uses
     "Public CSV contract anomaly/deprecation" and "Public CSV canary report
     missing". `--provider` on `summarize` chooses the missing-report title.
     Summary cells render `code ×count` when count > 1.
4. **Workflow** `.github/workflows/public-csv-contract-canary.yml`:
   - **Triggers and access:** weekly on Monday at 12:30 UTC plus
     `workflow_dispatch`, `permissions: contents: read`, the same repository
     guard, and no `secrets.` references.
   - **Actions:** SHA-pinned `uses` and a locked `uv sync`, mirroring the FMP
     workflow.
   - **Steps:**
     1. Run `canary --provider trader-monty --report reports/public-csv-canary-report.json`.
     2. Run `summarize --provider trader-monty` under `if: always()`.
     3. Upload the report as an artifact kept for 30 days.
   - **Report-only:** `continue-on-error: true`, under the same promotion
     policy as the FMP canary. The docs state that the annotations and the
     step summary are the only drift signal, and that the run stays green on
     drift until promotion.
   - **Tests:** a new `scripts/tests/test_public_csv_canary_workflow.py`,
     modeled on `test_fmp_canary_workflow.py`. The workflow is also added to
     `test_ci_supply_chain_wiring.py:16-20`.
   - `fmp-contract-canary.yml` is not modified.
5. **Consumer hardening for the two market-regime-daily skills.**
   - **market-breadth-analyzer `csv_client.py`.**
     - `fetch_detail_csv` checks the header against `DETAIL_COLUMNS` before
       parsing any row. If columns are missing, it prints one
       `ERROR: market_breadth_data.csv schema drift: missing columns […]`
       and returns `[]`. The existing `main` exit 1 is kept, and the
       per-line WARN flood goes away.
     - `fetch_summary_csv` warns once for each missing required metric.
       Otherwise behavior is unchanged, because the percentile fallback
       already exists.
   - **uptrend-analyzer `data_fetcher.py`.**
     - `fetch_timeseries` and `fetch_sector_summary` check the header against
       their required columns. If columns are missing, they print one
       `ERROR: <file> schema drift: missing columns […]` and return `[]`.
     - `fetch_timeseries` also flags drift when every `worksheet == "all"`
       row has an empty ratio. A NaN result from `_safe_float` counts as
       empty. Zero `all` rows also counts as drift, because `main` needs
       `latest_all`. Both cases are tested.
     - On drift, the fetcher caches `[]` so the ERROR prints once and the
       file is not downloaded again. The cache stays non-`None`.
     - Existing behavior is kept: an empty timeseries still exits 1
       (`uptrend_analyzer.py:80-84`), and an empty sector summary still
       falls back to summaries derived from the timeseries.
   - **Other owners.** market-top-detector, breadth-chart-analyst,
     sector-analyst and theme-detector are contract owners only. Their
     parser hardening is listed in the doc's "Out of scope" section with
     file:line read sites as a follow-up. Their behavior does not change.
6. **Docs and text.**
   - `docs/dev/provider-contracts.md`:
     - drop "(FMP)" from the title;
     - add the trader-monty layout;
     - document the new keys, coercion, `max_bytes`, `extra_cells`,
       `missing_required_value`, `body_too_large`, `transport_error`, the
       dedupe and `count`;
     - document the canary `--provider` flag and the new workflow;
     - add the four ownership rows;
     - replace "Non-FMP providers" in "Out of scope" (`:537`) with the
       remaining providers (yfinance, CoinGecko, Binance, Alpaca,
       FXMacroData) and the four deferred owner hardenings;
     - update the CLI reference.
   - Update the `ci.yml:268-271` comment and the
     `docs/dev/maintenance-runbook.md:79` row.
   - `skills-index.yaml` is not changed.

## Tests (TDD: failing tests first)

- **Framework.** Tests in `scripts/tests/test_provider_contracts.py`.
  - `parse_csv_rows` cases: empty cells, any-case bools, int, float,
    exponent, `nan`/`inf` → str, str dates, header-only input, a quoted
    comma, a BOM header, a short row, and an extra cell → `extra_cells`.
  - `format`/`url`/`query`/`max_bytes` validation, covering each invalid
    case.
  - `required_values` pass and fail.
  - `summarized()` dedupe: a 30k-row body with one renamed column gives one
    entry with a count of 30,000.
  - The four trader-monty fixtures pass `check`.
  - `test_expected_contracts_are_present` becomes per-provider exact sets:
    the 9 FMP contracts and the 4 trader-monty contracts.
  - The `len(CONTRACTS)` budget assertions use the FMP-filtered count.
  - Exact-dict assertions that gain `count`: `:932-938` (the profile report
    entry), `:981` (`http_status:-1`) and `:990` (`empty_response`).
  - `test_expected_legacy_alias_holders` (`:102-103`) adds
    `market-breadth-data`. The parametrized rename test (`:106-122`) then
    covers the new aliases automatically.
  - A stubbed `_build_requests_fetch` still drives a default `fmp` run.
  - A bare callable combined with a non-FMP contract raises `TypeError`.
  - An undecodable body → `decode_error`. Zero `all` rows → drift.
  - Duplicate endpoint across providers is still rejected.
- **Canary.**
  - Provider filtering and budget.
  - `--provider trader-monty` with no `FMP_API_KEY` succeeds against a fake
    CSV fetch.
  - The default `fmp` provider still requires the key.
  - The CSV fake is called with the URL, no credentials and no redirects.
  - These inputs each map to their code:
    - non-200 → `http_status`;
    - 3xx → `http_status`;
    - transport error → `transport_error`;
    - a body one byte under `max_bytes` is OK, and one byte over is
      `body_too_large`;
    - renamed column → `missing_required_field`.
  - The report carries `provider` and `count`.
  - The legacy `(path, query)` direct callers still work.
- **Summary.** FMP titles are unchanged with or without `provider`. A
  trader-monty report uses the public titles. A missing report uses the
  provider-specific title.
- **Consumer contract tests in `scripts/tests/`.** This follows the
  FMP-consumer convention in `test_provider_contracts.py`, where client
  modules are loaded by path, so skill suites never read `config/`.
  - Each test builds CSV text from the contract fixture and checks that the
    consumer parses it.
  - Renaming each required column must produce exactly one schema-drift
    ERROR, `[]` and no WARN flood.
- **Skill-suite unit tests** (inline CSV) run in each skill's own suite, for
  coverage:
  - a header with missing columns produces the error and `[]`;
  - a missing summary metric produces a warning;
  - all-empty `ratio` in the `all` rows produces the error;
  - the cached drift result prints once and fetches once;
  - main-level exit 1 for drifted detail and timeseries data.
  - HTTP goes through the existing fakes or mocks. No live calls.
- **Workflow.** `test_public_csv_canary_workflow.py` and the
  supply-chain-wiring entry.

## Verification

- Contract check: `python3 scripts/check_provider_contracts.py check`.
- Unit tests: the provider-contract, summary, workflow and supply-chain tests.
- Skill suites: market-breadth-analyzer and uptrend-analyzer, each run alone,
  with CI-equivalent coverage at or above the floor and before/after deltas
  reported.
- Replay: the market-regime and provenance replay tests. No golden change is
  expected; any change is a regression.
- Lint: ruff and codespell.
- Packaging: rebuild both `.skill` archives and pass `package_skills.py --check`
  for the two skills.
- Docs: `generate_skill_docs.py --check`.
- One manual live run, `canary --provider trader-monty --report /private/tmp/…`,
  against the keyless, read-only public CSVs. The result is recorded in the PR.
- No secrets, trading actions or merges.

## Review log

Plan round 1: not approved. It found 1 blocker, 4 major and 8 minor issues;
all were accepted:
- The 2 MB cap was smaller than the 2.81 MB timeseries; it is now a
  per-contract `max_bytes` with a named code.
- Anomalies are now deduped with a count for the canary and summary.
- The FMP fetch factory is kept, and the existing tests that pin the
  contract set and budget are listed.
- `summarize` titles and the report path are now provider-aware.
- Types now follow what the consumers accept, with case-insensitive bools,
  mixed summary `Value`, and short/extra-cell handling.
- The owner list is complete, and the breadth-chart-analyst aliases are
  recorded.
- Workflow lint and supply-chain wiring are added.
- Redirects are disabled, and format/url/query consistency is validated.
- The uptrend drift check is scoped to the `all` rows, treats NaN as empty
  and runs once.
- Consumer contract tests now live in `scripts/tests`.
- Stale "FMP-only" text is updated.
- The workflow being green on drift is documented.
- The scope decision is recorded.

Plan round 2: not approved (1 major, 5 minor); all accepted.
- **FetchResult.** `FetchResult(status, rows, extra_anomalies)` now carries
  `body_too_large`, `transport_error`, `decode_error`, `parse_error` and `extra_cells`.
  `parse_csv_rows` returns its anomalies, and validation is skipped after a
  fetch failure. FMP `http_status:-1` behavior is pinned unchanged.
- **Tests.** The exact-dict tests that change because of `count` are listed,
  and `test_expected_legacy_alias_holders` is updated.
- **Alias list.** The `Trend` alias is added. The aliases are worded as
  consumer-tolerated alternates.
- **Dispatch.** `run_canary` dispatch is by dict or bare callable, not by
  arity. A test covers a stubbed factory.
- **Edge cases.** CSV bytes are decoded as `utf-8-sig`. Zero `all` rows count
  as drift. Summary cells show `×count`.

Plan round 3 approved the plan, with 4 minor implementation notes, all applied:
- Validation is skipped for CSV whenever there are no rows, so a non-200
  response yields exactly `[http_status:<code>]`.
- The wording of the FMP pinned-test was corrected.
- The step-1 signature for `parse_csv_rows` now matches.
- Rows with `extra_cells` keep only the header keys.

This is the final plan.

## Implementation reviews

Code round 1: approved, with 7 minor findings, all fixed:
- header whitespace is normalized once;
- a canary `csv.Error` now reports `parse_error`;
- the uptrend short-row crash is fixed;
- `count`/`total` accept `["int","float"]`;
- the anomaly docs are updated;
- `--provider all` gets neutral titles;
- BOMs are written as escapes, and the dead block is removed;
- in addition, sector-summary `10MA`/`Slope` gained `reject_all_null`.

Code round 2: 1 major and 3 minor findings, all fixed:
- (major) the bool columns had been loosened to `["bool","int","str"]`, which
  let any string pass. They are back to `["bool"]` with the multi-owner
  rationale, and a test now checks that `Y`/`N`/`T`/`1`/`yes` are fatal;
- `_missing_columns` no longer strips a second time;
- both consumers now report an unparsable CSV as drift via `_read_csv`
  instead of crashing, and uptrend caches that result;
- the plan's bool wording is aligned with the contract.
