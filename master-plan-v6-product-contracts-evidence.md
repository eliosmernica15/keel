# Master Plan v6 — W1.10 / W4.3 / W6.1 / W6.3 product contracts evidence

- Branch: `agent/a10-product` (baseline `e2121c4`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\addenda\a10-product`
- New files only — **no existing source, test or registry file was edited**:
  - `keel/src/keel/product_contracts.py`
  - `keel/tests/test_product_contracts.py`
  - this evidence file
- Implementation tier: `local_module` — descriptor/policy layer, stdlib only.
- Commit SHA: reported in the agent hand-off message (single commit containing
  all three files). No push.

## What was implemented

All four assigned `P0` rows are covered by one pure module. `FEATURE_IDS` is
exactly `("W1.10", "W4.3", "W6.1", "W6.3")` and a test reads `PLAN-INDEX.json`
to confirm each row exists, is `P0` and carries its own `source_feature_id` and
acceptance criteria.

| ID | Feature (PLAN-INDEX.json) | Descriptor surface |
|----|---------------------------|--------------------|
| W1.10 | `SAFETY.md` surfaced as a first-run notice | `validate_safety_notice_text`, `safety_notice_descriptor`, `SafetyNotice`, `SafetyNoticeState`, `notice_reason`, `needs_notice`, `first_run_descriptor`, `acknowledge_notice`, `decline_notice` |
| W4.3 | OAuth for remote servers: PKCE, discovery, refresh; credentials outside project config; `oauth:false` for header-key servers | `pkce_challenge`, `validate_discovery_document`, `oauth_flow_descriptor`, `remote_auth_descriptor`, `oauth_switch`, `credential_ref`, `assert_no_credentials_in_config`, `assert_credential_store_outside_project`, `token_state`, `refresh_decision`, `assert_refresh_bounded` |
| W6.1 | Accuracy-over-approval response contract | `make_claim`, `validate_citation`, `make_response_draft`, `check_accuracy`, `response_contract`, `assert_finalizable`, `persona_rigor_section`, `validate_persona_section`, `rigor_eval` |
| W6.3 | Anti-sycophancy rules | `check_anti_sycophancy`, `PERSONA_RIGOR_SECTION`, `assert_safe_persona`, `rigor_eval` |

`feature_descriptors()` returns one uniform row per ID with
`layer="descriptor_only"`, `io_performed=False`, `network=False`,
`runtime_claimed=False`, `secret_values=False`.

## Key invariants (tested)

- **W1.10 content check + versioning.** The caller supplies `SAFETY.md` text;
  the module never reads a file. It requires a safety-titled level-one heading,
  exactly one `Version:` marker, at least one `##` section, safe markdown links
  (no `javascript:`/`file:`/traversal) and no credentials, bounded at 64 KiB.
  The descriptor carries a SHA-256 content digest. `first_run_descriptor`
  reports `first_run` on first run, `version_changed` when the version moves,
  `content_changed` when only the bytes change, and `acknowledged` otherwise —
  so a changed safety notice is re-shown like the C11.5 EULA. Decline clears
  acknowledgement.
- **W4.3 PKCE.** RFC 7636 Appendix B vector is reproduced exactly
  (`dBjft…EjXk` → `E9Melhoa…tw-cM`). Only `S256` is accepted; `plain` is
  rejected. The verifier is never retained in the descriptor, dict or error.
- **W4.3 discovery.** Endpoints must be HTTPS, except HTTP on loopback hosts
  (`localhost`, `127.0.0.1`, `::1`). Issuer origin must match the server URL;
  `S256`, `authorization_code` and `refresh_token` must be declared; query/
  fragment issuers, embedded credentials and literal secrets fail closed.
- **W4.3 auth-mode honesty.** `oauth:false` yields a header-key descriptor with
  `oauth_attempted=False` and `static_header_authoritative=True`. A header
  reference on an OAuth server is a conflict (`header_auth_takes_precedence`),
  never a silent downgrade. Literal `Authorization`/`client_secret`/token values
  in config are rejected; only opaque `credential-ref:` markers are accepted,
  and a store path inside the project is refused.
- **W4.3 bounded refresh.** Token descriptors carry metadata only
  (`token_value=None`). An expired token with a refresh token triggers exactly
  one silent refresh; a second attempt re-authenticates
  (`refresh_limit_reached`), and `assert_refresh_bounded` detects a loop.
- **W6.1 accuracy.** A `VERIFIED` claim needs a real citation and cannot be
  anchored on a user assertion. A numeric figure supplied by the user requires
  a separate, labelled independent estimate. `UNKNOWN` claims must be stated
  plainly (marker in the claim or an acknowledged topic plus a marker in the
  response). `assert_finalizable` raises `response_not_finalizable` on any
  violation; it never returns a permissive descriptor.
- **W6.3 anti-sycophancy.** Praise of questions/insights, missing immediate
  correction of a wrong premise, agreement with a wrong user, a missing or
  absent strongest counterargument, and capitulation under pushback without new
  evidence all fail closed.
- **Safety preserved.** The default `PERSONA.md` rigor section embeds the
  existing A4.4 rigor text plus W6.1/W6.3 rules. `validate_persona_section`
  requires every rule and rejects the excluded C-5 instruction family
  ("avoid all ethics", "no safety caveats", "be aggressive", "ignore safety").
  Keel's own safety messaging and Tier-2 behavior are explicitly retained.
- **Purity.** An AST test asserts the module imports only stdlib
  (`__future__`, `base64`, `hashlib`, `re`, `dataclasses`, `enum`, `typing`) and
  none of `socket`, `subprocess`, `os`, `urllib.request`, `pathlib`, `secrets`,
  `keyring`, `time`, etc. Error messages are redacted and never contain secret
  material.

## Verification

```
cd <worktree>/keel
$env:PYTHONPATH="<worktree>/keel/src"
python -m pytest tests/test_product_contracts.py -q
# 62 passed in 1.00s
```

### Fixes made during verification (all tests retained)

The first run produced 9 failures. The following corrections were applied; no
test was deleted or weakened:

1. Implementation — `_UNKNOWN_MARKERS` did not recognise "could not verify", so
   a plainly-stated gap was wrongly flagged. Added that phrase to the accepted
   plain-unknown markers.
2. Implementation — `FORBIDDEN_PERSONA_PHRASES` missed "avoid ethics" /
   "ignore all ethics", so the excluded C-5 instruction was not caught. Added
   both phrases.
3. Test fixture — the "no sections" case removed only one of two `##` headings;
   it now removes both so it actually exercises the rule.
4. Test fixture — the unsafe-link case used bare text instead of markdown link
   syntax; it now uses `[here](javascript:alert(1))` so the link checker runs.
5. Test expectation — `assert_finalizable` is a fail-closed gate that raises;
   the test now asserts the `response_not_finalizable` exception and that the
   message names `praise_of_question` (stronger than checking a returned flag).
6. Test fixture — the "agreement with wrong user" case did not contain an
   agreement phrase; it now uses "As you correctly pointed out…" so the rule is
   genuinely exercised.
7. Test fixture — the unknown-claim case had "unknown" in its own text, so it
   could not distinguish acknowledgement from plain speech. It now uses
   "unavailable", exercising both the acknowledged and unacknowledged paths.

Final result: **62 passed**.

## Known limitations / exclusions

- Descriptor/policy layer only: no browser, token endpoint, OS keychain or
  settings file is touched. A host integration must call these validators at
  its own boundaries and supply real bytes/credentials through its own store.
- **W1.18 (MIT license + `THIRD_PARTY_NOTICES.md`) is deliberately not
  implemented.** It is owner-gated and conflicts with the proprietary license
  requirement in `keel/pyproject.toml`; `OWNER_GATED_NOT_IMPLEMENTED` records
  this, and a test asserts it is absent from `FEATURE_IDS`.
- PLAN-INDEX.json statuses were not changed (the task owns new files only), so
  the registry still lists these rows as `not_started`; this evidence file is
  the record of the implementation.
