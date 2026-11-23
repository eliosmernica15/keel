# Master Plan v6 - Security Contracts Evidence (W7.x P0, Agent A5)

- **Branch:** `agent/a5-security`
- **Baseline:** `9201f2a` (Mark W3/D2/Y1 batch (44 P0 features) verified; regenerate all artifacts)
- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a5-security`
- **Scope:** all 12 `W7.x` P0 `not_started` rows in the 865-row `PLAN-INDEX.json` registry.
- **Files owned (created only):** `keel/src/keel/security_contracts.py`,
  `keel/tests/test_security_contracts.py`, this evidence file.
- **Constraints honored:** stdlib only; pure functions and in-memory/temp-file
  logic; **no network calls, no subprocesses, no third-party crypto package**.
  No existing source file, test or registry artifact was edited. `git status`
  lists only the three files above.

## 1. IDs implemented

| ID | Registry feature | Contract / public API | Key tests |
|---|---|---|---|
| W7.1 | Explicit trust boundary list | `TrustRole`, `TrustBoundary`, `TRUST_BOUNDARIES`, `TRUST_MODEL`, `render_trust_model()` | `test_w71_*` |
| W7.3 | AES-256-GCM sealed secrets + session cookie | `SealedSecret`, `aes_gcm_seal`, `aes_gcm_open`, `seal_secret`, `open_secret`, `SessionCookiePolicy`, `seal_session_cookie`, `open_session_cookie`, `session_cookie_header` | `test_w73_*` |
| W7.4 | API keys: prefixed token, SHA-256 store, rate limit, idempotency | `issue_api_key`, `hash_api_key`, `verify_api_key`, `ApiKeyStore`, `ApiKeyDecision` | `test_w74_*` |
| W7.5 | Staged secret files, never argv | `stage_secrets`, `consume_staged_secrets`, `build_setup_script`, `assert_no_secrets_in_argv`, `StagedSecretPlan` | `test_w75_*` |
| W7.6 | Log redaction + keyed identifier hashes | `LogRedactor`, `NoHashKeyError` | `test_w76_*` |
| W7.8 | Pairing rate limits, trusted proxy, relative return paths | `client_address_from_headers`, `safe_return_path`, `PairingRateLimiter` | `test_w78_*` |
| W7.10 | SSRF-safe fetch details | `validate_fetch_url`, `validate_redirect_chain`, `parse_redirect_location`, `validate_request_headers`, `assert_address_allowed`, `classify_address`, `stream_limited`, `redact_url`, `FetchPlan` | `test_w710_*` |
| W7.13 | Security headers for served UI | `build_security_headers`, `build_csp`, `assert_strong_csp`, `security_headers_for_url` | `test_w713_*` |
| W7.14 | Rendering safety | `render_safe_markdown`, `SafeMarkdownRenderer`, `validate_link_url`, `sandboxed_iframe_attrs`, `render_sandboxed_iframe`, `sandbox_headers_for_content_type`, `assert_no_dangerous_html_api` | `test_w714_*` |
| W7.16 | Safe publish path selector | `select_publish_files`, `build_publish_manifest`, `PublishFile`, `PublishManifest`, `SafePathError` | `test_w716_*` |
| W7.17 | Inbound channel rules | `InboundChannelVerifier`, `default_channel_rules`, `admit_channel_message`, `is_clean_email_body`, `ChannelRule` | `test_w717_*` |
| W7.19 | Honest known limitations | `KNOWN_LIMITATIONS`, `render_known_limits_page` | `test_registry_ids_are_all_covered` |

**All 12 eligible IDs implemented. 126 tests collected: 125 passed, 1
environment-gated skip (real `os.symlink` creation requires a privilege this
Windows host does not grant; symlink rejection is still covered by injected
`is_symlink` tests).**

Command (exact contract from the task):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_security_contracts.py']))"
```

Result: `125 passed, 1 skipped in 1.01s`.

## 2. Security invariants pinned by tests

### W7.1 - trust boundaries
Five typed roles (`CLIENT`, `DAEMON`, `AGENT`, `HOST_API`, `THIRD_PARTY`) and four
explicit boundary records: client->daemon (client untrusted, no secrets),
daemon->agent (daemon is sole secret holder; restricted agent env),
agent->host API (privileged, daemon-mediated), daemon->third party (untrusted
network). The same data feeds the private security model and the in-app
"What Keel protects and what it cannot" page.

### W7.10 - SSRF
- Only `http`/`https`; URL userinfo and `//`-style credential smuggling are
  rejected; errors use `redact_url()` (scheme + host + port only).
- DNS-resolve-then-pin: **all** returned addresses are classified before the
  first one is pinned into `FetchPlan.connection_target`; the original host is
  kept in `host_header` / `tls_server_name` so Host and SNI stay correct.
- IPv4 private/loopback/link-local/metadata/CGNAT/documentation ranges,
  IPv6 loopback/ULA/link-local/documentation, and IPv4-mapped (`::ffff:`),
  6to4 (`2002:`), IPv4-compatible (`::x.x.x.x`) and NAT64 (`64:ff9b::`) forms
  are rejected. Metadata (`169.254.169.254`, `fd00:ec2::254`,
  `100.100.100.200`) is rejected even when a broader link-local network is
  explicitly allowed; exceptions are opt-in only.
- Redirects are resolved and re-validated hop by hop: scheme downgrade, loops,
  malformed/CRLF `Location`, credentials, unsafe addresses and >5 hops fail.
