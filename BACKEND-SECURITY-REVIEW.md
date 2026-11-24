# Independent Security Red Team — Production Release Gate

| Field | Value |
|---|---|
| Candidate HEAD | `e6e7efc` (branch `agent/prod-security`) |
| Scope | Backend-only promotion (20 backend modules, capability hub, web bridge, workflow seam) |
| Method | Live probes against `keel serve` on `127.0.0.1:18937`, direct module probes, real multi-process races |
| Worktree | `C:\Users\Admin\.local\share\opencode\worktree\production\security` |
| Verdict | **BLOCK** — 3 HIGH findings (any HIGH blocks per gate rule) |

> No source files were modified. All probe scripts and artifacts live under
> `C:\Users\Admin\AppData\Local\Temp\opencode\secprobe\`.

---

## Verdict — HIGH findings first

### H-1 (HIGH) — SSRF via unvalidated HTTP redirects in `web_fetch`

**File:** `keel/src/keel/runner.py:782-786`
**Repro:** `probe_ssrf.py` (local listener returns `302 Location: http://127.0.0.1:18939/secret`).

```
=== 5 redirect to loopback (post-check) ===
  url=http://rebind.example.com:18939/redirect
  OUT='LOCAL-ONLY-METADATA-secret-9182'
  META={'url': 'http://127.0.0.1:18939/secret', ...}
```

**Analysis:** `_web_fetch` validates the *initial* hostname/IP at lines 748-772, then calls
`opener.open()` at line 783. `urllib` follows 3xx redirects by default and never
re-runs the allowlist / private-range / metadata checks. `resp.geturl()` at line
786 even records the final internal URL, confirming the redirect was followed.
An attacker who controls any allowed external URL (or injects a URL into an agent
prompt / fetched document) can reach `127.0.0.1`, `169.254.169.254`, RC1968,
and other internal services. This defeats the entire SSRF guard.

**Fix:** Install a custom `HTTPRedirectHandler` that re-applies `check_url()` +
DNS/IP validation to every `Location` before following, cap redirect count, and
disable automatic redirects entirely if re-validation is not implemented.

---

### H-2 (HIGH) — SSRF via DNS-rebinding TOCTOU between validation and connect

**File:** `keel/src/keel/runner.py:752-754` and `:783`
**Repro:** `probe_ssrf.py` (monkeypatched `socket.getaddrinfo`: port `None` → public
`93.184.216.34`, port `18939` → `127.0.0.1`, simulating a hostile DNS server).

```
4 DNS rebind to loopback
  url=http://rebind.example.com:18939/secret
  OUT='LOCAL-ONLY-METADATA-secret-9182'
```

**Analysis:** The address used for the security decision (`socket.getaddrinfo(host, None)`
at line 754) is discarded. `urllib.request` performs a *second, independent*
`getaddrinfo()` when opening the connection at line 783. A rebinding DNS name can
return a public IP for the check and a loopback/link-local IP for the connection.
The direct-literal and IPv4-mapped-IPv6 checks work (`::ffff:127.0.0.1` is
correctly flagged `is_private`/`is_reserved`), but hostname rebinding bypasses all of them.

**Fix:** Resolve once, validate every returned IP, then connect to the validated IP
with the original `Host` header and SNI preserved (or pin the validated address
set through a custom connection class) so check and use cannot diverge.

---

### H-3 (HIGH) — Tier-2 non-configurable safety envelope bypassed by directory junction / symlink

**Files:** `keel/src/keel/safety.py:86-112` (`_norm`, `_is_secret`, `_classify_target`),
`keel/src/keel/runner.py:412-419` (`_safe_path`)
**Repro:** `probe_symlink2.py` (creates `mklink /j workspace\innocuous -> hidden\.ssh`).

```
classify direct: secret-bearing path
classify via   : None
tier2 direct: Check(allowed=False, reason='read of a secret-bearing path is refused (...\hidden\.ssh\notes.txt)')
tier2 via   : Check(allowed=True, reason='')
direct -> ERR ValueError: tier-2 refused: read of a secret-bearing path is refused (...)
via-junction -> PRIVATE-CONTENT-abcdefg | {'type': 'text', 'file': {'filePath': '...\workspace\innocuous\notes.txt' ...}}
```

