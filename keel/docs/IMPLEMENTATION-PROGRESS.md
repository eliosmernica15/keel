# Implementation progress — post-recovery batches

Baseline: local HEAD `46f5f27` (M2, unpushed), `origin/main` `79200c3`, M1/M2 closed. Master Plan v5 remains incomplete; only explicitly available v5 requirements are used.

## Batch 1 — Runtime tool and MCP correctness

**v5 requirement:** §6 design rules for MCP client/server behavior, typed tool results and reliable filesystem tools; §11 MCP isolation and tool-path controls. No new milestone or acceptance criteria were invented.

**Implemented:**
- `src/keel/session.py`: imported `HttpMcpServer` so `isinstance()` checks for HTTP MCP clients no longer raise `NameError`. The broad `except Exception` had silently discarded all MCP resource/prompt context.
- `src/keel/mcp.py` + `src/keel/session.py`: stdio servers now retain their `initialize` capabilities, and resource/prompt discovery is attempted only when the server advertises those capabilities. This prevents unanswered discovery requests from consuming later tool responses on servers that support tools only.
- `src/keel/runner.py`: `RealTools._list_dir` now defines `fnmatch` and its ignore-pattern set locally and applies the same ignore rules in recursive and non-recursive listings.
- `tests/test_runtime_defects.py`: new regression tests for both non-recursive/recursive `list_dir` behavior and the imported MCP type.
- `tests/test_e2e_milestone_6b.py`: real Session+MCP integration test now asserts that resource and prompt content from a stdio MCP server reaches the first model turn.

**Verification:** `python -m pytest tests/test_runtime_defects.py tests/test_e2e_milestone_6b.py -q -s` → `4 passed`; `python -m pytest tests/test_runtime_defects.py tests/test_e2e_milestone_6b.py tests/test_mcp.py tests/test_v2_mcp_usage_images.py tests/test_tool_registry.py -q` → `36 passed` (2026-11-20). This includes a real stdio MCP server and the real Session/runtime, not a mock of the fixed code path.

**Remaining from defect register:** version mismatch, M2 API/UI integration, secret storage, hook coverage, artifact allowlist metadata, and distribution/signing gaps remain unchanged and unfixed.

## Batch 2 — Release consistency

**v5 requirement:** §0.4 (versioned releases, manifests, integrity) and §11 source-protection controls. No new milestone content was invented.

**Implemented:**
- `src/keel/__init__.py` version corrected to `0.1.1`.
- `scripts/check_version_sync.py` and `src/keel/release/common.py` now include the Python package version in version validation, preventing future silent drift.
- `site/download.json`: removed the internal `__hosting__` metadata key.
- `src/keel/release/artifacts.py`: `scan_tree()` now inspects JSON content for internal metadata keys (`FORBIDDEN_JSON_KEYS`) in addition to path patterns.
- `tests/test_version_sync.py` and additions to `tests/test_release_controls.py` cover both fixes.

**Verification:** `python scripts/check_version_sync.py` → `OK - all sources agree on version 0.1.1`; `python -m pytest tests/test_version_sync.py tests/test_release_controls.py tests/test_website_download_only.py -q` → `26 passed`. Windows packaging verification is running separately.

**Remaining from defect register:** secret storage, hook coverage, distribution/signing gaps, and the known hook/version-adjacent items remain for later batches.

## Batch 3 — M2 provider catalog reaches the real bridge/UI

**v5 requirement:** §7.1 M2 — JSONC + schema, `provider/model` naming, bundled offline provider catalog. No missing milestone content was invented.

**Implemented:**
- `src/keel/webapp.py`: added authenticated bridge endpoints:
  - `GET /api/model-catalog` (catalog metadata and provider summaries),
  - `GET /api/model-catalog/<provider>` (offline model identifiers),
  - `GET /api/settings/schema` (bundled settings schema),
  - `GET /api/models/resolve?ref=provider/model` (resolver result or clear 400).
- `site/ui/app.js`: `fetchCatalog()` now queries the local Keel bridge first and falls back to the provider's live catalog only for the public mirror.
- `tests/test_m2_api_integration.py`: real `webapp.make_server()` tests for all endpoints, auth, catalog-only rejection, and UI source integration.
- `node --check site/ui/app.js` passes.

**Verification:** `python -m pytest tests/test_m2_api_integration.py tests/test_m2_provider_config.py tests/test_webapp.py -q` → `38 passed`.

**Remaining from defect register:** secret storage, hook coverage, distribution/signing gaps.

## Batch 4 — Encrypted provider secret storage

**v5 requirement:** §8 free path (`keyring` master key, AES-256-GCM via `cryptography`, passphrase fallback) and §11 control 5 (secret storage and redaction). No new milestone content was invented.

**Implemented:**
- `src/keel/secret_store.py`: AES-256-GCM encryption/decryption with 12-byte random nonce; master key from OS keyring when available, `KEEL_MASTER_PASSPHRASE` or a local 0600 key file otherwise; errors never include secret material.
- `src/keel/settings_store.py`: saved provider keys are encrypted with `enc: aes256gcm-v1`; legacy plaintext keys remain readable and are migrated on the next save; env application and public projections use decrypted/material-free values only.
- `pyproject.toml`: added `cryptography>=42.0` and `keyring>=24.0` (both named by v5).
- `tests/test_secret_storage.py`: encryption-at-rest, legacy migration, public-view redaction, and env application tests.
- `docs/proprietary/THIRD_PARTY_NOTICES.draft.md`: added dependency notices.

**Verification:** `python -m pytest tests/test_secret_storage.py tests/test_fleet_credentials.py tests/test_settings.py tests/test_m2_provider_config.py -q` → `49 passed`.

**Remaining from defect register:** hook coverage, distribution/signing gaps.

## Batch 5 — Hook lifecycle integration

**v5 requirement:** §6 architecture (hooks in the Python daemon) and §11 control 9 (hooks/plugins cannot reach Tier 2). No M3 criteria were invented; only events with existing execution paths were wired.

**Implemented:**
- `src/keel/session.py`: wired SessionStart, UserPromptSubmit, PermissionRequest, PermissionDenied, PostToolUseFailure, PostToolBatch, PreCompact, PostCompact, Stop, StopFailure, and SessionEnd in addition to the existing PreToolUse/PostToolUse.
- Terminal hook firing is centralized so cancellation, provider errors, max-turn errors, and successful completion all emit Stop/StopFailure and SessionEnd exactly once.
- `src/keel/hooks.py`: docstring updated to reflect wired events.
- `tests/test_hooks.py`: ordering, failure, cancellation, and hook-failure-tolerance tests.
- `tests/test_compaction.py`: PreCompact/PostCompact boundary ordering test.

**Verification:** `python -m pytest tests/test_hooks.py tests/test_compaction.py tests/test_vertical_slice.py -q` → `33 passed`.

**Remaining from defect register:** distribution/signing gaps (Ed25519, updater, rollback, binaries-only endpoint); 20 declared hook events still have no runtime surface in this slice and are intentionally left inert rather than fabricated.

## Batch 6 — Locked platform targets

**v5 requirement:** §0.4 platform list — Windows installer, macOS Apple Silicon and Intel, Linux AppImage, DEB and RPM. These are locked requirements, not owner decisions.

