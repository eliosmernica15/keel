# Independent backend review — Group 4 (e5 / w4 / w7-x1-y5-d1 / small-groups / e6-x5-x6)

**Reviewer:** independent subagent (did not implement any of the code)
**Branch reviewed:** `integration/v6-backend-complete` (HEAD `1ffffb2`), work committed on `agent/review-g4`
**Date:** 2026-11-24
**Method:** static review of all 10 files + per-module targeted test runs only (no full suite, per instruction).
All five target test files pass: `e5 77`, `w4 54`, `w7_x1_y5_d1 32`, `small_groups 56`, `e6_x5_x6 65` (**284 tests total, 0 failures**).

## Cross-cutting findings

1. **All five modules are fully additive; none is imported by the live Keel runtime.** `grep` across the
   worktree finds references only in the modules' own tests, the five evidence notes and
   `backend-module-id-coverage.json`. No `from keel...` / `import keel...` appears in any of the five
   backend sources (the only two backend modules that import runtime code are `e3_backend.py:94` and
   `x8_backend.py:39`, outside this review). Every feature registry (`FEATURE_IMPLEMENTATIONS`,
   `OWNER_GATED`, etc.) is a local mapping. **Verdict impact:** genuine libraries, but zero runtime
   wiring — integration remains a lead decision, exactly as the E6 docstring (`e6_x5_x6_backend.py:3-6`)
   admits. This is not a code defect per se but the single most important architectural fact.

2. **A recurring redaction weakness**: four modules redact `key=value` with a `\S+` value pattern
   (`e5_backend.py:997-1000`, `w4_backend.py:126-134`, `w7_x1_y5_d1_backend.py:755-760`; small-groups
   `VcrRecorder.scrub` at `small_groups_backend.py:1162-1175` scrubs whole string values, so it is not
   affected). Observed: `redact_diagnostics("token=super secret value here")` →
   `"token=[REDACTED] secret value here"`. Only the first word is removed. Same for
   `redact_text("api_key=super secret value here")` → `"api_key=[REDACTED] secret value here"`.

3. **Test style is substantive, not existence-only**, with two narrow exceptions:
   `test_w7...py:527-540` asserts feature-ID strings appear in source/test text (a coverage guard), and
   `test_e6...py:836-848` only AST-checks banned imports. Everything else asserts concrete outputs,
   typed errors, state transitions, crypto round-trips, persistence, and (in W7) a real 50-thread
   concurrency test. Per-module detail below.

---

## 1. `e5_backend.py` + `test_e5_backend.py`

**1. Real observable behavior vs descriptors.** Mixed but substantial. Genuine algorithms/state machines:
`release_identity`/`assert_release_identity` (186-223) validate version identity and forbid split fields;
`seed_manifest` (403-435) performs deterministic name-hash sharding (SHA-256, 16 buckets, sorted members)
and `assert_seed_manifest` (438-491) re-derives the whole manifest, checks ordering, duplicates and exact
package coverage; `ActivationJournal` + `plan_activation`/`execute_activation`/`recover_activation`
(288-357) is a real staged→committed/rolled_back state machine with disk-aware recovery;
`UpdateCheckCoordinator` (583-608), `locale_payload` fallback resolution (698-737),
`effective_dev_config` (809-820), `validate_release_prerequisites` (845-874) and `redact_diagnostics`
(991-1001) all compute real results. Pure descriptor builders exist too (`bundled_runtime_descriptor`
230-246, `activation_descriptor` 273-285, `plugin_manager_surface` 650-661, `signing_plan` 950-966,
`linux_release_targets` 1018-1025, `known_limitations_section` 1067-1072) — roughly a quarter of the
public surface. Not descriptor-only.

**2. Tests assert behavior.** Yes — e.g. `test_e5_5_health_check_probes_staged_profile_and_gates_swap`
(125-137) asserts the injected callable received the staged name; `test_e5_6_seed_manifest_is_deterministic...`
(188-198) asserts byte-identical manifests under reversed input; `test_e5_6_adversarial_manifest_tampering_rejected`
(212-229) asserts typed errors and exact expected-package coverage; `test_e5_7_install_plan_verifies_before_stopping_backend`
(308-320) asserts call ordering. 77 passing tests.