**Analysis:** Tier 2 is documented as an unconfigurable envelope that "OVERRIDES a
Tier-1 allow" and protects `.ssh`, `.aws`, keys, etc. Both `_classify_target()` and
`_safe_path()` operate on the **lexical** path string and never resolve the final
path. A junction/symlink with an innocuous name inside the workspace hides the
protected target from the regexes, and `read_file` happily returns the secret
content. On Windows, `mklink /j` needs no admin rights, so the agent can create
the junction itself via `run_shell` and then read a secret with `read_file`.

**Fix:** Before classification, `Path(path).resolve(strict=False)` (and on POSIX open
with `O_NOFOLLOW` / verify `lstat` at each component); classify the resolved path,
return the resolved path, and re-check immediately before the actual open to close
the TOCTOU window. Apply the same to `_confined_dir`/`_confined_file` callers.

---

## MEDIUM findings

### M-1 (MEDIUM) — Public share artifacts omit JWT / AWS / private-key redaction vocabulary

**File:** `keel/src/keel/w7_x1_y5_d1_backend.py:64-67` (`_SECRET_RE`), used by
`public_share_view()` at `:792` and `render_share_html()` at `:820`.
**Repro:** `probe_share.py`.

```
VIEW: {'text': 'JWT=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefghij | aws_key=AKIAIOSFODNN7EXAMPLE | openrouter=[REDACTED] | ...'}
JWT leaked? True
aws_key leaked? True
```

**Analysis:** `keel.redaction` recognises JWTs, AWS key IDs, OpenRouter keys and PEM
private keys, but the independent `_SECRET_RE` in the share module does not. Any
live JWT or AWS credential in a transcript is published verbatim in a "public
share" view and its HTML export. The two DLP vocabularies must be one.

**Fix:** Make `_scrub_secrets()` delegate to `keel.redaction.redact_text()` (extend the
latter if needed) so every artifact shares one pattern set; add regression tests
that feed JWT/AWS/OpenRouter/private-key fixtures through `public_share_view`.

### M-2 (MEDIUM) — Caller-chosen `state_root` allows arbitrary directory creation and ledger writes

**File:** `keel/src/keel/backend_workflows.py:263-268` (`_state_root`), reached from
`webapp.py:601-643` via `params.state_root`.
**Repro:** `probe_misc.py`.

```
ARBITRARY ROOT: ok created? True ledger? True
```

**Analysis:** Any caller that passes token + `confirm:true` can set `state_root` to any
path the process can write; `_state_root` calls `mkdir(parents=True)` and every
workflow then writes JSONL files there. There is no confinement to `KEEL_STATE_DIR`.
In a multi-agent/fleet context this is a cross-project write primitive.

**Fix:** Derive the root exclusively from `KEEL_STATE_DIR` (or a server-configured
allowlist); if a caller-supplied root is ever permitted, require it to be a
pre-registered project key and resolve+contain it under the configured base.

### M-3 (MEDIUM) — JSONL ledgers have no tamper-evident chain and silently accept malformed/forged records

**Files:** `keel/src/keel/backend_workflows.py:281-317` (`_read_jsonl`, `_append_jsonl`).
**Repro:** `probe_ledger.py`.

```
records: 12 sequences: [1..12]  duplicate sequences? False
after tamper: records: 13 forged accepted? True
fields: ['at', 'payload', 'record_id', 'sequence', 'writer']   # no hash/prev_hash
```

**Analysis:** Cross-process concurrent append is sound (12 real processes produced
12 unique sequences), but records carry only `sequence`, `record_id`, `at`, no
cryptographic link. An appended forged record (`record_id="forged"`) is accepted as
authoritative evidence; a truncated/malformed line is silently skipped, which can
hide an interrupted write. No `verify_chain` API exists for approval/delegation/MCP
ledgers. Audit records that gate approval replay/consume can therefore be edited
without detection.

**Fix:** Add `prev_hash`/`hash` (HMAC with a server-held key) to each record, verify
the chain on read, fail closed on a gap/bad hash, and quarantine (rather than
silently skip) malformed tail records with an explicit `integrity_error`.

---

## LOW / informational findings

- **L-1 — Token accepted in URL query string.** `webapp.py:272-277` (`path_token`),
  `:262`. `?t=<token>` authenticates every GET (and would work on POST). Tokens in
  URLs leak via history, Referer and logs. Prefer `X-Keel-Token` / HttpOnly cookie
  only; keep query-token as an explicitly deprecated compatibility mode.