**Implemented:**
- `desktop-app/package.json`: macOS DMG/ZIP targets now build both `arm64` and `x64`; Linux targets now include `rpm`.
- `src/keel/release/build.py`: macOS build requests both architectures; Linux build includes RPM.
- `src/keel/release/common.py`: release channels/manifest now expect macOS Intel DMG/ZIP and Linux RPM; notes/install instructions updated.
- `site/download.json`: fallback manifest exposes Intel and RPM alternatives.
- `tests/test_platform_targets.py` and updated `tests/test_release_manager.py` cover config, manifest filenames, fallback channels, and build flags.

**Verification:** `python -m pytest tests/test_platform_targets.py tests/test_release_controls.py tests/test_release_manager.py tests/test_website_download_only.py -q` → `41 passed`. Cross-platform build artifacts remain CI-verified only on macOS/Linux; no local macOS/Linux build available.

## Batch 7 — Ed25519 signing infrastructure

**v5 requirement:** §0.4 (release manifests, checksums, integrity) and §11 update security (owner-held Ed25519 signatures, signed manifest, signature verification before install). Production-key custody remains an owner decision; this batch implements the technical chain with ephemeral test keys only.

**Implemented:**
- `src/keel/release/signing.py`: Ed25519 keypair generation for tests/dev, detached artifact signatures, manifest signing, canonical JSON, and verification helpers.
- `src/keel/release/build.py`: optional `--signing-key` produces `.sig` files for each artifact and signs `RELEASE-MANIFEST.json`.
- `src/keel/release/verify.py` + `cli.py`: optional `--public-key` verifies the manifest signature and detached artifact signatures in addition to HTTPS/size/SHA-256.
- `tests/test_release_signing.py`: roundtrip, tamper detection, detached-signature verification over loopback HTTP, and CLI option coverage.

**Verification:** `python -m pytest tests/test_release_signing.py tests/test_release_manager.py tests/test_release_controls.py -q` → `35 passed`.

**Not done (owner-gated):** no production key generated, deployed, or configured; no release published; updater/rollback still pending.

## Batch 8 — Offline catalog in Fleet provider endpoint

**v5 requirement:** §7.1 M2 — bundled offline provider catalog; provider/model discovery without internet. No new milestone content was invented.

**Implemented:**
- `src/keel/fleet/routes.py`: `POST /api/fleet/providers/catalog` now accepts `source: "offline"` and returns models from the bundled catalog without requiring a key or making a network call. Existing live behavior remains the default for compatibility.
- `tests/test_fleet_credentials.py`: offline discovery works with no key and no network; unknown providers fail clearly.

**Verification:** `python -m pytest tests/test_fleet_credentials.py tests/test_m2_api_integration.py tests/test_m2_provider_config.py -q` → `39 passed`.

## Batch 9 — Updater core

**v5 requirement:** §11 update security — signed manifest, HTTPS-only, version monotonicity, hash check before install, atomic swap, rollback. No production keys or endpoints were created.

**Implemented:**
- `src/keel/release/updater.py`: signed manifest verification, newest-version selection, verified artifact download with SHA-256 and optional detached Ed25519 signature, atomic directory staging, and rollback.
- `tests/test_updater.py`: loopback HTTP signed update, tampered manifest rejection, atomic install/rollback, and failed-install restoration.

**Verification:** `python -m pytest tests/test_updater.py tests/test_release_signing.py tests/test_release_manager.py -q` → `20 passed`.

**Not done:** Electron-side update wiring and production key/endpoint configuration remain owner-gated or later implementation work.

## Batch 10 — Updater CLI and opt-in Electron check

**v5 requirement:** §11 update security — verify before install, no mandatory hosted service, owner-controlled endpoint/key. No production endpoint or key was configured.

**Implemented:**
- `src/keel/release/cli.py`: `update-check` and `update-download` commands using signed manifests and verified artifacts.
- `desktop-app/main.js`: advisory startup update check, disabled unless `KEEL_UPDATE_MANIFEST_URL` is supplied; stores plan metadata in `update-state.json` and never auto-installs.
- `tests/test_updater.py`: CLI check against loopback signed manifest and Electron opt-in wiring test.
- `node --check desktop-app/main.js` passes.

**Verification:** `python -m pytest tests/test_updater.py tests/test_release_signing.py -q` → `10 passed`.

**Not done:** production key/endpoint, auto-install UI, version display, and rollback UI remain pending owner decisions or later work.

## Batch 11 — Fleet deletion correctness

**v5 requirement:** §6 canonical SQLite persistence and preservation of user data; no new milestone content was invented.

**Implemented:**
- `src/keel/fleet/service.py`: removed the shadowed early `delete_bot` definition so the library-purging implementation is the only one in effect.
- `tests/test_fleet.py`: behavioral test verifies Library files are purged when a bot is deleted, plus a source-level guard against reintroducing a duplicate definition.

**Verification:** `python -m pytest tests/test_fleet.py tests/test_fleet_library.py -q` → `40 passed`.

## Batch 12 — Subagent lifecycle hooks

**v5 requirement:** §6 subagents as a trust boundary and the existing hook architecture; no new milestone content was invented.

**Implemented:**
- `src/keel/subagent.py`: emits `SubagentStart` and `SubagentStop` around the real child `Session.run`, including on failure via `finally`.
- `tests/test_subagent.py`: verifies hook ordering relative to parent tool execution and completion.

**Verification:** `python -m pytest tests/test_subagent.py -q` → `5 passed`.

## Batch 13 — Fleet task lifecycle hooks

**v5 requirement:** §6 architecture (hooks in the Python daemon) and existing Fleet task lifecycle; no new milestone content was invented.

**Implemented:**
- `src/keel/fleet/routes.py`: fires `TaskCreated` on task creation and `TaskCompleted` on the transition to `completed`, using configured hooks through a non-blocking helper.
- `tests/test_fleet_tasks.py`: end-to-end bridge test for both events and their ordering.

**Verification:** `python -m pytest tests/test_fleet_tasks.py -q` → `15 passed`.

## Batch 14 — Config and instruction hooks

**v5 requirement:** §6 architecture (hooks in the Python daemon); no new milestone content was invented.

**Implemented:**
- `src/keel/webapp.py`: fires `ConfigChange` after settings saves with only changed section names, never values.
- `src/keel/session.py`: fires `InstructionsLoaded` with attached instruction source names before the first model turn.
- `tests/test_hooks.py`: tests for both events and payload safety.

**Verification:** `python -m pytest tests/test_hooks.py tests/test_webapp.py -q` → `34 passed`.

## Batch 15 — FileChanged tool hooks

**v5 requirement:** §6 architecture (hooks in the Python daemon) and existing filesystem tool surface; no new milestone content was invented.

**Implemented:**
- `src/keel/runner.py`: `FileChanged` fires after successful write/edit and after successful extended file mutations (delete/move/copy/apply_patch/make_dir). Hooks are advisory and never block the file operation.
- `tests/test_hooks.py`: verifies the event fires after a real `write_file` invocation.

**Verification:** `python -m pytest tests/test_hooks.py tests/test_safety.py tests/test_tool_registry.py -q` → `57 passed`.

Windows installer rebuilt successfully after accumulated release/updater changes.

## Batch 16 — Elicitation hooks

**v5 requirement:** §6 architecture (hooks in the Python daemon) and existing operator-question flow; no new milestone content was invented.

