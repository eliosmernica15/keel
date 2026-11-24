# Master Plan v6 — Webhooks & Channels Evidence (Agent 32)

- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\final\webhooks`
- Branch: `agent/f-webhooks` (based on `463481e`)
- Baseline SHA: `463481e`
- Environment: Python 3.11.9, pytest 9.0.2
- Commands were run from `keel/` with
  `PYTHONPATH=C:\Users\Admin\.local\share\opencode\worktree\final\webhooks\keel\src`
  so the worktree copy of `keel` is imported, not the editable install of the
  main checkout. All secrets used are synthetic test strings.

## Summary

| # | Weakness | Status |
|---|----------|--------|
| 1 | Signed messages replayable indefinitely inside the 300 s freshness window | Fixed |
| 2 | No receiver-side validation helper that enforces replay safety; nonce could never be validated | Fixed |
| 3 | Signature comparison needed verification that it is constant-time | Verified already correct + regression guard |
| 4 | Retry attempts produced different signed bytes and had no stable delivery identity, so retries could be processed twice | Fixed |
| 5 | Outbox JSONL appends were not serialized/durable (no lock, no `O_APPEND`, no `fsync`) | Fixed |
| 6 | `SubscriptionStore._save` used non-atomic `write_text` (truncation window / partial document) | Fixed |
| 7 | `deliver_with_fallback(..., max_attempts=0)` sent to the first channel because of a falsy `or` | Fixed |

No network calls or new dependencies were introduced. Existing signatures made
without a nonce keep the exact legacy wire format (`ts.body`).

## 1. Replay of signed messages

**Reproduction (baseline, synthetic secret):**

```text
signature: sha256=e67595616312f866a65e468f348cd6e2a4b0de952067fe0cc43e53f7eb1027be
first verify : True
replay verify: True
tampered body: False
has NONCE_HEADER: False
has NonceCache: False
```

`verify()` checked only `abs(now - ts) <= max_age`; the same signed request could
be accepted any number of times within 300 seconds.

**Fix (`keel/src/keel/webhooks.py`):**
- Added `NONCE_HEADER = "X-Keel-Nonce"`, `DEFAULT_SEEN_CAPACITY = 4096`.
- `sign(..., nonce=...)` binds an unambiguous, length-prefixed nonce into the HMAC.
- `verify(..., nonce=..., seen=...)` checks the signature with
  `hmac.compare_digest` **first**, then records a SHA-256 replay key
  (`ts + "." + nonce + "." + body`) in a bounded `NonceCache`; a repeat returns
  `False`. If a cache is supplied but no nonce is present, verification fails
  closed. Invalid signatures never consume a nonce (no cache-poisoning DoS).
- `NonceCache` is a thread-safe, insertion-ordered LRU-style cache with a hard
  capacity and optional atomic file persistence under `state_root`
  (`webhook-seen-nonces.json`), so a restart does not re-enable old replays.
- `WebhookVerifier` is the receiver helper that always requires a nonce and
  always uses the cache.

**Regression tests:** `test_signed_message_cannot_be_replayed`,
`test_nonce_is_bound_to_signature`, `test_invalid_signature_does_not_consume_nonce`,
`test_nonce_cache_is_bounded`, `test_verifier_enforces_replay_and_persists_state`,
`test_verifier_fails_closed_without_nonce`.

## 2. Missing replay-safe validation path

**Reproduction:** baseline `webhooks.py` exported only `sign`/`verify`/`deliver`;
there was no nonce header, no seen cache, and no validation helper that could
reject a replay.

**Fix:** `WebhookVerifier(secret, state_root=...).verify(body, signature,
timestamp, nonce)` performs timestamp freshness, constant-time HMAC validation
and persisted replay detection in one call.

**Regression tests:** `test_verifier_enforces_replay_and_persists_state`,
`test_verifier_fails_closed_without_nonce`.

## 3. Constant-time comparison

**Reproduction:** source inspection of baseline `verify` showed
`hmac.compare_digest(expected, signature)` was already in use — this was **not**
a defect. A regression guard was added so a future refactor to `==`/`!=` fails.

**Regression test:** `test_verify_uses_constant_time_comparison` (asserts
`hmac.compare_digest` present and no direct `==`/`!=` against `signature`).

## 4. Retries duplicating messages

**Reproduction (baseline):**

```text
deliver headers: ['Content-type', 'User-agent', 'X-keel-signature', 'X-keel-timestamp']
deliver has nonce header: False
send() return keys: ['attempts', 'ok', 'status']
```

Each retry called `deliver()` which called `sign()` with a fresh `time.time()`,
so the signature changed per attempt and a receiver had no stable identifier to
deduplicate on. A lost response after the receiver processed the event caused a
duplicate action.

**Fix (`keel/src/keel/webhooks.py`, `keel/src/keel/webhook_delivery.py`):**
- `deliver()` accepts `nonce` and `timestamp` and emits `X-Keel-Nonce` when a
  nonce is given.
- `WebhookDelivery.send()` generates one `delivery_id` (`secrets.token_urlsafe`)
  and one timestamp per logical send, and reuses both on every retry. All retry
  requests are byte-identical, so a `WebhookVerifier` deduplicates them by nonce.
- `delivery_id` is added to each delivery-log entry and to the return value
  (additive; existing keys unchanged).

**Regression tests:** `test_deliver_sends_nonce_header_with_matching_signature`
(real local HTTP server), `test_retries_reuse_one_delivery_identity`
(monkeypatched network edge only).

## 5. Non-atomic outbox writes

**Reproduction (baseline):** source inspection —
`outbox uses os.open: False`; `deliver_to_outbox` used plain `open(..., "a")`
with no lock and no `fsync`, allowing interleaved lines or lost data.

**Fix (`keel/src/keel/channel_ops.py`):** added `_OUTBOX_LOCK` (module-level
`threading.Lock`) and `_append_jsonl()` which creates the parent dir, opens with
`os.O_WRONLY | os.O_CREAT | os.O_APPEND`, writes the full line in one `os.write`
and `os.fsync`s it. `deliver_to_outbox` now calls this helper.

**Regression tests:** `test_parallel_outbox_writes_produce_valid_jsonl` (40
threads, all lines valid JSON and present), `test_outbox_write_is_locked_and_durable`.

## 6. Non-atomic subscription writes

**Reproduction (baseline):**

```text
subscription save uses os.replace: False
```

`write_text` truncated the live file before writing, so a crash or concurrent
reader could see an empty/partial subscription document.

**Fix:** `_save()` writes to `<file>.tmp`, flushes + fsyncs, then `os.replace`s
it into place (atomic rename on the same filesystem).

**Regression tests:** `test_subscription_save_uses_atomic_replace`,
`test_subscription_save_leaves_no_temp_file`.

## 7. `max_attempts=0` fallback bug

**Reproduction (baseline):**

```text
called ['a'] — expected []
```

`chain[:max_attempts or len(chain)]` treated `0` as "no limit".

**Fix:** `selected = chain if max_attempts is None else chain[:max(0, max_attempts)]`.

**Regression test:** `test_fallback_max_attempts_zero_means_no_calls`.

## Test results (exact commands and output)

New regression tests run against the **baseline** code (before fixes):

```text
python -m pytest tests/test_webhook_security.py -q
...FFFFFFFFFFF.F [100%]
11 failed, 5 passed in 3.43s
```

After fixes:

```text
python -m pytest tests/test_webhook_security.py -q
................ [100%]
16 passed in 2.80s

python -m pytest tests/test_webhook_security.py tests/test_webhooks.py ^
  tests/test_webhook_delivery.py tests/test_channel_ops.py tests/test_no_fake_success.py -q
............................. [100%]
29 passed in 36.70s

python -m pytest tests/test_message_state.py tests/test_security_validation.py ^
  tests/test_security_remediation.py -q
............... [100%]
15 passed in 6.48s
```

(`^` above is line continuation for readability; commands were executed as a
single line in PowerShell.)

## Files changed

- `keel/src/keel/webhooks.py` — nonce-aware signing, bounded/persistent replay cache, verifier helper, delivery nonce/timestamp headers.
- `keel/src/keel/webhook_delivery.py` — stable delivery identity across retries.
- `keel/src/keel/channel_ops.py` — atomic outbox append, atomic subscription save, `max_attempts` fix.
- `keel/tests/test_webhook_security.py` — NEW, 16 regression tests.
