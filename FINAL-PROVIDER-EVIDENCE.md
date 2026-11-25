# FINAL-PROVIDER-EVIDENCE.md

Final provider integration and opt-in live-harness evidence for branch
`agent/final-provider` at completion HEAD `35fb2b8`.

## 0. Honest status in one paragraph

All provider work recorded here is **offline integration and fail-closed gate
verification**. **No live provider request was made and no credential value was
read, printed, stored or spent.** A presence-only environment check (using
`os.environ.get` on the known provider key variables) found **no approved free-tier
credential**, so live validation is **external-pending** by design. The live
harness exists, is documented, and is tested with injected transports for every
negative/absent case; it cannot make a request until an operator explicitly opts
in AND documents a current free-tier confirmation.

## 1. Owned files

| File | Purpose |
| --- | --- |
| `keel/src/keel/provider_contracts.py` | Provider contract/runtime policy (registration, descriptors, normalization, classification, retry, fallback, streaming, cancellation). One defect fixed here (see §4). |
| `keel/src/keel/provider_catalog.py` | Bundled offline catalog loading/validation (unchanged this branch; verified). |
| `keel/src/keel/provider_validation.py` | Honest validation matrix; credentials are presence-only, SKIP/FAIL semantics (unchanged this branch; verified). |
| `keel/tests/test_final_provider.py` | New: 31 offline integration + harness gate tests. |
| `scripts/verify_live_provider.py` | New: opt-in, fail-closed, one-request live harness. |
| `FINAL-PROVIDER-EVIDENCE.md` | This file. |

No frontend files were touched. Nothing was pushed.

## 2. Credential check (presence only)

Checked with `os.environ.get` on the approved free-tier key variables
(`KEEL_OPENROUTER_API_KEY`, `KEEL_GOOGLE_API_KEY`, `KEEL_NVIDIA_API_KEY`) and the
other known provider key variables, treating whitespace-only values as absent.
No value was printed or logged.

**Credential existed: no.**

Because no credential is present, §3 executed entirely through injected
transports and the harness was never allowed past its gate in this environment.

## 3. Offline integration verification (executed)

`keel/tests/test_final_provider.py` (31 tests) covers:

- **Registration** — `ProviderRegistry.add` requires explicit user approval,
  rejects duplicates, and validates descriptors; the runtime registry exposes
  the five expected adapters; catalog-only providers are refused as executable.
- **Config validation** — plain-HTTP endpoints, URLs with embedded credentials,
  unknown protocols and empty model lists fail closed; JSON string approval
  (`"user_approved": "false"`) cannot be coerced into a true approval.
- **Model discovery** — catalog info reports consistent counts; a caller-mutated
  catalog copy cannot poison the cached original; a tampered count fails with
  `CatalogError`.
- **Request normalization** — credential-like fields are removed, secrets are
  redacted, and max-token claims are clamped to declared model limits with all
  adjustments reported; the unverified-claims warning is present.
- **Streaming** — text deltas accumulate, usage is normalized, and a failure
  after content yields `partial_failed` with the text preserved and **no
  replay/fallback**.
- **Timeouts** — validation's wall-clock budget reports `live_timeout` FAIL, not
  a silent PASS or SKIP.
- **Cancellation** — pre-cancelled execution makes no transport call; adapter
  `TurnCancelled` now classifies as the policy `cancelled` category.
- **Bounded retries** — rate-limit retries stop exactly at `max_attempts` (5 of
  5 calls, 4 backoff entries); auth failures are attempted once only.
- **Error classification** — status/payload/exception mappings are conservative
  and secret-redacted; security and credential failures are non-retryable.
- **Health diagnostics** — offline validation reports only SKIP for live checks;
  execution-config diagnostics are value-free.
- **Fallback cannot route to paid services** — a paid fallback is rejected by
  config diagnostics and `execute_request` returns `failed` **without calling the
  transport**; `search_catalog` excludes paid and bundled entries.

## 4. Defect fixed

`keel/src/keel/provider_contracts.py::classify_exception` recognised only the
policy layer's `ProviderCancelled`. An adapter-level `keel.providers.base.TurnCancelled`
(raised by a user-initiated stop) therefore fell through to `unknown`, which made a
normal cancellation look like an unclassified provider failure. The function now
recognises both signal types via a lazy import, keeping the module dependency-free
at import time. Regression coverage is in
`test_final_provider.py::test_error_classification_redacts_and_never_retries_auth`.