**3. Real defects.**
- **MEDIUM** — `redact_diagnostics` (`e5_backend.py:997-1000`): `\S+` truncates multi-word secret values;
  probe output above. Partial secret leak into diagnostics.
- **LOW** — `UpdateCheckCoordinator` (`e5_backend.py:583-608`): no lock; `request_check()` reports
  `{"waited": True}` but does not actually block, and concurrent `request_check`/`finish` can both start.
  Race under real threaded use.
- **LOW** — `verify_seed_shard` (`e5_backend.py:494-496`): `expected_digest` is not validated as SHA-256;
  a malformed expected value silently yields `False` rather than an error.

**4. Runtime wiring.** Fully additive; imports only `hashlib`, `re`, `dataclasses`, `typing`, `urllib.parse`.

**5. Verdict: GENUINE_BACKEND** (pure offline policy/state-machine engine; several descriptor helpers).
Top 3: (1) MEDIUM incomplete secret redaction `e5_backend.py:997`; (2) LOW racy/“waited” coordinator
`e5_backend.py:583-608`; (3) LOW unvalidated expected digest `e5_backend.py:494`.

---

## 2. `w4_backend.py` + `test_w4_backend.py`

**1. Real observable behavior vs descriptors.** Strongest of the batch. Real validators and algorithms:
`normalize_server_config` (236-299) with URL/scheme checks and shlex command parsing;
`merge_config_layers` (352-389) with whole-object precedence and dropped-field warnings;
`resolve_timeouts`/`call_progress` (421-470); `select_protocol` (497-525);
`select_client_registration` (569-644) with pre-registered→CIMD→DCR precedence;
`build_authorization_url` (716-741) computes a real SHA-256 PKCE S256 challenge;
`parse_pasted_callback` (683-713) uses `hmac.compare_digest` for state and host/redirect checks;
`normalize_tool_name` (758-789) deterministic SHA-1 collision suffixes; `ConnectionPool` (845-908)
reference counting; `render_prompt_command` (965-977); `build_system_prompt` (1070-1104) XML-escapes
tainted server instructions and omits fully-denied servers; `answer_elicitation` (1188-1246) full
form validator; `dispatch_mcp_command` (1513-1603) a real CLI parser/dispatcher. Descriptor helpers
(`feature_manifest`, `plugin_manager_surface`, `mcps_panel`) are a small minority.

**2. Tests assert behavior.** Yes: PKCE challenge/state asserted from the generated URL (test 148-165),
header-key server and logout config immutability (182-193), pool share/close lifecycle (408-421),
collision determinism (438-447), injection escaping (500-526), form validation (547-571), and a
“bad commands fail without crashing” list (196-207) — which unfortunately omits bare `auth`/`logout`.

**3. Real defects.**
- **MEDIUM (confirmed by probe)** — `dispatch_mcp_command` (`w4_backend.py:1531`):
  `name = parsed["positional"][0]` is unguarded. `_parse_cli` only enforces a positional for `add`
  (1496-1497), so `dispatch_mcp_command(["auth"], store)` and `["logout"]` (also with flags, e.g.
  `["auth","--client-id","x"]`) raise **unhandled `IndexError`**. The `except W4Error` at 1602 cannot
  catch it — a CLI crash reachable from user input.
- **MEDIUM** — `redact_text` (`w4_backend.py:126-134`): same multi-word leak as above; probe confirmed.
- **LOW-MEDIUM** — `answer_elicitation` (`w4_backend.py:1220-1242`): `int(spec["maxLength"])`,
  `int(spec["minLength"])` and `value < spec["minimum"]` assume a well-formed schema. Probe: a schema
  with `maxLength: "oops"` raises unhandled `ValueError`. Malformed server-supplied schemas crash
  instead of producing an `invalid` result.
- **LOW** — `ConnectionPool` (845-908) has no lock; concurrent `acquire`/`release` can interleave
  `_counter`, `_leases` and `owners` recomputation. `McpConfigStore.add_server` (1406) also keys
  `self._documents[scope]` without scope validation → `KeyError`.

