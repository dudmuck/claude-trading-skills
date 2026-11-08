# Issue #495 Batch C: stockbee-family FMP clients

## Selection and isolation

Select P1 #495's proposed Batch C: the five stockbee skills
`stockbee-20pct-study`, `stockbee-episodic-pivot-analyzer`,
`stockbee-exhaustion-hammer-screener`, `stockbee-momentum-burst-screener` and
`stockbee-setup-fluency-trainer`. Batch A (#532) and Batch B (#573) are merged.
On 2026-10-24 no open PR, remote branch or registered worktree covers Batch C
(open PRs: #585 external, #577/#578 dependabot; live worktrees cover #512/#514,
both merged). New worktree `cts-wt-495-batch-c`, branch
`codex/issue495-stockbee-batch-c-20261024`, based on main `52c9323`.
Batch D and the issue's repo-wide acceptance criteria stay out of scope; #495
stays open.

Scope decision: all five ship in one PR. They share one new extension and the
adapters are small (70-180 lines each). The per-skill test rewrites are
independent, so they can proceed in parallel. If review shows the diff is
unreviewable, split along the C1/C2 line: momentum and hammer first, then
20pct, EP and fluency.

## Current state (verified file:line on main 52c9323)

Each script carries its own `requests.Session` client, fixed 0.3 s sleep and
`/stable` → `api/v3` fallback:

| Skill | Client | Endpoints used | Budget / 429 / auth |
|---|---|---|---|
| momentum-burst | `screen_momentum_burst.py:81-232` | company-screener (→v3 stock-screener), EOD (→v3 historical-price-full) | raise local `ApiCallBudgetExceeded` (default 500); 429 sets `rate_limit_reached`, no wait; header auth |
| exhaustion-hammer | `screen_exhaustion_hammer.py:117-301` | same + **v3-only** `quote/{symbol}` (`:270`) | same (default 700); header **and** query auth |
| 20pct-study | `run_20pct_study.py:61-179` | company-screener (→v3), EOD (→v3), pad `days*2+20` | raise (default 500); **query-param auth only** (`:86`); fetch loop swallows non-budget exceptions (`:343-350`) |
| episodic-pivot | `analyze_ep.py:150-212` | EOD (→v3), profile (→v3; `get_profile` unused by `main`) | soft: returns `None` over budget (default 200); counter `api_calls` incremented *before* each request; errors silent |
| setup-fluency | `build_model_book.py:61-131` | EOD (→v3) | raise (default 200); **no exception handling**, so a `RequestException` aborts `command_update` before `save_model_book` (`:900, :913`) |

All five import `requests` optionally (`requests = None`) so their offline
paths (`--prices-json`, events JSON, model-book files) run without it. Tests
cover the "requests missing" error (`test_analyze_ep_coverage.py:122`,
`test_build_model_book_coverage.py:75`, `test_screen_momentum_burst_coverage.py:92`).
The generated core instead calls `sys.exit(1)` at import when `requests` is
missing (`core_template.py.tmpl:23-27`).

## Implementation plan

1. **Generator extension (`scripts/fmp_client/extensions/stockbee_stable.py.tmpl`).**
   Register five `SkillConfig` rows: family B, `budget=True` (so they stay
   out of `NO_BUDGET_FAMILY_B`), `has_compat=False`, header auth, fixed 30 s
   timeout and a `STABLE_URL` class constant. The extension adds stable-only
   primitives on top of the shared `_rate_limited_get`. That method already
   provides the rate limit, the single 60 s 429 retry, the malformed-JSON
   retry, redaction and budget accounting.
   - `fetch_screener_rows(params, quiet=False) -> list | None` → `/stable/company-screener`
   - `fetch_eod_rows(symbol, days, pad_days=10, quiet=False) -> list | None` →
     `/stable/historical-price-eod/full` with `from = _et_today() - (days*2 + pad_days)`
     and `to = _et_today()`. It returns the provider list unchanged, and
     callers keep their own normalizers.
   - `fetch_quote_row(symbol) -> dict | None` → `/stable/quote?symbol=`
   Names use `fetch_` so the family-B guard `"def get_quote" not in out`
   (`test_generate_fmp_client.py:95-101`) keeps passing. **No circuit
   breaker:** these primitives never call `_record_endpoint_failure` or
   consult `_disabled_endpoints`. Empty rows for a delisted or new ticker are
   not endpoint failures. The core `get_historical_prices` and
   `_request_with_fallback` are never called by the adapters. EP's unused
   `get_profile` is deleted, not ported. The core template and redaction
   fragment stay untouched, so the 17 existing clients are unchanged.
2. **Thin adapters in each script (composition, explicit sibling load).**
   - **Public surface:** keep the module-level `FMPClient` class name,
     constructor signature, defaults, public methods, return shapes and stats
     dict keys. Each adapter keeps its own API-key check and error message
     before it builds the shared client.
   - **Loading the shared client:** `__init__` keeps the existing
     `requests is None` check. After that check, the module loads the
     sibling generated client with
     `importlib.util.spec_from_file_location(..., Path(__file__).parent / "fmp_client.py")`
     The module is registered in `sys.modules` under a per-skill name, for
     example `_stockbee_momentum_burst_screener_fmp_client`, before
     `exec_module` runs, and the module object is cached once. Python's
     `sys.modules["fmp_client"]` lookup is not used, so a bulk pytest run or
     20pct's `spec_from_file_location` test loader can never pick up another
     skill's client. Tests reach the shared module through the adapter's
     handle (`_load_shared_fmp()`), never with `import fmp_client`. A plain
     import would create a second module, and its `ApiCallBudgetExceeded`
     would be a different class that the adapter does not translate.
   - **Why composition, not Batch B's subclassing:** a subclass would force
     the import at module load. That breaks offline mode and the existing
     "requests missing" errors.
   - **Attribute surface:** the adapter exposes `session` as a property with
     a setter that delegates to the shared client. It does the same for
     `api_calls_made` (and EP's `api_calls`), `rate_limit_reached`,
     `max_api_calls` and `last_call_time`. Tests
     that assign these keep working. `cache_entries` and every cache stay on
     the adapter, because the shared cache is unused.
   - **Exceptions:** every public method translates the shared
     `ApiCallBudgetExceeded` into the script's existing local class. EP keeps
     its soft `None` on budget exhaustion. Any non-budget exception from the
     shared layer, for example `_et_today`'s tzdata `RuntimeError`,
     propagates; the adapter never swallows it. In 20pct, the caller
     `fetch_prices_from_fmp` (`run_20pct_study.py:349`) has an
     `except Exception: continue`. It is narrowed so that `RuntimeError`
     propagates, and a test covers it.
   - **The one public method removed:** EP's `get_profile` is the single
     exception to "keep public methods". `main` never calls it. It is
     deleted along with its tests (`test_analyze_ep_coverage.py:159-168`).
   - **What is deleted:** `_stable_then_v3`, `BASE_URL`, `V3_URL`,
     `HIST_URLS`, `PROFILE_URLS`, the private `_request`/`_get` HTTP loops,
     and every v3 fallback.
   - **What stays unchanged:** each skill's normalizers
     (`normalize_fmp_historical_response`, `normalize_price_bars`,
     `normalize_bars`), the universe filters and sorting, the quote-bar
     construction, and every non-client function.
   - **Hammer quote:** moves from v3 `quote/{symbol}` to `/stable/quote`. Its
     default bar date switches from `date.today()` to the same ET date used
     for history windows, so the two paths agree. The test at
     `test_screen_exhaustion_hammer_coverage.py:203` changes to patch a fixed
     aware instant into the ET helper.
3. **Setup-fluency fail-closed preservation.** Before this change, a transport
   failure aborted `update` without saving. After it, failures are soft, so
   the plan adds `rate_limit_reached` and a `failed_requests` count to the
   FMP-path `api_stats`.
   - **What counts as a failure:** a request fails when the shared fetch
     returns `None`. That covers a transport error, an HTTP error, and the
     rate-limit short-circuit. A `[]` response is not a failure, because it
     means the ticker genuinely has no rows.
   - **All symbols failed:** `command_update` prints
     `ERROR: FMP price fetch failed for all N symbols; model book not updated`
     to stderr and returns exit code 1. It does **not** save the model book
     and writes no update report.
   - **Some symbols failed:** the model book is saved, and the report carries
     the count.

   This keeps a 429 or an outage from silently stamping every record
   `missing_prices`. Budget exhaustion still raises uncaught, as before.
   `--prices-json` runs (the replay path) are unaffected.
4. **Intentional transport changes (documented in
   `docs/dev/fmp-client-batch-c.md`):**
   - Stable-only: a 402/403/empty stable response no longer tries v3.
   - The first 429 waits 60 s and retries once. The second sets
     `rate_limit_reached`. Before, momentum and hammer stopped immediately,
     and 20pct, fluency and EP did not track 429 at all.
   - A malformed 200 JSON body is retried once, then fails soft.
   - History windows use the America/New_York date.
   - 20pct switches from query-param auth to header auth. Hammer drops its
     duplicate query-param key.
   - EP's counter now counts completed responses plus retries. It no longer
     counts requests that raised a transport exception.
   - Fluency no longer propagates a raw `RequestException`; see step 3.
   - Redacted stderr diagnostics replace the old unredacted
     `response.text[:200]`.
5. **Tests (TDD: write the failing tests first).** All HTTP goes through a
   fake `session`, with no live API. `time.sleep` is patched wherever a 429
   path runs.
   - **Per skill, in-process, inside each skill's own suite:** replace the
     tests that assert the v3 fallback or `_stable_then_v3` with tests that
     assert stable-only URLs and params. A test asserts that no
     `/api/v3/` URL is ever requested, including on empty or 402 responses.
     Cover:
     - success shapes, empty/None, HTTP errors, the malformed-JSON retry;
     - 429 → `rate_limit_reached`;
     - budget exhaustion → the local exception (EP: `None`), mid-loop and,
       for 20pct, inside `get_stock_list`;
     - redaction of raw and URL-encoded key echoes;
     - a missing `requests` still raises the existing error;
     - CLI `--api-key` / `FMP_API_KEY` precedence;
     - the no-circuit-breaker regression: 4+ empty symbols, then a
       succeeding symbol that is still fetched;
     - the fluency all-fail → non-zero exit without saving the model book.
     These tests must cover the adapters and the extension primitives each
     skill uses, because pytest-cov 7 does not measure subprocesses.
   - **Coverage:** record each skill's coverage before and after with the CI
     matrix command (`--cov=skills/<id>/scripts`, which includes the vendored
     `fmp_client.py`). No skill may drop below its policy floor, and the PR
     reports the deltas.
   - **Repo level:** add the five to `GENERATED_SKILLS` and
     `NO_COMPAT_SKILLS` (`test_generate_fmp_client.py:18, :39, :80`) and to
     the redaction target lists (`test_fmp_client_redaction.py:209`). Add a
     test that the `stockbee_stable` extension renders only into these five
     clients. Add one isolated-subprocess smoke per skill, following the
     pattern of `test_dividend_fmp_migration.py`. It checks real-bundle
     isolation, not coverage.
6. **Gates, metadata and docs.**
   - **Regenerate and repackage:** run `scripts/generate_fmp_client.py`, then
     rebuild the five `.skill` archives.
   - **Target lists:** add the five skills to `ci.yml:282`,
     `.pre-commit-config.yaml:205/238/242`,
     `.github/pull_request_template.md:46` and
     `scripts/tests/test_github_templates.py`.
   - **Provider-contract owners:** update the owners in
     `config/provider-contracts/fmp/historical-price-eod-full.v1.json` (all
     five) and `quote.v1.json` (hammer). `company-screener.v1.json` already
     lists momentum, hammer and 20pct as owners. Its `tier_notes` still
     claim a consumer-side fallback to v3 `/stock-screener`, which is wrong
     after Batch B and after this batch, so those notes are corrected. Also update the ownership rows in
     `docs/dev/provider-contracts.md:239-247` and `:481`. Row :247 is
     already stale after Batch B, so correct its count too.
   - **New doc:** add `docs/dev/fmp-client-batch-c.md`.
   - **SKILL.md:** add a short "FMP transport" note to each.
   - **Generated skill docs:** regenerate only the three `generated: true` EN
     pages (`stockbee-episodic-pivot-analyzer`,
     `stockbee-momentum-burst-screener`, `stockbee-setup-fluency-trainer`)
     with `generate_skill_docs.py --skill <name> --overwrite`. Check the
     marker on the EN and JA pages separately first, never use `--force`,
     and verify that `nav_order` did not change.
   - **No changes expected:** `requirements.txt` stays `requests>=2.31.0`,
     matching the Batch B and pead-screener manifests. `skills-index.yaml`
     needs no change.

## Verification

- **Test suites:** run each skill suite in its own process, because the five
  share the module name `fmp_client`. Then run the generator, redaction,
  provider-contract and template tests.
- **Gates:** run `generate_fmp_client.py --check`,
  `generate_skill_docs.py --check`, the targeted `package_skills.py --check`
  for all 22 targets, and `check_skill_deps.py check` plus
  `smoke --skill` for the five.
- **Existing clients unchanged:** run
  `git diff --exit-code origin/main -- scripts/fmp_client/core_template.py.tmpl scripts/fmp_client/redaction.py.tmpl`
  plus the 17 pre-existing vendored `fmp_client.py` / `_fmp_compat.py`
  paths. This is a PR-time check, not a hash-snapshot test.
- **Workflow replay:** run the stockbee replay tests
  (`test_workflow_replay_ep.py`, `_twenty_pct.py`, `_trade_memory.py`). No
  golden refresh is expected, because replay scrubs the env and runs EP with
  `--max-api-calls 0`. Any golden diff is a regression.
- **Coverage, lint and greps:** per-skill coverage stays at or above the
  floor, with deltas reported. Run ruff and codespell. A grep confirms zero
  `api/v3` strings in the five **main scripts**; the vendored client still
  carries the core's v3 table by design.
- **Out of bounds:** no live API calls, secrets, trading actions or merges.

## Review log

Plan round 1: not approved; 5 major and 9 minor findings were all accepted.
The changes:
- quote primitive renamed to `fetch_*`;
- no-circuit-breaker rule stated;
- coverage plan made in-process, with deltas reported;
- generated-doc regeneration added;
- fluency kept fail-closed;
- exception translation required on every method;
- delegating attribute properties;
- explicit sibling load;
- intentional-change list completed;
- v3 grep scoped to the main scripts;
- byte-parity check moved to a PR-time diff;
- provider-contract owner files added;
- `time.sleep` patching and the replay expectation stated;
- scope rationale recorded.

Plan round 2: approved, with 7 minor notes, all accepted:
- per-skill `sys.modules` registration;
- tests use the adapter's module handle;
- `max_api_calls` and `last_call_time` are delegated;
- the `company-screener.v1.json` correction is limited to its `tier_notes`;
- 20pct `RuntimeError` propagation;
- the exact fluency all-fail rule;
- the hammer date test update;
- the `get_profile` exception is stated.

## Implementation reviews

Code round 1 found 1 major issue and 9 minor ones. All ten are fixed.

**Major**
- The `company-screener.v1.json` `tier_notes` claimed that every consumer is
  stable-only. In fact, us-undervalued-growth-screener, pair-trade-screener and
  downtrend-duration-analyzer still fall back to v3. The note now names both
  groups.

**Minor**
- History errors in hammer and fluency print redacted diagnostics again
  (`quiet=False`).
- 20pct `stats()` gains `rate_limit_reached`.
- The vacuous fluency redaction test now asserts the marker.
- A tautological 20pct assertion was removed.
- The per-skill isolated-subprocess smoke test that plan step 5 called for was
  added (`scripts/tests/test_stockbee_fmp_migration.py`).
- The docs now give EP's soft budget return value as `[]`.
- The EOD owner count was corrected.
- The help text for hammer `--asof-date` and EP `--api-key` was corrected.
- The `skills-index.yaml` note was corrected, and `CLAUDE.md` was regenerated
  from it.
- The core's sticky `retry_count` is documented rather than changed. It is
  inherited behavior shared by all 22 clients, and changing the core would
  touch the 17 clients outside this batch. The note is in
  `fmp-client-batch-c.md`, and the SKILL.md notes now say a 429 is retried
  "at most once".

Code round 2: approved. Two minor documentation issues and one nit were fixed:
- the stderr-diagnostics statement now matches the code: EP prints, and the
  hammer quote override stays quiet;
- the subprocess smoke test is listed under gate coverage;
- institutional-flow-tracker is labelled as Batch A.
