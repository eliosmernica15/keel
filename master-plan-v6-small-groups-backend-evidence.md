# Master Plan v6 — small-groups backend implementation evidence

- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b3-mixed3`
- **Branch:** `agent/b3-mixed3`
- **Baseline:** `73b2a90` (`Add live backend operation task board: 16 agents across 2 waves`)
- **Scope:** every `not_started` feature ID from groups **X4, D2, E4, W9, X9, W6, W8, W2, W5, X0, X10, W3, Y6** in `PLAN-INDEX.json`.
- **Constraint:** real, deterministic **backend** behaviour only; **standard library only**; no frontend, no network, no owner-gate override.
- **Files owned (exactly three, no others touched):**
  - `keel/src/keel/small_groups_backend.py`
  - `keel/tests/test_small_groups_backend.py`
  - this evidence note.

## 1. Result summary

| Item | Count |
|---|---|
| `not_started` IDs in the 13 groups (baseline) | 55 |
| Implemented with real backend behaviour | **54** |
| Owner-gated, documented only (Y6.4) | 1 |
| Prior P0 rows in these groups, already `verified` (checked, not reimplemented) | 62 |
| Automated tests in `test_small_groups_backend.py` | **56** (54 feature tests + 2 registry/owner-gate tests) |
| Test result | **56 passed, 0 failed** |

The runtime registry `FEATURE_IMPLEMENTATIONS` in `small_groups_backend.py` contains exactly the 54 implemented IDs; `test_registry_covers_every_implemented_non_gated_feature` asserts the per-group counts and callable status, and `test_owner_gated_y6_4_is_documented_not_implemented` asserts Y6.4 is absent from that registry.

## 2. Implemented feature IDs

Each symbol below is exported from `keel.src.keel.small_groups_backend` and carries the plan ID in its docstring. Every ID has a dedicated test.

### X4 — Voice and multimodal extras (7)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| X4.1 | `BargeInController` | Full-duplex speech cancels active TTS at once; weak-hardware half-duplex fallback reports `half_duplex_fallback` instead of interrupting; interruption counter. |
| X4.2 | `stream_tts_sentences` | Splits a live token/chunk stream into complete sentences at each boundary and flushes the trailing fragment. |
| X4.3 | `WakeWordController` | Licence allow-list verification before enable; visible indicator (`off`/`listening`/`muted`); hard mute cannot be overridden by wake-word detection. |
| X4.4 | `LocalVisionTool` | User-installed model registration with mandatory licence display; image-type validation; offline VLM request descriptor (no network). |
| X4.5 | `VideoTooling` | ffmpeg command plans for frame/audio extraction; SRT generation from local STT segments with correct timestamps; user-installed ffmpeg required. |
| X4.6 | `VoiceCommandGrammar` | Command grammar (`approve`, `deny`, `stop everything`) separated from dictation; risky actions require spoken `confirm`. |
| X4.7 | `AudioPrivacyPolicy` | No recording stored by default; visible recording state; per-meeting consent reminder text. |

### D2 — Events, turn flow and session log (6)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| D2.2 | `HookRunner`, `HookContractError` | `waterfall` / `serial` / `parallel` modes; waterfall handlers must call `next()` or declare `short_circuit=True`, otherwise the contract error is raised (the test-failing lint rule). |
| D2.4 | `TurnClaimGate` | Rejected, empty or missing first claim closes the turn with `step=False`; valid claim opens the turn with a step. |
| D2.6 | `RequestSeriesLogger` | Emits `request_header` events on surface/context changes; retries reuse the assembled series and never repeat assembly. |
| D2.12 | `ProjectionRegistry` | Named projections fold committed events into views; `snapshot()` returns a deep copy so clients cannot mutate the private handle. |
| D2.14 | `SessionPersistence`, `JsonlPersistence`, `PersistenceProviderRegistry` | Runtime-checkable provider protocol with `create/open/stat/list/export`; JSONL default provider; swappable provider registry. |
| D2.17 | `TitleProviderRegistry`, `GoalsService` | Exactly one title provider enforced; same-session objective survives `compact` events. |

### E4 — Testing policy (6)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| E4.3 | `CoverageGate` | Computes coverage, lists uncovered files as dead-code candidates, records that line coverage is necessary but never sufficient, and exempts environment-dependent files locally while enforcing them on CI. |
| E4.4 | `BenchmarkGate`, `Budget` | Time/heap/scaling budgets over plain-runtime benchmark results; `diagnostic_only` results are excluded from required PR gates. |
| E4.6 | `FixtureFormatPolicy` | Strips sequence/time envelopes from fixtures, synthesises them deterministically on replay, and preserves released representation for historical fixtures with named format owners. |
| E4.7 | `BrowserSnapshotLane` | Engine matrix (Chromium everywhere, WebKit also for the model picker); CI forces replay-only mode and the plan validator enforces it. |
| E4.13 | `built_entrypoint_smoke`, `assert_missing_config_exits_nonzero` | Runs built entrypoints under the plain runtime through a shared launcher via `subprocess`; asserts a genuinely missing config exits non-zero. |
| E4.14 | `TestResolver` | Resolves a module to source or built origin, rejects ambiguous dual resolution, and provides `assert_source_only` for ordinary tests. |

### W9 — UI/UX additions, backend state/services only (6)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| W9.1 | `McpPanelService` | Per-server state machine (`disconnected`/`connected`/`needs_auth`/`disabled`/`error`), connect/disconnect/authenticate with callback URL, timeout/protocol fields and snapshot. |
| W9.2 | `ApprovalService` | `once` / `always` (editable saved pattern) / `reject` (optional feedback) decisions; rejecting cancels all other pending requests. |
| W9.3 | `normalize_agent_config`, `simulate_permission` | Validates mode, model reference (with variant), step limit, colour, hidden, permission list and subagent allowlist; permission simulator for the editor. |
| W9.4 | `build_palette_entries`, `expand_command_prompt` | Generates palette entries with `$1`/`$ARGUMENTS` hints and previews the expanded prompt before submit. |
| W9.5 | `FirstRunNotice` | First-run detection, safety-notice content, known-limits content and persisted `mark_seen`. |
| W9.6 | `web_server_config` | Rejects non-loopback bind addresses; builds the SSH forwarded-URL hint banner. |

### X9 — Testing and quality (6)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| X9.2 | `VcrRecorder` | Record/replay of provider traffic keyed by method+URL+body, with recursive secret scrubbing (secret keys and token patterns) before persistence. |
| X9.4 | `McpConformanceRunner` | Bundled stdio/HTTP sample servers plus hostile variants; guards for output size, timeout and schema validity produce pass/fail conformance reports. |
| X9.6 | `pseudo_localize`, `rtl_smoke` | Pseudo-localised build strings (accented characters + expansion) and RTL directional-isolation smoke markers. |
| X9.8 | `TokenAccountingCheck` | Estimated vs runtime-reported token usage with relative tolerance and delta reporting. |
| X9.9 | `SoakMonitor` | Long-session samples (events, memory, DB size, frame time) with growth summary and budget checks over thousands of events. |
| X9.10 | `MutationReport` | Mutation scores for the permission gate and command analyzer and a private-dashboard payload. |

### W6 — Persona contract (4)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| W6.2 | `ConfidenceLabeler` | Explicit `high`/`moderate`/`low`/`unknown` labels; factual web claims require an explicit (non-`unknown`) judgment. |
| W6.4 | `ConductorRouter` | One conductor enforced, optional external specialists for multi-file work, one writer per dirty tree, mandatory diff+test verification after a specialist. |
| W6.5 | `choose_tool` | Prefers healthy local desktop tools, browser tools for DOM work, optional accessibility-tree enrichment, PERSONA.md routing hints. |
| W6.6 | `MemoryLedger` | `MEMORY.md`-style ledger; writes require explicit approval and are appended with a date. |

### W8 — Small items from earlier sources (4)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| W8.1 | `AllowlistMatcher` | Exact entries, `@domain` patterns and device-label prefix patterns for the paired-client allowlist. |
| W8.2 | `BlobCaps` | Configurable size caps for recordings and screenshots with accept/reject decisions. |
| W8.3 | `ComputerAccessGuard` | Requested computer IDs checked against the user's own listing; core/home desktop mutation refused. |
| W8.4 | `normalize_question` | opencode `question` and MCP elicitation normalised onto one shared question-card form schema. |

### W2 — Agents (3)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| W2.5 | `apply_agent_fields` | `hidden`/`color`/`disabled` fields; `disabled` removes a built-in at config load; `hidden` documented as visibility-only, not security. |
| W2.7 | `resolve_default_agent`, `SessionAgentPin` | Chain: configured default → `build` → first visible primary-capable; session agent pins survive default changes. |
| W2.10 | `ModelReference` | Parses `provider/model#variant` and the expanded object form; round-trips to string/dict. |

