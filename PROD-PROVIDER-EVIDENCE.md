# PROD-PROVIDER-EVIDENCE — provider infrastructure hardening

- Branch: `agent/prod-provider`
- Candidate HEAD audited: `e6e7efc50d098aaf55b80c5b35e799c0c2e25a86`
- Code/test commit: `693843911c759652061de833001e685616791799`
- Owned files only:
  - `keel/src/keel/provider_contracts.py`
  - `keel/src/keel/provider_catalog.py`
  - `keel/tests/test_prod_provider.py` (new)
  - this evidence file
- No live provider call, socket, credential value or paid usage was used at any
  point. All failure transports are injected Python callables; all catalogs are
  temporary files or the bundled offline JSON.

## 1. Audit matrix

| Area | Where it lives | Result / hardening in owned files |
| --- | --- | --- |
| Registration | `provider_contracts.ProviderRegistry`, `ProviderDescriptor`, `search_catalog` | Permanent lowercase slug ids, one protocol per provider, explicit `user_approved`, bundled/paid excluded. Fixed a fail-open boolean coercion in `provider_from_dict` (see 2.1). |
| Model resolution | `provider_catalog.get_provider/model_ids/has_model`, `ExecutionConfig` | Catalog is informational only. Fixed cache poisoning and malformed-entry acceptance (2.3, 2.4). `validate_execution_config` checks a resolved model against the registered descriptor before any call. |
| Config validation | `validate_provider_descriptor`, `validate_execution_config` | Strict boolean types, https endpoint without credentials/whitespace/control chars/fragments, bounded attempts, backoff and timeout. Diagnostics never include values. |
| Request normalization | `adapt_request`, `normalize_request`, `image_preflight_message` | Deep copy, field-by-field compat overrides, credential-like keys removed at every depth with an explicit note, unsupported image content refused before send. |
| Response normalization | `normalize_response`, `usage_from_payload` | OpenAI Chat/Responses, Anthropic Messages and Gemini shapes reduced to `NormalizedResponse`. Error bodies and malformed/empty responses are refused; results carry no raw body, header or exception. |
| Streaming | `execute_stream`, `sanitize_event` | Events normalized and redacted; text/usage/stop accumulated; a failure after content yields `partial_failed` with text preserved, **no** retry and **no** fallback; cancellation preserves partial text. |
| Timeouts | `ExecutionConfig.timeout_seconds`, `CATEGORY_TIMEOUT` | Positive bounded timeout injected into every wire request; timeout failures are classified and retried with deterministic backoff. |
| Cancellation | `cancel.is_set()` checks in both executors, `ProviderCancelled` | Checked before every attempt and every streamed event; cancellation is a normal terminal status, never counted as a provider error. |
| Error classification | `classify_status`, `classify_payload`, `classify_exception` | 19-category taxonomy; HTTP status map, provider error-code markers, stdlib `TimeoutError`/`ConnectionError`/`OSError`/`JSONDecodeError` and injected `ProviderTransportError`. All messages redacted and bounded. |
| Retries/backoff | `retry_schedule`, injected `sleep` | Exponential `base * factor ** (attempt-1)`, capped by `max_backoff_seconds`, overridden by a bounded `retry_after`. No randomness, no wall-clock sleep in the policy. Security/permission/invalid/context failures are never retried. |
| Rate limits | 408/429 mapping, `extract_retry_after` | `retry_after`, `retry_after_ms`, `error.retry_after(_ms)` and `Retry-After` header parsed; non-numeric/bool rejected; clamped to 0–60 s and then to the configured cap. |
| Usage metadata | `UsageMetadata`, `merge_usage` | Token counts read from vendor-specific fields, invalid counts become zero, streamed usage merged across events. |
| Credential handling / redaction | `SecretDescriptor`, `describe_secret`, `redact_message`, `_scrub` | Raw secret accepted only by `describe_secret`; descriptors/audit records carry name and masked hint only. Errors and events scrub known secrets and common token shapes (`Bearer`, `sk-`, `AKIA`, `ghp_`) and are length-bounded. No credential is placed in the injected wire request. |
| Fallback | `ExecutionConfig.fallbacks`, `FALLBACK_CATEGORIES`, `validate_execution_config` | Empty by default. Only capacity/transport failures can fall back, only to explicitly named providers that are registered, approved, non-bundled and non-paid; duplicates and self-fallback rejected; never after partial stream content. |