**Implemented:**
- `src/keel/fleet/tools.py`: fires `Elicitation` before an `ask_user` question and `ElicitationResult` after an answer or timeout.
- `tests/test_fleet_ask_user.py`: end-to-end hook ordering test through the real bridge and approval/answer API.

**Verification:** `python -m pytest tests/test_fleet_ask_user.py -q` → `2 passed`.

## M6 Batch 1 — Release manifest hardening (C12.1, C12.4, C12.6)

**Implemented:** min_version/blocked_versions/rollout manifest fields, deterministic rollout bucketing, mirror failover with signature checks, and `keel release dry-run`.
**Verification:** `python -m pytest tests/test_release_hardening.py tests/test_updater.py tests/test_release_signing.py -q` → `16 passed`; registry regenerated and consistency tests pass.
**Next:** C8.1 recoverable trash for agent deletions.

## M6 Batch 2 — Recoverable trash (C8.1)

**Implemented:** `src/keel/trash.py` with move/list/restore; `delete_file` now returns a recoverable trash id.
**Verification:** `python -m pytest tests/test_trash.py tests/test_safety.py tests/test_tool_registry.py -q` → `39 passed`.
**Next:** C3.2 doom-loop detection.

## M6 Batch 4 — Screen-share safe mode (C1.4)

**Implemented:** Ctrl+Shift+S toggle masks key hints, endpoints and local paths during screen share/recording; badge indicator added.
**Verification:** `python -m pytest tests/test_screen_safe_mode.py -q` → `4 passed`; `node --check` clean.

## M6 Batch 5 — Outbound redaction, output DLP, egress log (B3.6, B3.8, B3.5)

**Implemented:** `src/keel/redaction.py` with narrow credential detection; `Session` redacts a copy of outbound messages (original transcript stays intact) and records egress JSONL; `RealTools` write/edit/apply_patch refuse credential-shaped content, with `KEEL_OUTPUT_DLP` opt-out.
**Verification:** `python -m pytest tests/test_redaction.py tests/test_safety.py tests/test_tool_registry.py tests/test_resilience.py -q` → `49 passed`.
**Next:** B3.3 dry-run mode.

## M6 Batch 6 — Dry-run mode (B3.3)

**Implemented:** `SessionConfig.dry_run` (opt-in) records planned tool calls, emits a `[dry-run]` notice, and executes nothing; `keel run --dry-run` exposes it, with side effects reported in the result envelope and diagnostics.
**Verification:** `python -m pytest tests/test_dry_run.py tests/test_vertical_slice.py tests/test_tool_registry.py tests/test_safety.py -q` → `49 passed`.
**Next:** B3.4 read-only session mode and per-project egress allowlist.

## M6 Batch 7 — Read-only sessions and egress allowlist (B3.4)

**Implemented:** `SessionConfig.read_only` denies mutating tools at the permission boundary; `src/keel/egress.py` enforces `KEEL_EGRESS_ALLOWLIST` in `web_fetch`/`web_search`; `keel run --read-only` added.
**Verification:** `python -m pytest tests/test_read_only.py tests/test_dry_run.py tests/test_safety.py tests/test_tool_registry.py -q` → `45 passed`.
**Next:** B2.1 verification loop (auto-detect and run tests after edits).

## M6 Batch 8 — Verification loop (B2.1)

**Implemented:** `src/keel/verification.py` detects test/lint commands from project manifests and runs them after a turn that changed files; results appear in the result envelope and an informational event; `keel run --no-verify` opts out.
**Verification:** `python -m pytest tests/test_verification.py tests/test_dry_run.py tests/test_read_only.py tests/test_resilience.py -q` → `18 passed`.
**Next:** A1.10 visible task checklist (`todo` tool).

## M6 Batch 9 — Visible task checklist (A1.10)

**Implemented:** `src/keel/todos.py` persists a normalised checklist under `state_root/todos.json`; `todo` native tool and session handler render the checklist and emit it as an informational event.
**Verification:** `python -m pytest tests/test_todo.py tests/test_tool_registry.py tests/test_hooks.py tests/test_verification.py -q` → `47 passed`.
**Next:** A1.5 `/init` command generating AGENTS.md.

## M6 Batch 10 — Repository init (A1.5)

**Implemented:** `src/keel/init_project.py` scans manifests, directories and test folders and renders `AGENTS.md`; `keel init [--force]` writes it, refusing to overwrite by default.
**Verification:** `python -m pytest tests/test_init_project.py tests/test_vertical_slice.py tests/test_tool_registry.py -q` → `31 passed`.
**Next:** A1.7 slash commands and A1.9 image/file attachment workflow.

## M6 Batch 11 — Slash commands (A1.7)

**Implemented:** added `/undo`, `/redo`, `/compact`, `/export`, `/models`, `/themes`, `/details` as local builtins in `src/keel/commands.py`; undo/redo reuse the recoverable trash with a redo marker.
**Verification:** `python -m pytest tests/test_slash_commands.py tests/test_commands.py tests/test_vertical_slice.py -q` → `32 passed`.
**Next:** A1.9 image/file attachment workflow.

## M6 Batch 12 — Composer attachments and @file search (A1.9)

**Implemented:** `GET /api/files/search` provides bounded fuzzy workspace file matching; the composer now accepts pasted/dropped images and shows an `@`-triggered file suggestion dropdown with keyboard selection.
**Verification:** `python -m pytest tests/test_attachments_ui.py tests/test_webapp.py -q` → `20 passed`; `node --check` clean.
**Next:** C2.5 unified surface switcher with per-surface agents and permissions.

## M6 Batch 13 — Unified surface configuration (C2.5)

**Implemented:** `src/keel/surfaces.py` defines Cowork/Code/Duet/Fleet with per-surface default agent, permission mode and tool allowlist, persisted as local settings; authenticated `GET /api/surfaces` and `POST /api/surfaces/<name>` expose them; the UI shows a per-surface badge.
**Verification:** `python -m pytest tests/test_surfaces.py tests/test_webapp.py tests/test_settings.py -q` → `35 passed`; `node --check` clean.
**Next:** C1.3 agent avatars/colors/voices and C2.3 voice previews.

## M6 Batch 14 — Global stop and token revocation (B3.9, A3.6)

**Implemented:** `cancel_all_turns()` signals every in-flight Fleet turn; `POST /api/kill-switch` stops all turns and rotates the bridge token, revoking existing client credentials; a header "Stop all" button wires it into the UI.
**Verification:** `python -m pytest tests/test_kill_switch.py tests/test_webapp.py tests/test_fleet_ask_user.py -q` → `22 passed`; `node --check` clean.
**Next:** B3.11 provider circuit breaker with retry/backoff and health scoring.

## M6 Batch 15 — Provider circuit breaker (B3.11)

**Implemented:** `src/keel/circuit_breaker.py` tracks per-provider health with closed/open/half-open states; `ProviderModelClient` consults the breaker, records outcomes, and fails fast while open.
**Verification:** `python -m pytest tests/test_circuit_breaker.py tests/test_providers.py tests/test_vertical_slice.py -q` → `20 passed`.
**Next:** C6.5 memory provenance and tainted-source tracking (deferred to batch 17).

## M6 Batch 16 — Zero-secrets release scan (A4.8)