**4. Runtime wiring.** Fully additive; stdlib only. The docstring even notes W4.3 already lives in
`keel.product_contracts` and is deliberately not reimplemented (26-27).

**5. Verdict: GENUINE_BACKEND.** Top 3: (1) MEDIUM unhandled `IndexError` on `mcp auth|logout` without a
name, `w4_backend.py:1531`; (2) MEDIUM secret leak in `redact_text`, `w4_backend.py:126-134`;
(3) LOW-MEDIUM malformed elicitation schema raises raw `ValueError`, `w4_backend.py:1220-1242`.

---

## 3. `w7_x1_y5_d1_backend.py` + `test_w7_x1_y5_d1_backend.py`

**1. Real observable behavior vs descriptors.** Genuine: HMAC seal/unseal with expiry and constant-time
compare (`seal_value`/`unseal_value` 466-491); `BrowserBoundSignIn` (507-553) with state machine,
fingerprint binding and one-time consumption; `check_csrf_origin` (559-579); `StreamingBodyLimiter`/
`bounded_multipart`/`cap_recording` (589-637); `AtomicSpendLedger` (721-749) uses integer micro-units
and a `threading.Lock` for check-then-increment; `public_share_view`/`render_share_html` (676-711)
redact and HTML-escape; `PluginTransaction.run` (407-423) applies steps with best-effort LIFO rollback
and real `mkdir`; `plan_tool_batches` (905-941) is a topological sort with cycle detection;
`PartialJSONParser` (857-891); `WebhookSubscriptionManager` (1094-1137) and `ChatIdCache` (1183-1209)
persist via atomic writes and survive reinstantiation. Some descriptor/report helpers
(`live_view_headers`, `deployment_hygiene_report`, `support_policy`, TROUBLESHOOTING) exist but do not
dominate.

**2. Tests assert behavior.** Yes, including the only real concurrency test in the batch
(`test_w7_18_atomic_spend_ledger`, 259-287: 50 threads, exactly 10 charges succeed), HMAC tamper/expiry
(158-183), persistence across instances (440-463), rollback trace (119-139), topo ordering and cycle
errors (354-371). The only existence-style test is the feature-ID coverage guard (527-540).

**3. Real defects.**
- **LOW-MEDIUM** — `_atomic_write` (`w7_x1_y5_d1_backend.py:73-77`) uses a fixed `<name>.tmp` file and
  no lock. `WebhookSubscriptionManager` and `ChatIdCache` are read-modify-write without locking
  (1100-1137, 1189-1196): concurrent subscribers can lose subscriptions or interleave temp-file
  contents. Paths (`WebhookSubscriptionManager.__init__`, `ChatIdCache.__init__`, `log_error_detail`
  650-658) are caller-controlled with no traversal validation — arbitrary file write if ever fed
  untrusted input (today: operator-supplied credentials dir).
- **LOW-MEDIUM** — `redact_keys_for_display` (`w7_x1_y5_d1_backend.py:755-760`) shares the `\S+`
  truncation; probe: `"token: hello world and more"` → `"token=[REDACTED] world and more"`.
- **LOW** — `BrowserBoundSignIn` (512-539) `_states` and `_consumed` grow without bound (memory growth
  in a long-running daemon); `unseal_value` line 489 `int(payload.get("exp", 0))` can raise on a
  signed-but-malformed payload.

**4. Runtime wiring.** Fully additive; imports only stdlib (`pathlib`, `threading`, `secrets`, etc.).
Note this is one of only two modules in scope that performs real filesystem writes (the other is
small-groups).

**5. Verdict: GENUINE_BACKEND.** Top 3: (1) LOW-MEDIUM unlocked fixed-temp atomic write / lost-update
race and unvalidated caller paths, `w7_x1_y5_d1_backend.py:73-77,1100-1137`; (2) LOW-MEDIUM partial
redaction `w7_x1_y5_d1_backend.py:755-760`; (3) LOW unbounded sign-in state/consumed-set
`w7_x1_y5_d1_backend.py:512-539`.