No other defect was found in the owned modules while running the verification
suites; the remaining suites already passed at HEAD with the worktree source on
`PYTHONPATH` (the machine's global `keel` install shadows the worktree when tests
are launched from the wrong directory — always run with the worktree `keel/src`
first on `sys.path`, as the clean-HOME runner does).

## 5. Opt-in live harness

`scripts/verify_live_provider.py` makes **at most one** request and only when
**all** of these hold:

1. explicit `--allow-live-provider-check` flag;
2. explicit `--confirm-free-tier-current` flag (operator asserts current terms
   were re-verified);
3. a JSON confirmation record (via `--confirmation-file` or
   `KEEL_LIVE_CONFIRMATION_FILE`) with `schema_version=1`, an allowed provider,
   an explicit free-tier model, a named operator, an ISO `confirmed_at` within
   30 days, and boolean-true `free_tier_current` and `no_paid_usage`;
4. a non-blank, well-formed credential for that provider present in the
   environment (presence checked with `os.environ.get` only);
5. provider on the free-tier allowlist (`openrouter`, `google`, `nvidia`) and
   model matching the confirmation; OpenRouter models must carry `:free`.

Fail-closed specifics:

- any missing gate → `blocked`, exit code 2, **zero transport calls**;
- no retry, no fallback (`max_attempts=1`, `fallbacks=[]`), `max_output_tokens=16`,
  no tools, no images, wall-clock budget 15 s, one-call transport guard;
- paid/opt-in providers (notably Anthropic) and unknown providers are never
  eligible; there is no code path that enables paid usage automatically;
- the final report is scrubbed against every known credential value before it
  is printed or written.

Recorded fields are limited to `kind`, `status`, `provider`, `model`,
`timestamp_utc`, `commit`, `quota_context` and `result`. No credential value,
prompt text, response text, header or raw payload is recorded. Result details
are bounded to `text_chars`, stop reason, token counts, an error **category** and
gate reasons (which name environment variables, never values).

Tested negative/absent cases with injected transports (no live endpoints):
both flags missing individually; confirmation file missing; stale confirmation;
`free_tier_current=false`; `no_paid_usage=false`; missing operator; `auto`/paid
model; model mismatch; credential absent, blank or malformed; paid/unlisted
provider; confirmation containing a credential; a failing provider (no retry);
and a timeout. Positive paths (explicit file and env-provided file) use a fake
OpenAI-compatible SSE transport and assert the safe-field contract.

## 6. Verification run (clean HOME)

Executed from `keel/src` with `HOME` and `USERPROFILE` pointed at a fresh empty
temporary directory and `PYTHONNOUSERSITE=1`, with the worktree `keel/src` first
on `sys.path`:

```
test_final_provider.py (31) + test_prod_provider.py + test_provider_validation_ready.py
+ test_stab_provider.py  →  139 passed, 0 failed
```

Earlier `test_stab_provider.py` failures observed when invoking pytest from the
wrong directory were caused by the global `keel` install shadowing the worktree
source, not by this branch; they disappear with the worktree source imported.

## 7. Live verification pending (external)

The following cannot be claimed until an operator supplies a credential and a
current free-tier confirmation and runs the harness for real:

- real endpoint reachability, TLS behaviour and DNS resolution;
- each vendor's exact status/body/error-code vocabulary and `Retry-After`
  semantics;
- real SSE framing, reconnect behaviour and stream cancellation propagation;
- real token-usage fields for a pinned model and quota/cost effects of any
  retry/fallback (the harness performs none);
- validity of any credential, and whether the operator's account is still on a
  free tier at the time of the run.

**How to close safely:** re-verify current free-tier terms; write a confirmation
JSON as specified above; set exactly one approved provider key; run the harness
with both explicit flags and a private `--results-json` path; record the
produced safe report in a separate evidence file under operator control. Do not
enable Anthropic, do not configure fallbacks, and do not raise
`max_output_tokens` above the harness cap. This subagent made no network call
and did not enable paid usage.