**Implemented:** extended secret detection (Google/Slack/JWT shapes) and wired `scan_secret_markers()` into `check-artifacts` and `release dry-run`, so a staged release with a planted credential fails locally before publication.
**Verification:** `python -m pytest tests/test_release_no_secrets.py tests/test_release_hardening.py tests/test_release_signing.py -q` → `14 passed`; existing `release/` and `dist/win-unpacked` scan clean.
**Next:** C6.5 memory provenance and tainted-source tracking.

## M6 Batch 17 — Memory provenance and taint (C6.5)

**Implemented:** `src/keel/memory.py` stores local JSONL memories with session/tool/source provenance and taints untrusted sources; `remember`/`recall` native tools expose it in-session, with review/forget controls.
**Verification:** `python -m pytest tests/test_memory.py tests/test_todo.py tests/test_tool_registry.py tests/test_read_only.py -q` → `30 passed`.
**Next:** A2.2 voice-to-task handoff and push-to-talk dictation.

## M6 Batch 18 — Voice dictation and voice-to-task (A2.2)

**Implemented:** opt-in push-to-talk dictation in both composers using the browser SpeechRecognition API, with explicit consent notice, live transcript visibility, cancel, and Shift+hold to send the dictated text as a task.
**Verification:** `python -m pytest tests/test_voice.py tests/test_attachments_ui.py tests/test_screen_safe_mode.py -q` → `13 passed`; `node --check` clean.
**Next:** A2.5 group-chat loop prevention.

## M6 Batch 19 — Group-chat loop guards (A2.5)

**Implemented:** `src/keel/fleet/mention_guard.py` caps agent @mentions per pair and per round; Fleet group sinks replace runaway mentions with a `loop_guard` system row, and the group brief warns agents about the cap.
**Verification:** `python -m pytest tests/test_mention_guard.py tests/test_fleet_groups.py tests/test_fleet_approvals.py -q` → `34 passed`.
**Next:** A1.13 custom tools from `.keel/tools/`.

## M6 Batch 20 — Custom Python tools (A1.13)

**Implemented:** `src/keel/custom_tools.py` discovers `.keel/tools/*.py` via AST only, requires explicit content-hash approval before any import, and registers approved tools with `execute` permission; `keel tools list/approve/revoke` added.
**Verification:** `python -m pytest tests/test_custom_tools.py tests/test_tool_registry.py tests/test_commands.py -q` → `31 passed`.
**Next:** A1.12 per-agent tool enable/disable and permission overrides.

## M6 Batch 21 — Per-agent tool policies (A1.12, verification only)

**Verified existing implementation:** `fleet_policies` storage, `ApprovalBroker.policy_outcome` enforcement, and fleet policy routes already implement per-agent tool enable/disable and standing permission overrides.
**Evidence:** `python -m pytest tests/test_fleet_approvals.py -q` → `15 passed` (including always/never policies, isolation and revocation). No code duplication.
**Next:** A1.2 attach to a running Keel session (`keel attach`).

## M6 Batch 22 — CLI attach to a running daemon (A1.2)

**Implemented:** `src/keel/attach.py` and `keel attach` list sessions, show history, and send messages through the authenticated local v2 sessions API of a running daemon.
**Verification:** `python -m pytest tests/test_attach.py tests/test_compat_runtime.py tests/test_compat_tracer.py tests/test_webapp.py -q` → `35 passed`.
**Next:** A3.10 per-vendor cost caps with daily/monthly windows.

## M6 Batch 23 — Per-vendor cost caps (A3.10)

**Implemented:** `src/keel/cost_caps.py` keeps local caps and a JSONL usage ledger, estimates costs from tokens, enforces caps at the CLI run boundary, and adds `keel costs status/cap`.
**Verification:** `python -m pytest tests/test_cost_caps.py tests/test_vertical_slice.py tests/test_commands.py -q` → `21 passed`.
**Next:** B1.1 grammar/JSON-schema-constrained tool calls with tolerant parsing.

## M6 Batch 24 — Constrained and tolerant tool calls (B1.1, B1.2)

**Implemented:** `src/keel/tool_json.py` repairs common malformed tool JSON, validates/coerces inputs against declared schemas, and tightens schemas; the OpenAI-compatible adapter and Session use it before permission checks and execution.
**Verification:** `python -m pytest tests/test_tool_json.py tests/test_providers.py tests/test_vertical_slice.py tests/test_hooks.py tests/test_safety.py -q` → `60 passed`.
**Next:** B1.6 model download manager with resume and integrity verification.

## M6 Batch 25 — Resumable model downloads (B1.6)

**Implemented:** `src/keel/model_downloads.py` supports HTTP Range resume, `.part` staging and SHA-256 verification before publish; `keel model download` exposes it with explicit `--allow-http` opt-in.
**Verification:** `python -m pytest tests/test_model_downloads.py tests/test_commands.py tests/test_vertical_slice.py -q` → `23 passed`.
**Next:** A4.4 rigor contract in persona and A2.8 local Playwright-style E2E scaffold.

## M6 Batch 26 — Rigor contract in persona (A4.4)

**Implemented:** `rigor_attachment()` requires evidence before completion claims and forbids fabricated results; injected into Fleet guidance and every Session's context with an `InstructionsLoaded` source.
**Verification:** `python -m pytest tests/test_rigor.py tests/test_compaction.py tests/test_vertical_slice.py tests/test_hooks.py -q` → `39 passed`.
**Next:** A2.8 local E2E flow scaffold.

## M6 Batch 27 — Local end-to-end flows (A2.8)

**Implemented:** `tests/test_e2e_local.py` drives the real authenticated bridge through app shell/auth, settings round-trip, surfaces, file search and Fleet chat, with no external services. A browser-driven Playwright layer remains optional.
**Verification:** `python -m pytest tests/test_e2e_local.py -q` → `4 passed`.
**Next:** A3.3 mock/scripted agents (verification) and B1.5 smart context management.

## M6 Batch 28 — Context and mock-agent verification (B1.5, A3.3, verification only)

**Verified existing implementations:** `context.py` budget/compaction/thrash guard and `fakes.py` deterministic scripted providers.
**Evidence:** `python -m pytest tests/test_compaction.py tests/test_compat_runtime.py -q` → `19 passed`. No code duplication.
**Next:** B2.3 Duet default design (builder and independent reviewer agents).

## M6 Batch 29 — Duet builder and reviewer (B2.3)

**Implemented:** `src/keel/duet.py` defines builder and independent read-only reviewer roles; the `Duet` tool runs both via subagents with recursion excluded and returns both evidence-bearing summaries.
**Verification:** `python -m pytest tests/test_duet.py tests/test_subagent.py tests/test_tool_registry.py -q` → `26 passed`.
**Next:** A1.22 internal AGENTS.md builder instructions.

## M6 Batch 30 — Internal builder guide (A1.22)

**Implemented:** `keel/AGENTS.md` documents layout, commands, conventions and evidence rules; instruction discovery now finds AGENTS.md alongside CLAUDE.md.
**Verification:** `python -m pytest tests/test_builder_guide.py tests/test_rigor.py tests/test_compaction.py -q` → `12 passed`.
**Next:** C7.1 import other tools' instruction formats and C1.1 repo hygiene stack verification.

## M6 Batch 31 — Other tools' instruction formats (C7.1)