---

## 4. `small_groups_backend.py` + `test_small_groups_backend.py`

**1. Real observable behavior vs descriptors.** Genuine, with the broadest state-machine coverage:
`BargeInController` (39-90) full/half duplex transitions; `WakeWordController` (120-178) license gate
and hard mute; `stream_tts_sentences` (96-117) sentence segmentation; `VideoTooling.subtitles_from_stt`
(242-257) real SRT generation; `HookRunner` (508-571) waterfall/serial/parallel dispatch with
contract enforcement; `JsonlPersistence` (388-429) real JSONL create/append/open/stat/export with
session-id validation; `ProjectionRegistry` (338-370) event folding with deep-copy snapshots;
`RequestSeriesLogger` (592-628); `McpPanelService` (866-933) and `ApprovalService` (936-981) real
approval state; `VcrRecorder` (1149-1204) scrubs and replays cassettes; `CoverageGate`/`BenchmarkGate`/
`McpConformanceRunner`/`SoakMonitor` implement real gate math; `DecisionLog` (1797-1836) persists and
deduplicates decisions. `OWNER_GATED` (1969-1979) is an honest, deliberate non-implementation of Y6.4.

**2. Tests assert behavior.** Yes: 54 feature tests plus registry/owner-gate checks, with real outputs
and transitions asserted (e.g. hook waterfall short-circuit 182-208, JSONL persistence 251-263,
SRT timestamps 141-153, subprocess smoke with a real generated script 348-363, secret scrubbing
468-477).

**3. Real defects.**
- **LOW-MEDIUM** — `CoverageGate.evaluate` (`small_groups_backend.py:701-725`): a report with zero
  files yields `percent = 100.0`, `dead_code_candidates = []`, `passed = True` (probe confirmed).
  An empty/malformed coverage report vacuously passes the gate — a gate-integrity weakness.
- **LOW** — `built_entrypoint_smoke` (`small_groups_backend.py:636-647`) calls `subprocess.run` on a
  caller-supplied argv list (no `shell=True`, so no shell injection). It is an intentional test helper
  but is arbitrary code execution if ever exposed to untrusted input — the only `subprocess` import in
  the five modules.
