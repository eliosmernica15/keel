# Master Plan v6 — D3.* P1/P2 backend evidence

- Branch: `agent/b2-d3` (baseline `982335d`)
- Worktree: `C:\Users\Admin\.local\share\opencode\worktree\backend\b2-d3`
- New files only — no existing source, test, plan index or matrix was edited:
  - `keel/src/keel/d3_backend.py`
  - `keel/tests/test_d3_backend.py`
  - this evidence file
- Implementation tier: `local_module` — executable stdlib-only backend logic.
  No OS file I/O, subprocess launch, socket, database or UI is performed.
- The final commit SHA is reported in the agent hand-off message (one commit
  containing all three files).

## Scope derivation (coverage cannot silently drift)

`PLAN-INDEX.json` contains 23 `D3.*` rows: 10 are `P0` (all already `verified`
in `keel/src/keel/capability_seams.py`) and 13 are the `not_started` `P1`/`P2`
rows implemented here. `test_feature_ids_are_exactly_the_p1_and_p2_d3_rows`
reads the plan index and compares its `P1 ∪ P2` set with `FEATURE_IDS` (13 IDs),
asserting the two sets are disjoint from `P0`.

## Verification of the already-done D3 P0 rows (no files changed)

`verified_p0_references()` records the existing owner of every `P0` row;
`test_verified_p0_references_point_at_real_capability_seams_symbols` checks that
the plan's `P0` set equals the reference set, that each source/test file exists,
and that every named symbol is actually exported by `keel.capability_seams`.

| ID | Capability | Verified symbols in `capability_seams.py` |
|----|-----------|-------------------------------------------|
| D3.1 | Capability seam (definition + provider + consumer) | `SeamRegistry`, `CapabilitySeam`, `seam_checklist` |
| D3.2 | One provider swap moves the execution world | `resolve_provider`, `swap_world`, `world_manifest` |
| D3.6 | Human commands without a model turn | `CommandService`, `CommandRegistration` |
| D3.7 | Background jobs (`job_*` read/stop tools) | `job_tools`, `JOB_TOOLS` |
| D3.8 | Trusted-rule webhook runtime | `webhook_rule`, `WebhookRuleDescriptor` |
| D3.9 | Shell / terminals / sandbox backends; argv wrapping | `backend_services`, `sandbox_wrap_argv` |
| D3.11 | Missing package groups with honest classification | `classify_packages`, `package_policy` |
| D3.13 | Spill with preview and redaction | `plan_spill`, `redact_preview` |
| D3.14 | Loop/tool guards with monotonic deny | `GuardRegistry`, `GuardRegistration`, `GuardVerdict` |
| D3.18 | Workspace entities + session query | `WorkspaceService`, `SessionQueryService` |

Their own `keel/tests/test_capability_seams.py` (28 tests) still passes; this
change does not import or modify that module.

## Implemented rows (13)

| ID | Capability | Backend behaviour | Tests |
|----|-----------|-------------------|-------|
| D3.3 | Subagent providers behind one interface | `SubagentRegistry` / `SubagentProvider` / `ActivationDescriptor`: child, delegated-turn and external adapters share `SUBAGENT_INTERFACE`; activation flags distinguish a fresh child from a delegated turn | `test_subagent_kinds_share_one_activation_interface`, `test_subagent_registry_rejects_broken_contracts` |
| D3.4 | Agent Teams | `TeamService` enables a board **per root session**; `TeamBoard` owns task state policy (`todo → in_progress → done`, owner-only completion), membership/discovery, messaging with broadcast + inbox (own messages excluded), inbox-wait descriptors, and interruption | 3 tests (`test_teams_*`, `test_team_task_*`, `test_team_messaging_*`) |
| D3.5 | Agent presets / isolate realm | `PresetService.resolve()` composes a per-session capability set; `shared` rows keep one instance id, `isolate` rows get `preset/session/service` instance ids | `test_preset_isolate_rows_get_session_scoped_instances`, `test_preset_validation_*` |
| D3.10 | `fs/*` filesystem policy | `FsEventBus` dispatches waterfall listeners by tier (policy/plugins tier 2 **before** tier 1); a veto short-circuits and names the veto source; registration and decisions are validated | `test_fs_policy_listeners_run_tier2_first_and_can_veto`, `test_fs_event_bus_validation_and_allow_path` |
| D3.12 | Deliverables | `DeliverableService` attaches named file/summary/report items per turn, hashes supplied content with SHA-256, lists them deterministically and renders result-card descriptors (`open_action`, `export_action`) | `test_deliverables_attach_per_turn_and_render_result_cards`, `test_deliverable_validation` |
| D3.15 | Extensions (runtime self-modification) | `ExtensionService` records approval-gated skill/command/agent diff proposals with a SHA-256 of the diff; `application()` is refused until an explicit owner approves and always reports `performed=False`, `writes=False` — **never auto-installs** | `test_extensions_require_explicit_owner_approval`, `test_extension_reject_and_proposal_digests` |
| D3.16 | Feedback | `FeedbackService` records up/down + note (2000-char bound) locally and computes summary counts; no transmission and no eval-service call in this layer | `test_feedback_records_summaries_and_stays_local` |
| D3.17 | Anonymous identity | `derive_install_id()` / `generate_install_id()` produce `local-…` ids (deterministic from seed or CSPRNG); `public_view()` hides the id, `export_for_transmission()` always raises; telemetry/transmitted flags rejected at construction | `test_install_identity_*`, `test_identity_rejects_*` |
| D3.19 | Plan + schedule | `PlanLog` is append-only and `replay(events)` rebuilds the exact checklist (survives restart); `ScheduleService` computes `due_at` with `datetime`+`timedelta`, supports ISO strings, `pending`, `is_due`, one-shot `fire` — no timer/thread | `test_plan_log_*`, `test_schedule_*` (4 tests) |
| D3.20 | `experimental/` quarantine | `ProductPackagePolicy` requires experimental packages to be declared and live under `keel/experimental/`, and non-experimental packages to state product use or an explicit classification; `check_layout()` returns violations; enforces flag `X6.10`; never writes the policy file | `test_quarantine_layout_accepts_documented_packages`, `test_quarantine_rejects_misplaced_and_unclassified_packages` |
| D3.21 | Generated provider metadata | `generate_metadata()` hashes canonicalised source inputs; `check_metadata()` compares per-provider digests and returns a read-only verdict (`reject_stale=True`, `writes=False`, `rewrites=False`); `assert_metadata_fresh()` raises on stale/missing data without touching files | `test_metadata_check_rejects_stale_data_without_writing`, `test_canonical_digest_*` |
| D3.22 | Inspector seam (backend only) | `PinnedSource` + `InspectorBuildSpec` require a 64-hex pin, offline build and no browser download; `inspector_build_plan()` lists verify/compile/package steps with `network=False`; `check_offline_build()` rejects `http(s)://`, `curl`/`wget` and `fetch(` in build sources — no frontend is built | `test_inspector_build_is_pinned_offline_and_published`, `test_inspector_rejects_unpinned_or_network_dependencies` |
| D3.23 | Live Share wire codecs (experimental) | `WireCodec` frames versioned JSON with magic + length + SHA-256 checksum for node-compatible decoders; rejects bad magic/length/checksum/JSON/version/kind; descriptor states `read_only`, `lan_only`, `cloud_relay=False`, `browser_carrier_implemented=False` | 3 tests (`test_wire_frames_round_trip_for_every_kind` × 4 kinds, `test_wire_codec_rejects_corrupt_frames`, `test_wire_descriptor_*`) |

