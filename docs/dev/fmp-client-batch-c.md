# FMP client migration: stockbee Batch C (#495)

The following standalone skills now vendor a generated `scripts/fmp_client.py`
from `scripts/fmp_client/registry.py`, the shared family-B core with API-call
budget, and the `stockbee_stable` extension:

- `stockbee-20pct-study`
- `stockbee-episodic-pivot-analyzer`
- `stockbee-exhaustion-hammer-screener`
- `stockbee-momentum-burst-screener`
- `stockbee-setup-fluency-trainer`

Each main script keeps a thin module-level `FMPClient` adapter that preserves
its public class name, constructor, methods, return shapes and stats keys. The
adapter loads the sibling generated client by file path under a per-skill
module name, so the five bundles never share a `fmp_client` module. HTTP,
authentication, redaction, rate limiting, JSON retry, 429 handling and budget
accounting run in the generated client. The existing seventeen generated clients
are unchanged: the core template and redaction fragment are untouched.

The extension adds three stable-only primitives on top of the shared
`_rate_limited_get`:

- `fetch_screener_rows(params)` for `/stable/company-screener`
- `fetch_eod_rows(symbol, days, pad_days=10)` for
  `/stable/historical-price-eod/full`
- `fetch_quote_row(symbol)` for `/stable/quote`

They return the provider list unchanged (`[]` when the provider answered
without rows) or `None` on a transport error, an HTTP error or a non-list 200
body. They never call `_record_endpoint_failure` or consult
`_disabled_endpoints`: an empty answer for a delisted or new ticker is data,
not an endpoint failure, so no streak of empty symbols can disable a scan.

## Preserved behavior

CLI `--api-key` / `FMP_API_KEY` precedence, report formats, universe filters,
sorting, normalizers (`normalize_fmp_historical_response`,
`normalize_price_bars`, `normalize_bars`), quote-bar construction and every
non-client function are unchanged. Offline paths (`--prices-json`, event JSON,
model-book files) still run without `requests`, and the existing "requests
missing" errors are kept. Each adapter keeps its local budget exception class
and translates the shared `ApiCallBudgetExceeded` into it. Episodic-pivot keeps
its soft budget behavior: `get_historical_prices` returns `[]`. Each skill keeps its own default budget.
Non-budget exceptions from the shared layer, such as the tzdata
`RuntimeError`, propagate.

Episodic-pivot's unused `get_profile` was deleted with its tests. It is the
only public method removed.

## Intentional transport changes

- Stable only. A 402, 403 or empty stable response no longer tries a v3 URL.
  The quote call in the hammer screener moves from v3 `quote/{symbol}` to
  `/stable/quote`.
- A 429 waits 60 seconds and retries once; a repeated 429 sets
  `rate_limit_reached`. The shared core resets its retry counter only on an
  HTTP 200, so after a 429 whose retry ended in another error, the next 429
  stops immediately without waiting. This is inherited core behavior shared by
  all generated clients. Momentum and hammer previously stopped immediately;
  20pct, fluency and episodic-pivot did not track 429.
- A malformed 200 JSON body is retried once, then fails soft.
- History windows use the America/New_York date. The hammer default bar date
  uses the same helper.
- 20pct switches from query-parameter auth to header auth. Hammer drops its
  duplicate query-parameter key.
- Episodic-pivot's counter counts completed responses plus retries, and no
  longer counts requests that raised a transport exception.
- HTTP-error diagnostics are redacted instead of printing the raw
  `response.text[:200]`. History and universe failures print their status to
  stderr in all five skills. Episodic-pivot was silent before and now prints
  them too. The best-effort hammer quote override stays quiet.
- Fluency no longer propagates a raw `RequestException`. Because failures are
  now soft, `command_update` fails closed. A request fails when the shared fetch
  returns `None`, which covers transport errors, HTTP errors and the 429
  short-circuit; `[]` is not a failure. If all N symbols fail, it prints
  `ERROR: FMP price fetch failed for all N symbols; model book not updated` to
  stderr, returns exit code 1, saves no model book and writes no report. If only
  some fail, the model book is saved and the report carries `failed_requests`.
  `--prices-json` runs are unaffected, and budget exhaustion still raises.
- 20pct's fetch loop no longer swallows `RuntimeError`.

## Gate coverage

The generated client drift gate covers 22 targets. CI, pre-commit and the PR
template package checks include the five new archives, and the provider
contracts list the stockbee skills as owners of `historical-price-eod-full`
(all five), `quote` (hammer) and `company-screener` (momentum, hammer, 20pct).
The `company-screener` contract notes now say which consumers are stable-only
and which three still fall back to v3 `/stock-screener`. Repo tests cover the extension rendering only into these five
clients, no circuit breaker in the extension block, and fake-transport checks of
the three primitives: stable URL and params, the ET window, `None` on HTTP error
or non-list body, `[]` passthrough, and no request to `/api/v3/`. Each skill
suite runs in its own process because the bundles share the module name
`fmp_client`. `scripts/tests/test_stockbee_fmp_migration.py` loads each
bundle in a fresh interpreter. It asserts that the adapter uses its own
sibling client, never imports the bare `fmp_client` name, and sends requests
only to `/stable`.

This PR completes Batch C, not the remaining #495 batches.