- **L-2 — Approval CSRF guard is caller-controlled.** `backend_workflows.py:762-769`:
  `check_csrf_origin()` runs only when the *caller* supplies both `headers` and
  `expected_origin` in `params`; omitting them skips the guard. Transport-level
  Origin checking in `webapp.py:574` currently compensates, so this is defence-in-
  depth, not an exploitable CSRF on its own.
- **L-3 — Approval seal key is a single fragile shared secret.** `backend_workflows.py:693-723`:
  truncating `approval.seal.key` (`probe_misc.py`) makes all outstanding sealed
  tokens fail integrity verification (`invalid_token`) — a local DoS / mass
  revocation vector for anyone with state-dir access. The O_EXCL create → write
  window is also not fsync'd. Write atomically via temp file + `os.replace`, and
  version keys so old tokens can be validated during rotation.
- **L-4 — Outgoing webhook delivery has no SSRF guard.** `webhooks.py:173-197`:
  `deliver()` only checks the scheme; with `allow_http=True` it will POST to
  `http://169.254.169.254/...`. Apply the same validated-IP connection strategy
  as H-1/H-2, or require an explicit `KEEL_EGRESS_ALLOWLIST` match.
- **L-5 — Prose multi-word secrets not redacted.** `redaction.py:61-72`:
  `redact_text("The secret is purple monkey dishwasher 4242")` is unchanged.
  Assignment-style and Bearer forms *are* correctly redacted. Document this
  limitation or add an opt-in high-recall mode for DLP-only contexts.
- **L-6 — `kill-switch` returns the new token in the JSON body but does not set a
  fresh `keel_token` cookie** (`webapp.py:722-727`). The browser keeps the revoked
  cookie and receives 403 until reloaded with the new `?t=` URL. Functional
  self-lockout rather than a privilege issue.

---

## Controls verified as effective (real probes)

| Area | Probe | Result |
|---|---|---|
| Unauthenticated webapp + fleet endpoints | `probe_webapp.py` #1, #7, #11, #13 | 403 for `/api/health`, `/`, v2 session create, cross-origin POST without token |
| Token auth (header, query, cookie) | `probe_webapp.py` #2/#3 | 200 only with correct token; `compare_digest` used |
| Cross-Origin POST rejection | `probe_webapp.py` #8 vs #9 | `Origin: http://evil.example` → 403; same-origin → 200 |
| Capability confirm gate | `probe_webapp.py` #6 | mutating capability without `confirm:true` → 409 |
| Workflow confirm gate | `probe_webapp.py` #4 | `confirm` must be literal boolean `true` |
| Backend workflow end-to-end | `probe_webapp.py` #5 | approval request→resolve→replay→revoke all correct |
| Approval single-use, 8 real processes | `probe_approval_race.py` | exactly **1** success, 7 `replay_denied` |
| Approval possession | `probe_approval_extra.py` | wrong/empty token → `invalid_token`/`missing_token` (403) |
| Approval TTL bounds | `probe_approval_race.py` | 0, -1, 86401, `true` → `bad_ttl`; ttl=1 expired → denied |
| Revocation | `probe_approval_race.py` | post-revoke resolve → `revoked` (403) |
| Replay from serialized grant | `e6_x5_x6_backend.py:1251-1292` | `_GRANT_STATES` authoritative; copied dataclass cannot re-spend |
| Cross-process ledger append | `probe_ledger.py` | 12/12 records, unique sequences, no loss |
| Dispatcher allowlist | `backend_hub.py:998-1034` | 129 dispatches, all pure/deterministic; no caller command executed |
| MCP workflow dry-run | `backend_workflows.py:1163-1199` | caller `server_config.command` never executed |
| Webhook signature/replay/timestamp | `webhooks.py:126-170` | HMAC constant-time, ts window, nonce cache required |
| Core redaction vocabulary | `probe_redaction.py` | API keys, Bearer, JWT, GitHub, Slack, PEM all redacted |

---

## Release recommendation

**BLOCK.** H-1 and H-2 make the `web_fetch` SSRF protection ineffective against any
hostile URL/redirect; H-3 breaks the non-configurable Tier-2 filesystem envelope
that the security model relies on. All three are reachable from the authenticated
web/CLI agent surface and have direct confidentiality impact. Remediate H-1..H-3,
add the suggested regression tests, and re-review before promotion.