## 2. Confirmed defects fixed (test-first: each regression test failed before the fix)

### 2.1 HIGH — approval gate bypassed by string `"false"` / numeric booleans
`provider_from_dict` used `bool(data.get("user_approved", False))`, so a JSON
setting `"user_approved": "false"` became `True` and satisfied the explicit
registration gate; `paid: 0` and `bundled: ""` became `False` and hid a paid
provider. Now `_strict_bool` rejects every non-`bool` with a
`ProviderContractError` naming the field. Tests:
`test_approval_gate_cannot_be_bypassed_by_string_false`,
`test_registration_boolean_fields_are_strict`.

### 2.2 MEDIUM — CRLF / whitespace accepted in provider endpoints
`_validate_endpoint` accepted `https://host/v1\r\nX-Evil: 1`, and URLs with
embedded spaces/tabs. Now whitespace/control characters and fragments are
rejected before the URL ever reaches a transport. Test:
`test_endpoint_rejects_crlf_and_embedded_whitespace`.

### 2.3 MEDIUM — cached catalog could be poisoned by callers
`get_provider()` returned the live dict inside the process-wide `_CACHE`; a
caller mutating `models` or `id` permanently changed what every later call saw.
The cache is now internal; `load_catalog()` and `get_provider()` return isolated
copies. Test: `test_catalog_get_provider_does_not_expose_the_live_cache`.

### 2.4 MEDIUM — truncated/tampered catalogs loaded silently
`load_catalog` validated only top-level key presence. A `models` string was read
as a list of characters; wrong `provider_count`/`model_count` and unknown schema
versions were accepted. Now schema version, entry shapes, per-entry ids, model
types and both declared counts are validated and fail closed. Tests:
`test_catalog_rejects_malformed_models_field`,
`test_catalog_rejects_inconsistent_counts_and_schema`,
`test_catalog_entry_must_be_an_object_with_a_matching_id`,
`test_offline_catalog_loads_without_network` (existing, still passes).

## 3. Added offline runtime policy (auditable, injection-only)

`provider_contracts.py` gained a stdlib-only policy section:
`ExecutionConfig`, `TransportResponse`, `ProviderFailure`,
`ProviderTransportError`, `ProviderCancelled`, `RetryDecision`, `AttemptRecord`,
`ProviderResult`, `UsageMetadata`, `NormalizedResponse`, plus
`classify_status`, `classify_payload`, `classify_exception`, `normalize_request`,
`normalize_response`, `sanitize_event`, `extract_retry_after`, `retry_schedule`,
`validate_execution_config`, `execute_request` and `execute_stream`.

The policy never imports a network library and never constructs a credential.
It consumes a caller-supplied `transport(request_dict)` callable, so deterministic
failure injection covers the full error matrix without a live endpoint. Sleeper
and cancellation objects are also injected; backoff values are computed, not
waited on. No existing call site was modified — adopting this layer is an
explicit caller decision (see the live-validation gap).

## 4. Deterministic failure-injection tests

`keel/tests/test_prod_provider.py` — **55 tests**, all offline:

- auth failure (HTTP 401 and injected category), invalid credentials, timeout,
  connection error, HTTP error normalization across 401/403/404/422/429/500/503,
  malformed response, rate limit with bounded `retry_after`, context-limit error,
  provider unavailable (with and without explicit fallback), cancellation before
  and during a call, streaming partial failure, streaming cancellation, stream
  error events, usage accumulation and credential redaction.
- fallback discipline: no fallback for auth/credential/context-limit failures;
  no fallback unless explicitly configured; never replay after streamed content;
  validation rejects unregistered, unapproved, paid, bundled, duplicate and
  self fallbacks.