**Implemented:** instruction discovery now reads `.cursorrules`, `.windsurfrules`, `.github/copilot-instructions.md` and `.cursor/rules/*.md` root-first, and imported files are explicitly labelled untrusted context.
**Verification:** `python -m pytest tests/test_instruction_imports.py tests/test_builder_guide.py tests/test_rigor.py tests/test_compaction.py -q` → `15 passed`.
**Next:** C1.1 repository hygiene stack verification.

## M6 Batch 32 — Repository hygiene stack (C1.1)

**Implemented:** added `.editorconfig`, changelog, patch policy, and ruff/mypy configuration; `scripts/check_repo_hygiene.py` verifies the stack locally.
**Verification:** `python -m pytest tests/test_repo_hygiene.py tests/test_release_controls.py -q` → `22 passed`.
**Next:** A5.1 gateway process concept with status/start/stop.

## M6 Batch 33 — Gateway lifecycle (A5.1)

**Implemented:** `src/keel/gateway.py` manages the scheduler in a supervised background thread with status/start/stop; authenticated `/api/gateway*` endpoints and `keel gateway status` expose it.
**Verification:** `python -m pytest tests/test_gateway.py tests/test_fleet_routines.py tests/test_webapp.py -q` → `52 passed`.
**Next:** A4.1 signed outgoing webhooks and A5.3 account-level config inheritance.

## M6 Batch 34 — Signed outgoing webhooks (A4.1)

**Implemented:** `src/keel/webhooks.py` signs payloads with HMAC-SHA256 over timestamp+body, verifies signatures with replay window, and delivers opt-in via `keel webhook send` using `KEEL_WEBHOOK_SECRET`.
**Verification:** `python -m pytest tests/test_webhooks.py tests/test_commands.py -q` → `14 passed`.
**Next:** A5.3 account-level configuration inheritance.

## M6 Batch 35 — Settings inheritance verification (A5.3, verification only)

**Verified existing implementation:** `settings.py` resolves managed/flags/local/project/user/env scopes with provenance and restrictive-key rules.
**Evidence:** `python -m pytest tests/test_settings.py -q` → `14 passed`. No code duplication.
**Next:** A5.5 outbound message state machine.

## M6 Batch 36 — Outbound message state machine (A5.5)

**Implemented:** `src/keel/message_state.py` tracks queued→sent→delivered→read with failed/retry paths in a local JSONL ledger; webhook sends now record their lifecycle.
**Verification:** `python -m pytest tests/test_message_state.py tests/test_webhooks.py -q` → `9 passed`.
**Next:** B2.6 local RAG knowledge bases.

## M6 Batch 37 — Local RAG knowledge bases (B2.6)

**Implemented:** `src/keel/rag.py` indexes folders with deterministic local TF-IDF-style embeddings, persists named JSON indexes under state, and supports scored search; `rag_index`/`rag_search` tools registered.
**Verification:** `python -m pytest tests/test_rag.py tests/test_tool_registry.py -q` → `23 passed`.
**Next:** A1.16 session statistics/import-export verification.

## M6 Batch 38 — Session import/export and statistics (A1.16)

**Implemented:** `src/keel/session_export.py` exports/imports local JSON session bundles and computes row/token statistics; `keel session export/import/stats` commands added.
**Verification:** `python -m pytest tests/test_session_export.py tests/test_compat_runtime.py -q` → `16 passed`.
**Next:** A1.11 browser and workspace resource management.

## M6 Batch 39 — Browser and workspace resource budgets (A1.11)

**Implemented:** `src/keel/resource_limits.py` enforces tab counts, workspace byte budgets and per-resource size caps with a status snapshot.
**Verification:** `python -m pytest tests/test_resource_limits.py -q` → `4 passed`.
**Next:** A3.1 grammar-constrained decoding verification or B2.2 automatic verification loop verification.

## M6 Batch 40 — MCP presets catalog (A4.3, verification only)

**Verified existing implementation:** `fleet/connector_ops.py` already ships a catalog of free/self-hosted presets (filesystem, memory, github, sequential-thinking) with `preset_spec` for opt-in local servers.
**Evidence:** `python -m pytest tests/test_mcp_presets.py tests/test_mcp.py -q` → `11 passed`.
**Next:** B4.12 redacted diagnostics bundle.

## M6 Batch 41 — Redacted diagnostics bundle (B4.12)

**Implemented:** `src/keel/diagnostics.py` builds a local ZIP of environment facts with all credential values masked and no conversation content; `keel doctor --bundle` writes it.
**Verification:** `python -m pytest tests/test_diagnostics.py tests/test_commands.py -q` → `13 passed`.
**Next:** B4.13 auto-rollback after repeated failed starts.

## M6 Batch 42 — Auto-rollback after failed starts (B4.13)

**Implemented:** `src/keel/start_health.py` tracks consecutive failed launches per version and flags rollback after 3 (success resets), complementing the existing updater rollback.
**Verification:** `python -m pytest tests/test_start_health.py -q` → `3 passed`.
**Next:** B5.2 release feeds and version history.

## M6 Batch 43 — Release feeds and version history (B5.2)

**Implemented:** `src/keel/release_feed.py` generates `latest.json`, a JSON version history and a well-formed RSS feed from local release notes.
**Verification:** `python -m pytest tests/test_release_feed.py -q` → `3 passed`.
**Next:** B5.5 privacy/EULA/third-party-notices site pages.

## M6 Batch 44 — Privacy, EULA and notices pages (B5.5)

**Implemented:** local site pages for privacy ("what Keel does not collect"), a draft EULA with versioned local acceptance/re-prompt, and third-party notices. Legal finalization remains owner-gated.
**Verification:** `python -m pytest tests/test_legal_pages.py -q` → `4 passed`.
**Next:** C12.1 blocked versions and minimum-version enforcement verification.

## M6 Batch 45 — Download page auto-detection (B5.1)

**Implemented:** `/download` landing page now detects the visitor's OS and CPU and marks the recommended installer card, while keeping the verified-manifest availability gate.
**Verification:** `python -m pytest tests/test_download_detect.py -q` → `2 passed`; `node --check` clean.
**Next:** C1.12 LAN/headless client pairing allowlist.

## M6 Batch 46 — Client pairing allowlist (C1.12)

**Implemented:** `src/keel/pairing.py` stores explicit LAN/headless client pairings locally with revocation, so remote access is opt-in and reversible.
**Verification:** `python -m pytest tests/test_pairing.py -q` → `3 passed`.
**Next:** C8.5 plugin/skill supply-chain review with permission diffs.

## M6 Batch 47 — Skill supply-chain review (C8.5)

**Implemented:** `src/keel/supply_chain.py` extracts requested capabilities from skill frontmatter and body, and produces a permission diff against a baseline, flagging new capabilities and untrusted project-scope skills for review.
**Verification:** `python -m pytest tests/test_supply_chain.py -q` → `4 passed`.
**Next:** B3.11 circuit breaker verification or C9.1 model manager.

## M6 Batch 48 — Local model manager (C9.1)

**Implemented:** `src/keel/model_manager.py` loads/unloads local models with an idle timeout and RAM budget; unloads are local decisions that never delete files or contact remote services.
**Verification:** `python -m pytest tests/test_model_manager.py -q` → `3 passed`.
**Next:** B5.3 system requirements and first-run guide.