- Request headers reject CRLF/NUL injection and credential/Host overrides
  without echoing values. Time and size caps live in the plan, and
  `stream_limited()` enforces the body cap on streamed chunks (not just
  `Content-Length`).

### W7.13 - headers
CSP has `default-src 'self'`, script/style without `unsafe-eval` or
`unsafe-inline`, `object-src 'none'`, `frame-ancestors 'none'`; `X-Frame-Options:
DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
COOP/CORP same-origin, and a permissions policy with `microphone=(self)` and
every other sensitive sensor empty. HSTS is emitted **only** for HTTPS.
Custom headers cannot override security headers, set cookies, or carry token
patterns / caller-declared secret values; error messages omit the value.

### W7.14 - rendering
The Markdown seam escapes every byte not in a small explicit token set;
fenced code is escaped too. Links allow only `http`, `https`, `mailto`;
`javascript:`, `data:`, `vbscript:`, `file:`, protocol-relative and NUL-padded
variants become inert spans. External images are **not** auto-loaded by
default (relative images are allowed; `data:` images never are). Inline
HTML/SVG/XML get a `sandbox` CSP with `script-src 'none'`, and generated-site
previews render as an iframe with `sandbox="allow-scripts"` (never
`allow-same-origin`), `referrerpolicy="no-referrer"` and a CSP attribute.
`assert_no_dangerous_html_api()` rejects `dangerouslySetInnerHTML` and related
raw-HTML sinks in templates.

### W7.16 - publishing
Candidates must be relative, contain no `..` or dot-prefixed component, be
regular files, and have no symlink in any path component (root included);
canonical-path containment uses `normcase` + `commonpath` for Windows
case-insensitivity. Enumeration prunes hidden directories and symlinked
entries. The manifest is sorted, timestamp-free, digest-addressed and contains
only relative paths, sizes and SHA-256 values (no absolute host paths).

### W7.17 - inbound channels
`hmac.compare_digest` on raw HMAC-SHA256 bytes; 300-second symmetric freshness
window; bounded LRU nonce cache keyed by `(channel, sender, nonce)`; empty or
missing secrets fail closed before any other check; sender allowlists are
mandatory. Extra channel rules implement owner-only clean email, pairing
allowlists, and confirmation codes for voice/phone-initiated work.

### W7.3 / W7.4 / W7.5 / W7.6 / W7.8 / W7.19
Pure-stdlib AES-256-GCM (verified against NIST AES-256 GCM known-answer
vectors) with a fresh 12-byte IV and 16-byte tag per value, AAD-bound session
cookies with 30-day `Max-Age`, `HttpOnly`, `SameSite=Lax` and HTTPS-only
`Secure`, plus revocation and expiry checks. API keys are prefixed random
tokens stored only as SHA-256 with a constant-time verifier, per-key sliding
rate limits and per-user idempotency keys. Secrets are staged in a
restricted file whose path alone reaches the child; argv is checked for
secret material and the setup script deletes the file in `finally`. Logs get
pattern/explicit-value redaction and keyed BLAKE2b pseudonyms. Sign-in address
detection honors only configured trusted-proxy hops, pairing is rate-limited
per address and globally, and return paths must be same-origin relative.
Known limitations are recorded honestly, including client-side watch-only in
openman and prompt-injection risk.

## 3. Integration seams (deliberately NOT wired in)

`INTEGRATION_SEAMS` in the module is the hand-off list for the lead:

1. About/security pages render `render_trust_model()` and
   `render_known_limits_page()`; ship the same text as `security-model.md`.
2. `keel web` merges `build_security_headers()` into every UI response;
   session issuance/verification uses the sealed-cookie helpers and
   `session_cookie_header()`.
3. Fetch adapters call `validate_fetch_url()` before dialing and
   `validate_redirect_chain()` before following each redirect; connect to the
   pinned address with the preserved Host/SNI and pipe the response through
   `stream_limited()`. The resolver is injectable for DNS-policy tests.
4. Markdown/HTML rendering routes through `render_safe_markdown()` and
   `render_sandboxed_iframe()`; generated-site previews never get
   `allow-same-origin`.
5. The sites exporter drives `build_publish_manifest()` and copies only the
   returned `PublishFile.source` paths.
6. Webhook/channel handlers call `InboundChannelVerifier.verify()` and
   `admit_channel_message()` before any work is started.
7. API token, pairing, child-process and logging adapters adopt the W7.4 /
   W7.8 / W7.5 / W7.6 helpers at their respective edges.

The module imports no live Keel module, so none of these seams changes existing
runtime behavior until a caller explicitly adopts it.

## 4. Coverage and limitations

- Test file: `keel/tests/test_security_contracts.py` (126 tests, 125 pass, 1
  skip). Coverage is parametrized across private IP variants, redirect chains,
  malformed headers, HTML injection, dangerous URL schemes, hidden/symlinked
  publish paths, replay/tamper/expiry signatures and missing secrets.
- Windows cannot create symlinks without extra privilege, so the real-symlink
  test is environment-gated; the injectable `is_symlink` seam exercises the
  same rejection path unconditionally.
- The AES-GCM implementation is a reference-grade stdlib implementation for
  contract verification and small values. Production deployments may substitute
  a vetted platform AEAD behind the same `SealedSecret` seam; the wire format
  (version || IV || tag || ciphertext) and NIST vectors stay identical.