- local operation: `ExecutionConfig()` with no provider yields `no_provider`,
  zero transport calls and zero validation diagnostics.
- no paid path: a paid/bundled descriptor is rejected before the transport is
  called, and `ProviderDescriptor` itself refuses paid/bundled construction.

Commands and results (candidate worktree, branch `agent/prod-provider`):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_provider.py','keel/tests/test_provider_contracts.py','keel/tests/test_provider_catalog.py']))"
```

`test_provider_catalog.py` does not exist in this revision, so the verified
command omits that absent path:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_provider.py','keel/tests/test_provider_contracts.py']))"
-> 140 passed
```

Additional regression set: `test_m2_provider_config.py`, `test_providers.py`,
`test_provider_validation.py`, `test_provider_sources.py`,
`test_model_dialects.py` -> **102 passed, 1 skipped**.

Out-of-scope environmental note: `test_webapp.py::test_run_streams_events_and_done_marker`
times out on the local loopback HTTP fixture on this Windows host. It was
reproduced with the owned files stashed back to candidate `e6e7efc`, so it is a
pre-existing host/fixture issue, not a regression from this work.

## 5. Exact live-validation gap

**What was not validated:** no request was sent to any real provider. Therefore
the following remain unverified by this evidence: real endpoint reachability and
TLS behavior; each vendor's exact status/body/error-code vocabulary; real SSE
framing and reconnect behavior; real token-usage fields for a pinned model; real
`Retry-After` semantics; real urllib cancellation propagation; validity of any
credential; and actual quota/cost effects of retries and fallback. Category
mappings in this layer are deliberately conservative and are derived from the
offline taxonomy in `keel.providers.base` plus documented status classes — they
are claims, not live facts.

**Integration gap:** the new policy is additive. `keel/providers/model_client.py`
and the vendor adapters still perform their own classification and are outside
the owned files. Production callers must opt in by constructing
`ExecutionConfig` and passing a production transport into `execute_request` /
`execute_stream`; no such rewiring was performed here.

**Credentials/config needed to close the gap (names only; no values were used or
stored here):** an operator-approved, disposable/free-tier account and, for each
provider actually tested, the environment key `KEEL_OPENROUTER_API_KEY`,
`KEEL_GOOGLE_API_KEY`, `KEEL_NVIDIA_API_KEY`, or
`KEEL_COMPAT_API_KEY` **plus** `KEEL_COMPAT_BASE_URL` and `KEEL_COMPAT_MODEL`.
`KEEL_ANTHROPIC_API_KEY` is opt-in only (`--provider anthropic`, licensing review
OPEN-Q1) and must not be enabled by default. Also needed: `KEEL_DEFAULT_PROVIDER`
and an explicit model (e.g. `KEEL_GOOGLE_MODEL`), `user_approved: true` on a
non-bundled, non-paid descriptor, `fallbacks: ()` during initial validation, and
a hard spend cap/throwaway budget.

**How to close it safely:** with explicit operator approval, inject the real
`keel.providers.base.http_transport` into the executors, send one tiny prompt
(`max_output_tokens: 16`, no images, no tools), record observed status/event
sequences and normalized category/usage, assert no secret appears in any log or
result, then separately exercise cancellation and a deliberate rate-limit
response. Record those results in a new evidence file under a separate branch
with paid usage enabled only by the operator. This subagent was explicitly
prohibited from network calls, credential use and paid usage, so it did not do
so.

## 6. Local-operation and paid-path conclusion

- No provider is mandatory for local operation: an empty `ExecutionConfig` is
  valid, `execute_request` returns `no_provider` without invoking the transport,
  and the existing offline/fake-script test suites pass.
- No automatic paid usage path exists in the owned layer: paid and bundled
  descriptors are rejected at construction and again before execution; fallback
  is empty unless explicitly configured and is restricted to registered,
  approved, non-paid providers; security failures are never retried; and streamed
  content is never replayed after a partial failure.