## M6 Batch 49 — Requirements and first-run guide (B5.3)

**Implemented:** `site/requirements.html` documents per-platform requirements, a model-size guide, and a first-run guide for unsigned builds with SHA-256 verification.
**Verification:** `python -m pytest tests/test_requirements_page.py -q` → `2 passed`.
**Next:** B7.1 property-based and fuzz tests for path containment.

## M6 Batch 50 — Path/command fuzz tests (B7.1)

**Implemented:** `tests/test_property_safety.py` uses seeded random inputs to verify secret/system paths are always refused and catastrophic shell verbs are declined, with no new dependency.
**Verification:** `python -m pytest tests/test_property_safety.py -q` → `3 passed`.
**Next:** B4.13 verification done; continue with C9.2 UI virtualization/backpressure.

## M6 Batch 51 — Deterministic workflow nodes (C5.1, C5.2)

**Implemented:** `workflows.py` now supports `map` and `loop` nodes with `{{item}}`/`{{index}}` binding and a `human` node that consults an approval callback with timeout/default.
**Verification:** `python -m pytest tests/test_workflow_nodes.py tests/test_workflows.py -q` → `9 passed`.
**Next:** C3.1 best-of-N with test selection.

## M6 Batch 52 — Best-of-N selection (C3.1)

**Implemented:** `src/keel/best_of_n.py` generates N candidates via a pluggable local generator and selects the best by a test-based score, returning the chosen value with evidence.
**Verification:** `python -m pytest tests/test_best_of_n.py -q` → `4 passed`.
**Next:** C8.8 local red-team evaluation suite.

## M6 Batch 53 — Best-of-N and red-team suite (C3.1, C8.8)

**Implemented:** `best_of_n.py` selects candidates by test-based scoring; `red_team.py` runs deterministic adversarial cases (secret redaction, path refusal, mention loops, output DLP) locally with no provider.
**Verification:** `python -m pytest tests/test_best_of_n.py tests/test_red_team.py -q` → `7 passed`.
**Next:** C2.1/C2.2/C2.4 Keel Cowork/Code/Fleet surface tooling verification.

## M6 Batch 54 — Product surfaces verification (C2.1, C2.2, C2.4)

**Verified existing implementations:** `surfaces.py` defines Cowork, Code, Duet and Fleet surfaces with per-surface default agents, permission modes and tool sets, exercised end-to-end in `test_surfaces.py` and `test_e2e_local.py`.
**Evidence:** `python -m pytest tests/test_surfaces.py -q` → `6 passed`.
**Next:** C9.2 UI virtualization/backpressure and B4.5 rich rendering.

## M6 Batch 55 — Rich rendering primitives (B4.5)

**Implemented:** `src/keel/markdown_render.py` detects Markdown fences, Mermaid, LaTeX and image/PDF previews and emits HTML-escaped scaffolds with copy controls.
**Verification:** `python -m pytest tests/test_markdown_render.py -q` → `4 passed`.
**Next:** A2.3 persistent per-agent browser profiles.

## M6 Batch 56 — Per-agent browser profiles (A2.3)

**Implemented:** `src/keel/browser_profiles.py` creates and persists isolated browser-profile and workspace directories per agent, with reset and listing.
**Verification:** `python -m pytest tests/test_browser_profiles.py -q` → `3 passed`.
**Next:** B7.4 performance budgets and B7.2 golden/chaos tests.

## M6 Batch 57 — Performance budgets (B7.4)

**Implemented:** `src/keel/performance_budgets.py` defines cold-start, idle-memory, installer-size and first-token budgets with a checker for caller-supplied measurements.
**Verification:** `python -m pytest tests/test_performance_budgets.py -q` → `3 passed`.
**Next:** B7.2 golden-file and chaos tests.

## M6 Batch 58 — Golden and chaos helpers (B7.2)

**Implemented:** `src/keel/golden.py` provides deterministic snapshot normalisation/digest, golden-file check with update mode, diff output, and a chaos fault injector for mid-turn failure tests.
**Verification:** `python -m pytest tests/test_golden_chaos.py -q` → `3 passed`.
**Next:** C11.5 EULA acceptance state (owner-gated legal finalization stays blocked).

## M6 Batch 59 — Local EULA acceptance (C11.5)

**Implemented:** `src/keel/eula.py` stores acceptance of a specific EULA version locally and flags re-prompt when the version changes; the legal text itself remains owner-gated.
**Verification:** `python -m pytest tests/test_eula.py -q` → `3 passed`.
**Next:** C9.2 UI virtualization/backpressure.

## M6 Batch 60 — UI virtualization and backpressure (C9.2)

**Implemented:** `src/keel/virtual_list.py` computes visible list slices with overscan and a token-bucket backpressure limiter for streaming updates.
**Verification:** `python -m pytest tests/test_virtual_list.py -q` → `3 passed`.
**Next:** Remaining P1/P2 features; continue through the registry.

## M6 Batch 61 — Agent style and voice previews (C1.3)

**Implemented:** `src/keel/agent_style.py` deterministically assigns avatars, accent colors and voices to agents and produces preview descriptors for the UI.
**Verification:** `python -m pytest tests/test_agent_style.py -q` → `3 passed`.
**Next:** B1.5 difficulty-based model routing or C5.x workflow versioning.

## M6 Batch 62 — Difficulty-based model routing (B1.3)

**Implemented:** `src/keel/model_router.py` selects an easy/medium/hard model tier from local signals (prompt size, tool count, verification need) with no hosted router.
**Verification:** `python -m pytest tests/test_model_router.py -q` → `3 passed`.
**Next:** B1.7 hardware detector and quantization advisor.

## M6 Batch 63 — Hardware detection and quantization advice (B1.7)

**Implemented:** `src/keel/hardware.py` reads local platform/CPU/RAM signals and recommends a quantization level, labelling unknown RAM honestly.
**Verification:** `python -m pytest tests/test_hardware.py -q` → `3 passed`.
**Next:** B1.9 compare mode (arena) and other local-model reliability tools.

## M6 Batch 64 — Compare mode (B1.9)

**Implemented:** `src/keel/arena.py` runs a prompt through two caller-supplied local generators, collects both outputs and an optional preference winner.
**Verification:** `python -m pytest tests/test_arena.py -q` → `3 passed`.
**Next:** B1.4 prefix/KV-cache reuse and B1.10 speculative decoding toggle.

## M6 Batch 65 — SWE benchmark and installer smoke harness (C13.1, C13.4)

**Implemented:** `swe_bench.py` runs tiny local tasks through a pluggable agent and records a per-model leaderboard; `installer_smoke.py` validates staged installer checksums and upgrade policy, and declares CI-only clean-VM checks.
**Verification:** `python -m pytest tests/test_swe_bench.py tests/test_installer_smoke.py -q` → `6 passed`.
**Owner-gated:** C11.1 (hosting choice) and C11.2 (repo security enforcement) marked `blocked` — require owner decisions.
**Next:** B1.4 prefix/KV-cache reuse and B1.10 speculative decoding toggle.

## M6 Batch 66 — Prefix cache and speculative toggle (B1.4, B1.10)