- **LOW** — caller-controlled file paths with no validation/locking in `JsonlPersistence.export` (425),
  `DecisionLog._save` (1829-1831), `CommandTemplateStore.store` (1673-1677),
  `ScopeCreepGuard.capture` (1868-1875), `MemoryLedger.write` (1435-1442) → arbitrary overwrite and
  lost-update races. `JsonlPersistence._path` (395-398) rejects `/`, `\`, `.`/`..` but not `:` (NTFS
  alternate data streams) or NUL. `ApprovalService.decide` (956) raises `KeyError` on an unknown
  request id; `BenchmarkGate.evaluate` (766) raises `KeyError` on an unrecorded name.

**4. Runtime wiring.** Fully additive; stdlib only (plus `subprocess` as above).

**5. Verdict: GENUINE_BACKEND.** Top 3: (1) LOW-MEDIUM vacuous pass on empty coverage report,
`small_groups_backend.py:717-725`; (2) LOW unvalidated/unlocked caller-supplied file writes,
`small_groups_backend.py:1829-1831,425-429`; (3) LOW unguarded `KeyError` paths and Windows-unsafe
session ids, `small_groups_backend.py:956,395-398`.

---

## 5. `e6_x5_x6_backend.py` + `test_e6_x5_x6_backend.py`

**1. Real observable behavior vs descriptors.** Genuine offline engines: `CredentialEditor`
(367-445) staged edit/removal state machine with irreversible-deletion warning; `parse_models_response`
(609-647) tolerant two-format parser with dedup; `ModelPicker` (698-775) default/session/reorder/block
state; `HotReloadAdapter` (912-933) digest-versioned re-read; `classification_from_labels`/`egress_allowed`
(1111-1136) fail-closed labels; `issue_grant`/`consume_grant` (1167-1202); `CapabilityTokenIssuer`
(1264-1325) scoped, revocable tokens with append-only audit log; `resolve_profile`/`operation_allowed`
(1424-1439); `seal_export`/`verify_import` (1493-1524) HMAC signature + toy XOR stream (doc honestly
says it is not production encryption); `detect_secret_paste` (1675-1678); `plugin_scaffold`/SDK generators
(1699-1713, 1839-1884) emit deterministic code; `validate_event`/`SubscriptionRegistry.dispatch`
(2038-2078) real schema validation and type-filtered dispatch; `resolve_layers` (2119-2133) precedence
with provenance; `diff_against_defaults`/`reset_section`/`import_settings` (2174-2214). Descriptor-only
parts (catalog constants, `FEATURE_LIFECYCLES`) are supporting data.

**2. Tests assert behavior.** Yes: 65 tests asserting state transitions, typed errors and deterministic
output (credential seams 119-179, discovery parse/tick/save 258-289, HMAC tamper/version tests 578-597,
token revoke/forgery/audit 496-519, event dispatch 762-771, settings diff/reset 799-814).

**3. Real defects.**
- **MEDIUM (confirmed by probe)** — `consume_grant` (`e6_x5_x6_backend.py:1193-1202`) documents
  “A JIT grant is single-use” but never marks the grant consumed (the frozen `TimeBoxedGrant.consumed`
  field stays `False`). Probe: `consume_grant(g, 100)` and `consume_grant(g, 101)` both return
  `granted: True`; `g.consumed == False`. **The test at `test_e6_x5_x6_backend.py:482-488` masks this**
  by manually doing `replace(grant, consumed=True)` instead of calling `consume_grant` twice. A
  just-in-time permission can be replayed indefinitely within its TTL.
- **LOW** — `CapabilityTokenIssuer` (1264-1325) has no lock; concurrent `issue`/`verify`/`revoke` can
  interleave `_seq` and the audit log (e.g. duplicate sequence numbers).
- **LOW** — `parse_semver` (`e6_x5_x6_backend.py:960-971`) accepts negative components
  (`parse_version("1.-2")` → `ApiVersion(1, -2, 0)`); X5.10's passphrase→HMAC key is a single unsalted
  SHA-256 (`_signature`, 1487-1490), so offline guessing is cheap — mitigated by the module's explicit
  “not production encryption” disclaimer (56-59, 1494-1498).

**4. Runtime wiring.** Fully additive. Its test `test_already_implemented_p0_symbols_still_import`
(`test_e6_x5_x6_backend.py:857-872`) imports real `keel.*` modules only to assert they still exist — that
is a test-side check, not backend integration. Docstring states integration is a separate lead decision.

**5. Verdict: GENUINE_BACKEND** (pure/offline engine; no I/O by design). Top 3: (1) MEDIUM JIT grants
not actually single-use, `e6_x5_x6_backend.py:1193-1202` + masking test `test_e6_x5_x6_backend.py:482-488`;
(2) LOW unlocked token issuer/audit log, `e6_x5_x6_backend.py:1264-1325`; (3) LOW permissive semver
and weak passphrase KDF, `e6_x5_x6_backend.py:960-971,1487-1490`.

---

## Summary table

| Module | Verdict | Tests | Top severity |
|---|---|---|---|
| e5_backend | GENUINE_BACKEND (pure policy engine) | 77 pass | MEDIUM redaction leak |
| w4_backend | GENUINE_BACKEND | 54 pass | MEDIUM `IndexError` on bare `auth`/`logout` |
| w7_x1_y5_d1_backend | GENUINE_BACKEND | 32 pass | LOW-MEDIUM atomic-write race / path validation |
| small_groups_backend | GENUINE_BACKEND | 56 pass | LOW-MEDIUM vacuous coverage gate pass |
| e6_x5_x6_backend | GENUINE_BACKEND (pure/offline engine) | 65 pass | MEDIUM JIT grant replay |

**Overall:** none of the five is a descriptor-only stub; all contain real, tested behavior. The most
actionable fixes are the W4 CLI crash, the E6 JIT-grant single-use invariant (and its misleading test),
and the shared `\S+` redaction pattern. Architecturally, all five remain unwired additive libraries.