`all_backend_descriptors()` returns one uniform row per feature ID with
`layer="stdlib_backend"`, `runtime_claimed=True` (the in-process logic really
runs), and `io_performed=False`, `network=False`, `frontend=False`.

## Key invariants (tested)

- **Determinism:** equal inputs produce equal descriptors; presets and plan
  replay are stable across sessions/restarts; deliverable and extension digests
  are content-addressed.
- **Fail loud:** invalid kinds, realms, tiers, states, dates, checksums,
  approval flows and policy classifications raise typed `D3BackendError`
  subclasses rather than returning a plausible-looking result.
- **No fake success:** `application()` of an extension, the inspector build
  plan, metadata checks and all descriptors explicitly report `performed`,
  `writes`, `network` or `io_performed` as `False` where nothing happened.
- **No auto-install / no telemetry:** extensions need an approver; the install
  id cannot be exported or flagged for telemetry.
- **Containment and authority:** teams are per root session; task completion
  is owner-only; quarantine paths must match policy; FS policy tier 2 runs
  first and a veto stops the waterfall.

## Tests and results

`keel/tests/test_d3_backend.py` — 35 tests covering all 13 rows, including the
plan-index coverage checks and the P0 reference verification.

Commands and results (run from the worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_d3_backend.py']))"
35 passed in 4.17s

python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_capability_seams.py','keel/tests/test_d3_backend.py']))"
63 passed in 7.44s
```

## Integration seams (where a consumer would attach this layer)

| Existing surface | Seam |
|------------------|------|
| `keel/src/keel/agent_contracts.py`, `subagent.py` | `SubagentRegistry.activate()` is the single activation descriptor for child/delegated/external providers. |
| `keel/src/keel/fleet/` (task board, members, inbox) | `TeamBoard` supplies the per-root-session policy/state machine; the fleet routes own transport. |
| `keel/src/keel/capability_registry.py` | `PresetService.resolve()` is the per-session capability-set manifest, including `isolate` instance ids. |
| `keel/src/keel/providers/` | `FsEventBus` carries `fs/*` policy events on top of the provider boundary. |
| `keel/src/keel/toolresult.py`, `views.py` | `DeliverableService.card()` is the backend result card a future panel would render. |
| `keel/src/keel/skills_manager.py`, `commands.py` | `ExtensionService.application()` is the approval-gated gate before any installation wiring. |
| `keel/src/keel/identity_contracts.py` | `InstallIdentity` supplies the local-only anonymous id (no transport). |
| `keel/src/keel/session.py`, `workflows.py` | `PlanLog.replay()` / `ScheduleService` supply durable-plan and follow-up descriptors. |
| `keel/src/keel/feature_flags.py`, `provider_catalog.py` | `ProductPackagePolicy` / `check_metadata()` are the read-only policy and staleness checks. |
| packaging / release scripts | `inspector_build_plan()` / `check_offline_build()` are the pin-and-offline checks; the dock itself is a future frontend build. |

No existing module imports this new module: integration is intentionally a
follow-up wiring step, so this change cannot alter current runtime behaviour.

## Limitations / honesty statement

This is backend logic only. It does not write deliverable files, install
extensions, open sockets, compile the inspector frontend, render a live-share
viewer, start timers, persist records to disk, or transmit any identity. The
frontend parts of D3.12/D3.22/D3.23 and the browser carrier/node runtime of
D3.23 are explicitly out of scope and are described as such in the descriptors.
`liveshare` and `inspector` remain `external_dependency` in `classify_packages()`
where a real carrier/compiled asset is still required.