### W5 — Commands (3)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| W5.5 | `resolve_model_precedence` | Command model → command agent's model → session model. |
| W5.6 | `BackgroundCommandRunner` | `subagent: true` child commands report result or failure back to the parent without raising through it. |
| W5.7 | `CommandTemplateStore` | `@path` tokens stay raw in stored templates; attachments come from the composer only; no hidden file reads. |

### X0 — Plan problems fixed before building (3)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| X0.2b | `MilestoneSplitter` | Split map for M11 (code-intel core / engineering tools), M17 (voice / documents / meetings), M22 (packaging / update feed / stores). |
| X0.5 | `StorePolicy` | Per-store evaluation of proprietary-freeware acceptance and public-manifest requirement; failing stores dropped; AUR binary and self-hosted APT/YUM retained. |
| X0.9 | `RiskRegister` | Per-milestone risks (likelihood, impact, owner, mitigation) plus a rollback line; completeness validation. |

### X10 — Process and builder control (3)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| X10.3 | `DecisionLog` | Owner-level `D1`–`D7` / `G1`–`G7` decision log with date and answer, explicitly separate from ADRs. |
| X10.5 | `generate_weekly_report` | Reads `PLAN-INDEX.json`, reports counts by status, stale evidence (verified with no evidence) and failing rows. |
| X10.6 | `ScopeCreepGuard` | New ideas captured into `INBOX.md` with a proposed milestone instead of being built inline. |