**Implemented:** `src/keel/prefix_cache.py` finds the longest shared prompt prefix with bounded storage and exposes an opt-in (`KEEL_SPECULATIVE_DECODING`) speculative-decoding flag, off by default.
**Verification:** `python -m pytest tests/test_prefix_cache.py -q` → `3 passed`.
**Next:** More P1/P2 features from the registry.

## M6 Batch 3 — Doom-loop detection (C3.2)

**Implemented:** identical tool-call repetition emits a warning at three repeats and terminates the turn with `terminal_reason=doom_loop` at five.
**Verification:** `python -m pytest tests/test_resilience.py tests/test_vertical_slice.py tests/test_compaction.py -q` → `20 passed`.
**Next:** C1.4 screen-share safe mode.

---

## M6 expansion — final registry status

**Feature registry (`PLAN-INDEX.json` / `parity.json`):** 228 addendum feature IDs
preserved, 226 `verified`, 2 `blocked`, 0 `not_started`. `Keel_Master_Plan_v6.md`
is generated from the registry; v5 and both addenda remain unchanged on disk.

**Two blocked features (genuine owner decisions, not fabricated):**
- `C11.1` — source-hosting choice (GitHub free-tier caveats vs a different forge).
- `C11.2` — repository security enforcement (mandatory 2FA, signed commits,
  protected branches, release reviewers). Both require owner account decisions
  the agent must not make unilaterally.

**Honesty note on verification depth.** A `verified` status means the feature's
automated tests pass and its behaviour was checked locally. Features fall into
two tiers:
- **Runtime-integrated** — wired into the live Python runtime (hooks, redaction,
  trash, circuit breaker, dry-run, cost caps, RAG, workflows, memory, etc.).
- **Local descriptor/scaffold** — features that inherently need an external
  service or owner environment (CI runners, clean VMs, hosted forges, optional
  container/WASM runtimes, phone companions, paid/licensing seams). For these,
  the local data model, gating and tests exist and are verified, but the real
  external integration is explicitly marked as requiring that environment.
  Legal texts (EULA, trademark, notices) are drafts pending owner review.

**Full suite:** `python -m pytest -q` green throughout the expansion (final run
recorded in the batch commit history). No push, release publication, deployment,
visibility change, history rewrite, credential rotation or production signing
occurred.

---

## Operational completion phase — history reconciliation

**Actual Git history (verified with `git rev-list`/`git log`):**
- `origin/main` = `79200c3`; HEAD before this phase = `07de3ab`;
  HEAD was **59 commits ahead** of the remote (not 17). The earlier "17 ahead"
  report was the state at `0b026d0`, the baseline when the v6 task started —
  17 commits predated v6, then +1 plan commit, then +41 batch commits = 59.
- The "110 batches" figure counts **ledger batch numbers, not commits**. Many
  batches were combined into grouped commits: e.g. batches 1–3 → `676f845`;
  39–51 → `5ee3879`; 52–64 → `e00b648`; 65–74 → `ff7d489`; 75–89 → `5dd62a7`;
  90–110 → `07de3ab`. Most batches 4–38 have individual commits. No history was
  rewritten; the working tree is clean.

## Operational completion — tier classification and real upgrades

The registry now records `implementation_tier` per feature (honest, not inferred
from passing unit tests): 49 operational, 45 local modules, 109 descriptors,
23 external-dependency, 2 owner-gated.

**Upgraded from descriptor/scaffold to real local functionality:**
- `C2.1` Cowork — real DOCX/XLSX read+write, CSV conversion, cell statistics and
  cited document Q&A (`src/keel/documents.py`), exercised over the real backend.
- `B4.11` backups — real AES-256-GCM encrypted backup/restore with PBKDF2 and
  per-file SHA-256 verification (`src/keel/backups.py`), exercised E2E.
- `C4.1` debugging — real Python debugger with breakpoints, stepping and frame
  inspection via `bdb` (`src/keel/debugger.py`).
- `B3.1/B3.2` sandbox — real bounded subprocess execution with time/memory/CPU
  limits (`src/keel/sandbox_exec.py`).
- `C2.3` Duet — real local inline completion and reviewer comments
  (`src/keel/inline_completion.py`).
- `A2.3` browser — real persistent profile management and opt-in launch of a
  locally installed browser (`src/keel/browser_launch.py`).
- `A2.8` E2E — `tests/test_e2e_operations.py` starts the real backend and
  exercises sessions, real tool paths, permission denials, provider failures,
  DLP, Cowork files, backup/recovery, update policy and secret-leak checks.

**Source-document recovery defect fixed:** the original Downloads copies of v5
and both addenda disappeared. They were reconstructed byte-exactly from v6's
preserved appendices into `keel/docs/plan-sources/` (hashes: v5
`da1dd5dc…427f`, addenda `e4e314a5…` and `b4221915…`), and the builders now
prefer those canonical in-repo copies. A regression test pins all three hashes.

**Further descriptor→real upgrades (operational completion):**
- `B3.1/B3.2` real bounded Python subprocess sandbox (`sandbox_exec.py`).
- `C2.3` real Duet local inline completion (`inline_completion.py`).
- `A2.3` real browser-profile management + opt-in launch (`browser_launch.py`).
- `A3.1` real webhook retry/backoff + delivery log (`webhook_delivery.py`).
- `C5.4` real polling file watcher (`file_watcher.py`).
- `A2.1/A2.2` real confirmed voice-to-task queue (`voice_tasks.py`).
- `C2.1` real IMAP-style email drafts, ICS calendar parsing, WAV meeting audio
  (`cowork_channels.py`), plus DOCX/XLSX over the HTTP bridge (`webapp.py`).
- `C9.1` real model runtime with RAM budget + LRU eviction (`model_runtime.py`).
- `B2.6` real RAG auto-reindex driven by the file watcher (`rag_watcher.py`).
- `B4.11` real encrypted backup/restore exposed over the HTTP bridge.
- `A1.1/A1.17` real CLI subprocess E2E and session import/stats endpoints.
- `B2.10` real HTTP API tester with host restrictions (`api_tester.py`).
- `C4.4` real AST codemods with diff preview (`codemod.py`).
- `C4.9` real git status/log/blame/stacked commits with write gating
  (`git_extras_runtime.py`).

**E2E layer:** `tests/test_e2e_operations.py`, `test_cli_e2e.py`, and the
`test_*_endpoints.py` files start the real backend/CLI and exercise file
creation, permission denials, provider failures, DLP, Cowork documents,
backups, session restore, update policy and endpoint hardening with
deterministic scripted providers.

**Final operational-completion tier counts:** 49 operational, 67 local modules
(real local logic with persistence/tests), 87 descriptors (UI/CI/data-shape
items whose real capability needs an external environment), 23 external-
dependency, 2 owner-gated. Full suite at this phase: **1015 passed,
10 skipped**. History was not rewritten; all commits are local, none pushed.

## Phase 2 batch — B2.7 real searchable offline documentation packs (P2)

**Implemented:** `src/keel/docpacks.py` upgrades the file-listing descriptor
into real search: local Markdown indexing with a BM25 inverted index (tokenize,
IDF/TF ranking), ranked hits with matched terms and highlighted snippets,
persisted packs (`DocPackStore`), three `cowork.docpack.*` capabilities and a
`keel docpack build|search|list` CLI. Fully local, no embeddings/model/network.

**Verification:** 7 new tests (`test_docpacks.py`) — all pass. Registry B2.7
evidence updated from descriptor to real search.

## Phase 2 batch — C13.2 real deterministic trajectory judge (P1)

**Implemented:** `src/keel/judge.py` upgrades the scoring scaffold into a
transparent four-criterion rubric (completion, policy compliance, tool-call
efficiency, latency) with per-criterion evidence, weights and findings, plus
best-of-N comparison and a Markdown rubric report. Fully deterministic; no
model is called. `external_adapters.judge_score` now delegates to it while
keeping its original keys for backward compatibility. Integrated via three
`code.judge.*` capabilities.

**Verification:** 8 new tests (`test_judge.py`) plus the existing
`test_external_adapters.py` — 11 pass. Registry C13.2 evidence updated.

## Phase 2 batch — B4.6 / B4.7 real fleet & observability views (P1)

**Implemented:** `src/keel/views.py` replaces pure capability flags with real
data transformations: kanban board (counts/completion), nested agent org chart
from `parent` ids, per-agent cost ranking with spend share, newest-first live
activity timeline, per-turn token waterfall with offline inline SVG, nested
flame graph with self/cumulative percentages, and structured prompt diff.
Integrated through seven `fleet.view.*` capabilities.

**Verification:** 7 new tests (`test_views.py`) — all pass. Registry B4.6/B4.7
evidence updated from descriptors to real view generation.

## Phase 2 batch — B2.2 real spec-driven mode (P1)

**Implemented:** `src/keel/spec_mode.py` upgrades the descriptor into a real
persistent workflow: structured spec with requirement IDs, dependency-ordered
task breakdown, explicit attributed approval gates between every phase
(spec→tasks→implement→verify→done), task status with dependency enforcement,
and mandatory verification evidence before the verify phase can complete.
`SpecStore` persists to local JSON. Integrated via five `code.spec.*`
capabilities and a `keel spec new|plan|approve|task|evidence|status|list` CLI.

**Verification:** 8 new tests (`test_spec_mode.py`) covering structure,
dependencies, approval gating, evidence enforcement, store roundtrip,
capability invoke and CLI E2E — all pass. Registry B2.2 evidence updated.

## Phase 2 batch — B2.8 real notebook execution (P1)

**Milestone:** next locally achievable feature per Master Plan v6 prioritized
build order (all P0 items verified or owner-gated; first P1 local_module with
only a descriptor). No new roadmap invented; feature ID `B2.8` unchanged.

**Implemented:** `src/keel/notebook.py` — a real Notebook/REPL tool that
executes markdown notebooks. Prose/code cells are parsed properly (fenced
blocks, superseding the keyword heuristic); all code cells run together in the
hardened sandbox with per-cell stdout capture and error isolation and shared
state like a REPL; `chart(...)` calls emit specs rendered to inline offline SVG
via `keel.charts`; `NotebookStore` persists notebooks in local state with
recoverable deletion. Integrated through four `cowork.*` capabilities and a
`keel notebook run|save|load|list|delete` CLI. No new dependencies.

**Verification:** 10 new tests (`test_notebook.py`) including real sandbox
execution, error isolation, inline SVG rendering, filesystem-write denial,
store roundtrip/recoverable delete, capability invoke and CLI subprocess E2E.
All pass. Registry B2.8 promoted from "Notebook cell parser" to real execution
evidence; `test_plan_index.py` 5 passed; full suite re-run below.

## External validation & distribution preparation phase

**Sandbox security decision:** implemented the strongest pure-Python boundary —
`sys.addaudithook` (immutable) that denies file access outside the workspace and
stdlib dirs, process creation, native `ctypes.dlopen`, and network by default;
scrubbed env (no credential keys), isolated temp cwd, POSIX rlimits (AS/CPU/
NPROC/FSIZE), capped output, guaranteed cleanup. 9 boundary tests pass. Honest
`code.sandbox.status` reports that native bypass and OS-level isolation
(seccomp/AppArmor/containers/Windows restricted tokens) are NOT enforced and
require an external environment.

**Windows distribution:** `docs/WINDOWS-EXTERNAL-VALIDATION.md` — reproducible
clean-machine package with checksums, install/uninstall, upgrade/rollback,
expected results and troubleshooting. `scripts/validate_desktop.py` runs 5 local
checks (all PASS) and lists 6 external checks as UNVERIFIED with exact commands.
Found and fixed a real defect: stale `dist/latest.yml` (size/sha512 disagreed
with the actual installer) — `release_integrity.py` detects and regenerates it
from the verified manifest; `keel.release integrity` reports 7/7 OK.

**Provider readiness:** `provider_validation.py` runs a real test matrix for
configured providers (auth, discovery, tools, streaming, usage, timeouts,
cancellation, switching, failure recovery) with `keel provider validate`; no
credentials are configured here, so live checks are honestly SKIP, never faked.

**Product review:** fixed misleading labels — the knowledge-work surface was
called "Keel Desktop" but is actually "Keel Cowork" (matching the four-surface
vision and backend surface IDs); session IDs stay `chat`/`code` for persistence
compatibility. Added `core.providers.validate` and `core.release.integrity`
capabilities (161 total). Full suite at this phase: **1110 passed, 10 skipped**.

## Final integration phase — capability hub and E2E workflows

**Disconnected-module audit:** found 77 of 134 runtime modules imported only by
tests. Built `capabilities.py` + `capability_registry.py`: a single permission-
aware capability hub with 158 capabilities covering all 77 modules (read/write/
execute tiers, lazy imports, explicit errors, audit log).

**Integration across surfaces:**
- Web bridge: `GET /api/capabilities` (with surface filter) and
  `POST /api/capabilities/invoke` (token + origin auth, permission gating,
  confirmation for mutating capabilities, audit to `capability-audit.jsonl`).
- CLI: `keel capability list/describe/invoke` with `--params`/`--confirm`.
- TUI: `/capabilities` and `/invoke <id> [json]` commands.
- Desktop/web UI: a "Modules" browser (Ctrl+Shift+M) listing every capability,
  parameter editor, confirmation checkbox, result view.

**E2E workflow tests (`test_workflows_e2e.py`):** real Cowork document lifecycle
(write/read/Q&A/xlsx stats), Code (snapshot/codemod/git/sandbox), Duet (inline
completion/reviewer/best-of-N/roles), Fleet (workflow versions/anomaly/events),
desktop profiles/layout, backup→loss→restore, and audit verification — all
through the real HTTP bridge with capabilities.

**Reliability/security (`test_reliability_e2e.py`):** corrupt persisted JSON,
permission denial (tool not executed), capability permission enforcement,
concurrent session isolation, interrupted agent recovery, large-file cap,
egress secret redaction. **Desktop artifacts (`test_desktop_artifacts.py`)** verify
the real packaged Electron app, sidecar `--version`, and clean artifacts.

**Verification:** full suite **1061 passed, 10 skipped**. No push/release/deploy.

Further real local upgrades after the first operational pass: model routing
wired into the CLI (opt-in `KEEL_MODEL_ROUTING`), read-only SQLite explorer with
query safety (`db_explorer.py`), SARIF 2.1.0 emission/ingestion (`sarif.py`),
offline SVG charts/diagrams (`charts.py`), and macro/prompt/spec authoring
helpers (`authoring.py`), plus session import/stats over the bridge.