### W3 — Permissions (2)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| W3.5 | `expand_path_actions` | `~`/`$HOME` expansion for path actions only; shell resources stay raw (and are also exposed as `*_raw`). |
| W3.11 | `McpPermissionActions` | `keel_list_mcp_resources` (resource = server), `keel_read_mcp_resource` (resource = `<server>:<uri>`) and `keel_<server>_<tool>` action/resource builders and parsers. |

### Y6 — Keel's own repository (1 implemented + 1 owner-gated)

| ID | Backend symbol | Real behaviour implemented |
|---|---|---|
| Y6.3 | `repo_descriptor` | Validates that the repo description names all four surfaces (Cowork, Code, Duet, Fleet) and that the homepage is `keel-desktop.vercel.app`. |

## 3. Owner-gated feature — documented, NOT implemented

**Y6.4 — "Repo visibility: Public, 0 stars/forks"** (P0, milestone M1, section "2.6 Keel's own repo").

- The live repository state is **Public with 0 stars/forks** (as observed at fetch time). This is a factual observation of an external/repository setting, not a locally implementable backend capability.
- Changing visibility, star or fork counts is an **owner action** on the hosting platform. The task board and `DECISIONS.md` treat owner-gated public-repo changes as rejected/out of scope; the integration protocol forbids visibility changes and owner-gate overrides.
- Consequently the module records Y6.4 in `OWNER_GATED` with `implemented=False` and an explicit reason, and **no implementation exists** in `FEATURE_IMPLEMENTATIONS`. The test `test_owner_gated_y6_4_is_documented_not_implemented` enforces this.

## 4. Prior P0 rows — verified, not reimplemented

All rows in these groups that were already `verified` at baseline were checked rather than reimplemented. An automated check of `PLAN-INDEX.json` confirmed that **all 62** verified rows in these groups have existing source files and test references on disk (0 missing):

| Group | Verified rows already implemented |
|---|---|
| D2 | D2.1, D2.3, D2.5, D2.7–D2.11, D2.13, D2.15, D2.16 (11) |
| E4 | E4.1, E4.2, E4.5, E4.8–E4.12, E4.15 (9) |
| X9 | X9.1, X9.3, X9.5, X9.7 (4) |
| W6 | W6.1, W6.3 (2) |
| W2 | W2.1–W2.4, W2.6, W2.8, W2.9, W2.11 (8) |
| W5 | W5.1–W5.4 (4) |
| X0 | X0.1–X0.4, X0.6–X0.8, X0.10 (8) |
| X10 | X10.1, X10.2, X10.4 (3) |
| W3 | W3.1–W3.4, W3.6–W3.10, W3.12, W3.13 (11) |
| Y6 | Y6.1, Y6.2 (2) |

No duplicate implementation was added for any `verified` row. Groups X4, W9 and W8 had no `verified` rows at baseline. The implemented ID set for this task follows exactly the `not_started` status recorded in `PLAN-INDEX.json` at baseline.

## 5. Test evidence

Command (from the worktree root):

```
$env:PYTHONPATH='<worktree>\keel\src'
python -m pytest -q keel/tests/test_small_groups_backend.py
```

Result:

```
........................................................                 [100%]
56 passed in 4.6s
```

Coverage of tests:

- one dedicated test for each of the 54 implemented IDs, exercising real behaviour (including negative/error paths where specified);
- `test_registry_covers_every_implemented_non_gated_feature` — 54 callables, per-group counts match the plan;
- `test_owner_gated_y6_4_is_documented_not_implemented` — Y6.4 recorded as owner-gated and absent from the registry.

No pre-existing source or test file was modified; only the three owned files were added. No push, release, deploy, visibility change or owner-gate override was performed.
